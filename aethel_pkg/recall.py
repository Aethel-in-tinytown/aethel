"""Semantic recall: her memory stops being a pile (v0.33, NLTK plan Phase 2).

A deterministic relevance score between a query (a dream she is about
to settle, a passage she is reading, a letter she is composing) and a
candidate text (usually one of her beliefs). The score is

    score = LEMMA_WEIGHT * rarity-weighted lemma overlap
          + WORDNET_WEIGHT * WordNet path similarity

and every score carries its explanation with it: the top shared
lemmas and the best shared synset path, names and glosses included,
so her journal can say WHY a memory surfaced ("this resembles what
you concluded from Frankenstein: you share 'create' and the path
through creature.n.01 ~ abandonment.n.01") instead of reporting a
mute number. Explainability is a design requirement here (the plan's
addendum: an explainable memory beats a stronger mute one), not a
garnish: the why-payload is part of the score function's return
value, and the organism journals a summary of it on every recall.

Design choices, argued (the Kevin standard — docstrings argue):

RARITY WEIGHTS. A lemma's weight is its inverse document frequency
over HER corpus (beliefs + dreams + kept passages + recent memory —
the texts resident in her state blob; the journal proper is
unbounded, and rarity is a property of what she carries, not of
everything she has ever written). weight(l) = ln((N+1)/(df(l)+1)) + 1,
the smoothed form, so an unseen lemma gets the maximum weight
instead of infinity and a lemma in every document still weighs 1.
Corpus statistics are RECOMPUTED from the stored texts on every
recall rather than cached in state: the texts are few (her beliefs
cap at 50), recomputation is microseconds, and a cache would be a
second source of truth that a restart would have to prove faithful.
A pure function of stored texts cannot drift from them.

LEMMA OVERLAP is a weighted Jaccard: sum of weights of shared
content lemmas over sum of weights of the union. Normalizing by the
union keeps long candidates from winning by bulk, and weighting by
rarity keeps "life" and "thing" from outvoting "abandonment".

WORDNET COMPONENT. For content lemmas in query and candidate,
synsets are chosen with the SAME rule the vocabulary notebook uses
(POS-filtered first match in WordNet's frequency order, first-synset
fallback — see notebook.choose_synset; one rule everywhere, so a
word means the same sense in her notebook and in her memory). For
each query lemma we take its BEST path similarity over candidate
lemmas and average those bests. Three restrictions, each earned in
calibration against her real corpus: (1) only noun and verb synsets
participate — adjective and adverb trees are too shallow for path
similarity to mean anything (unrestricted, unrelated adverbs score
a flat 0.33 against each other and drown the signal); (2) pairs must
share a WordNet POS category, since cross-category paths are an
artifact of the root, not of meaning; (3) identical lemmas are
excluded — they are already paid in the overlap term. Cost is
bounded by WN_LEMMA_CAP: at most 8 query lemmas x 8 candidate
lemmas = MAX_SYNSET_PAIRS (64) path lookups per score, the lemmas
chosen by rarity weight (the ones that carry the meaning), ties
broken by lemma so the cap itself is deterministic.

DIVERSITY. Recall that always surfaces the same belief makes her
monotonous — the plan names this risk explicitly. The mechanism:
a candidate recalled within the last DIVERSITY_WINDOW recall events
has its score multiplied by (1 - DIVERSITY_PENALTY). Recall history
is derived FROM THE JOURNAL (every recall is journaled, below), so
the history is a pure function of the append-only log and
restart-faithful by construction; nothing about diversity lives in
state, and a rebuilt Aethel inherits exactly the diversity her
journal implies. The rejected alternative, persisted recall counts,
would need its own fidelity proof and could disagree with the diary.

PERSONAL ASSOCIATION (v0.37, NLTK plan Phase 6a). When the caller
hands in her persisted co-occurrence graph (the counts she has kept
since long before this phase — meals only, until 6a extended the
coverage to her own writing), a third term personalizes the score:
query lemmas whose graph neighbors include candidate lemmas earn a
bonus. The arithmetic is deliberately kept on a short leash. Per
query lemma, the best neighbor strength is count/(count +
ASSOC_SATURATION) — a saturating function in [0, 1), so one shared
meal already counts (0.2) but no single association, however often
repeated, can approach 1 by itself; identical lemmas are excluded
(they are already paid in full by the overlap term). The term is
the mean of those bests over all query content lemmas. It enters
through the headroom the base score leaves:

    total = base + ASSOC_WEIGHT * assoc * (1 - base)

so the bonus is at most ASSOC_WEIGHT (0.10) — strictly less than
the WordNet term's own maximum contribution (0.25) — and it shrinks
as the base score grows: an already-certain match cannot be pushed
further by habit, and association alone can never outvote the
0.75/0.25 evidence, only break the near-ties where personalization
is the honest decider. A graph is an OPTIONAL argument everywhere:
without one the term is exactly 0 and the score is the pre-6a
score, bit for bit — which is what keeps the Phase 2 goldens and
every caller that does not pass a graph untouched.

DETERMINISM. No randomness anywhere in this module: ranking is
(score desc, candidate id asc), every cap and sort carries an
explicit tie-break, and scores are rounded to 6 decimals in the
why-payload so a journaled score is the score that was compared.

FAIL-CLOSED / HEURISTIC GATE. This module is only ever constructed
with an NLTK backend (the organism checks its `_nlp` gate before
every call and returns before touching state, journal, or RNG in
heuristic mode). With no WordNet reader the WordNet term is 0 and
the overlap term still stands — absence is data, never a silent
substitution of a different algorithm.
"""

import hashlib
import math
from dataclasses import dataclass

from .notebook import wn_pos

#: Score mixture. Lemma overlap is the load-bearing term (it is her
#: own words, rarity-weighted); WordNet paths are the second signal,
#: valuable exactly where her wording diverges from her earlier
#: wording, and too blunt to lead.
LEMMA_WEIGHT = 0.75
WORDNET_WEIGHT = 0.25

#: Phase 6a personal association: the bonus cap and the saturation
#: constant of the per-pair strength count/(count + K). See the
#: module docstring for why the bonus enters through the base
#: score's headroom instead of as a third mixture weight.
ASSOC_WEIGHT = 0.10
ASSOC_SATURATION = 4.0

#: A reading whose best belief scores below this does not earn a
#: resemblance line in her narration. Calibration on her canonical
#: book beliefs: a genuinely kindred passage scores 0.15-0.45, an
#: unrelated one under 0.06 (mostly WordNet background). 0.12 sits
#: between, nearer the noise floor: resemblance should be common
#: enough to seed an inner life, rare enough to mean something.
READING_THRESHOLD = 0.12

#: Diversity: how many recent recall events shadow a candidate, and
#: how hard. A window of 12 recalls is roughly a day or two of her
#: morning tables and reading; a halved score lets a dominant belief
#: still win when it is truly the only kin in the room (raw score
#: twice the runner-up), which is the honest outcome, while near
#: ties rotate.
DIVERSITY_WINDOW = 12
DIVERSITY_PENALTY = 0.5

#: WordNet cost bound: lemmas per side and the resulting pair cap.
WN_LEMMA_CAP = 8
MAX_SYNSET_PAIRS = WN_LEMMA_CAP * WN_LEMMA_CAP

#: WordNet categories whose hypernym trees are deep enough for path
#: similarity to carry meaning (see module docstring).
_WN_CATEGORIES = ("n", "v")


def candidate_id(text):
    """A belief's identity: a stable digest of its text. Beliefs are
    plain strings with no ids of their own; the digest is a pure
    function of the text, so the same belief has the same id in
    every process and after every restart, and the journal's recall
    history can name it without storing the whole belief per event."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def select_synset(wordnet, lemma, pos_tag):
    """The chosen synset OBJECT for a lemma, by the notebook's rule:
    POS-filtered first match (WordNet frequency order), falling back
    to the first synset overall. Returns None when the reader is
    absent or the lemma is unknown to WordNet."""
    if wordnet is None or not lemma:
        return None
    synsets = wordnet.synsets(lemma, pos=wn_pos(pos_tag))
    if not synsets:
        synsets = wordnet.synsets(lemma)
    return synsets[0] if synsets else None


class CorpusStats:
    """Document frequencies over her corpus: a pure function of the
    texts handed in, recomputed per recall (see module docstring)."""

    def __init__(self, doc_count, df):
        self.doc_count = doc_count
        self.df = df

    def weight(self, lemma):
        """Smoothed inverse document frequency: rare lemmas weigh
        more, corpus-wide lemmas still weigh 1, unseen lemmas weigh
        the most (they are the query's news, not its noise)."""
        return math.log((self.doc_count + 1) / (self.df.get(lemma, 0) + 1)) + 1.0


@dataclass(frozen=True)
class RecallResult:
    candidate_id: str
    text: str
    score: float  # diversity-adjusted; the ranking score
    raw_score: float  # the pure relevance score, before diversity
    why: dict  # explanation payload (see SemanticRecall.score)


class SemanticRecall:
    """Scoring and ranking over one language backend. Holds no state
    beyond the backend and its WordNet reader; every method is a pure
    function of its arguments and the pinned WordNet data."""

    def __init__(self, language):
        self.language = language
        self.wordnet = getattr(language, "wordnet", None)

    # -- analysis ------------------------------------------------------
    def content_map(self, text):
        """lemma -> POS tag of its first occurrence, content tokens
        only (the backend's own content predicate, so recall sees
        exactly the words acquisition saw)."""
        analysis = self.language.analyze(text)
        is_content = getattr(self.language, "content", None)
        out = {}
        for token in analysis.tokens:
            if is_content is not None and not is_content(token):
                continue
            if token.lemma not in out:
                out[token.lemma] = token.pos
        return out

    def corpus_stats(self, texts):
        """Build CorpusStats from raw texts (documents = texts)."""
        df = {}
        for text in texts:
            for lemma in self.content_map(text):
                df[lemma] = df.get(lemma, 0) + 1
        return CorpusStats(len(texts), df)

    # -- scoring ---------------------------------------------------------
    def _wordnet_term(self, qmap, cmap, stats):
        """(score, best_path) — mean of per-query-lemma best path
        similarities, over the bounded, category-matched pair set."""
        q_lemmas = sorted(qmap, key=lambda l: (-stats.weight(l), l))[:WN_LEMMA_CAP]
        c_lemmas = sorted(cmap, key=lambda l: (-stats.weight(l), l))[:WN_LEMMA_CAP]
        q_syn = {l: select_synset(self.wordnet, l, qmap[l]) for l in q_lemmas}
        c_syn = {l: select_synset(self.wordnet, l, cmap[l]) for l in c_lemmas}
        best_total = 0.0
        counted = 0
        best_path = None
        pairs = 0
        for ql in q_lemmas:
            qs = q_syn[ql]
            if qs is None or qs.pos() not in _WN_CATEGORIES:
                continue
            best = 0.0
            for cl in c_lemmas:
                if cl == ql or pairs >= MAX_SYNSET_PAIRS:
                    continue
                cs = c_syn[cl]
                if cs is None or cs.pos() != qs.pos():
                    continue
                pairs += 1
                sim_fn = getattr(qs, "path_similarity", None)
                if sim_fn is None:
                    continue
                try:
                    sim = sim_fn(cs)
                except Exception:
                    sim = None
                if sim is None:
                    continue
                if sim > best:
                    best = sim
                if best_path is None or sim > best_path["similarity"]:
                    best_path = {
                        "query_lemma": ql,
                        "candidate_lemma": cl,
                        "similarity": round(sim, 6),
                        "query_synset": qs.name(),
                        "query_gloss": qs.definition(),
                        "candidate_synset": cs.name(),
                        "candidate_gloss": cs.definition(),
                    }
            best_total += best
            counted += 1
        return (best_total / counted if counted else 0.0), best_path

    def _assoc_term(self, qmap, cmap, cooc):
        """(assoc_score, evidence) — her own associations between
        the query's lemmas and the candidate's, read off the
        co-occurrence graph. The graph is symmetric by construction
        (every update writes both directions), so one row lookup per
        query lemma suffices. Pure function of the graph handed in;
        an absent or empty graph scores exactly 0 with no evidence,
        which is what makes the term opt-in per caller."""
        if not cooc or not qmap or not cmap:
            return 0.0, []
        cand = set(cmap)
        total = 0.0
        evidence = []
        for ql in sorted(qmap):
            row = cooc.get(ql) or {}
            best_lemma, best_count, best_strength = None, 0, 0.0
            for cl in sorted(cand):
                if cl == ql:
                    continue
                count = row.get(cl, 0)
                if not count:
                    continue
                strength = count / (count + ASSOC_SATURATION)
                if strength > best_strength:
                    best_lemma, best_count, best_strength = (
                        cl,
                        count,
                        strength,
                    )
            total += best_strength
            if best_lemma is not None:
                evidence.append(
                    {
                        "query_lemma": ql,
                        "candidate_lemma": best_lemma,
                        "count": int(best_count),
                        "strength": round(best_strength, 6),
                    }
                )
        evidence.sort(
            key=lambda e: (-e["strength"], e["query_lemma"], e["candidate_lemma"])
        )
        return total / len(qmap), evidence

    def score(self, query_text, candidate_text, stats=None, cooc=None):
        """(score, why) for one query/candidate pair. `stats` carries
        the corpus rarity weights; without one, the pair alone is the
        corpus (every lemma equally rare — the honest degenerate).
        `cooc`, when given, is her co-occurrence graph and earns the
        bounded Phase 6a association bonus (module docstring)."""
        qmap = self.content_map(query_text)
        cmap = self.content_map(candidate_text)
        if stats is None:
            df = {}
            for m in (qmap, cmap):
                for lemma in m:
                    df[lemma] = df.get(lemma, 0) + 1
            stats = CorpusStats(2, df)
        shared = sorted(
            set(qmap) & set(cmap),
            key=lambda l: (-stats.weight(l), l),
        )
        union = set(qmap) | set(cmap)
        union_weight = sum(stats.weight(l) for l in union)
        lemma_score = (
            sum(stats.weight(l) for l in shared) / union_weight if union_weight else 0.0
        )
        wordnet_score, best_path = self._wordnet_term(qmap, cmap, stats)
        base = LEMMA_WEIGHT * lemma_score + WORDNET_WEIGHT * wordnet_score
        assoc_score, associations = self._assoc_term(qmap, cmap, cooc)
        total = base + ASSOC_WEIGHT * assoc_score * (1.0 - base)
        why = {
            "shared_lemmas": [
                {"lemma": l, "weight": round(stats.weight(l), 6)} for l in shared[:5]
            ],
            "best_path": best_path,
            "lemma_score": round(lemma_score, 6),
            "wordnet_score": round(wordnet_score, 6),
            "assoc_score": round(assoc_score, 6),
            "associations": associations[:5],
        }
        return total, why

    # -- ranking ---------------------------------------------------------
    def recall(self, query_text, candidates, k=1, stats=None, recent_ids=(), cooc=None):
        """Top-k (candidate, score, why) for a query.

        `candidates` is an iterable of (candidate_id, text) pairs.
        `recent_ids` are candidate ids recalled within the diversity
        window (the organism derives them from the journal); those
        candidates are deprioritized per DIVERSITY_PENALTY — the
        penalty is applied BEFORE ranking, and the result carries
        both the adjusted and raw scores so the journal can show its
        work. Ranking: adjusted score desc, candidate id asc. No
        randomness, ever. `cooc` is forwarded to score() for the
        Phase 6a association term."""
        candidates = list(candidates)
        if stats is None:
            stats = self.corpus_stats([t for _, t in candidates])
        recent = set(recent_ids)
        results = []
        for cid, text in candidates:
            raw, why = self.score(query_text, text, stats, cooc=cooc)
            penalized = cid in recent
            adjusted = raw * (1.0 - DIVERSITY_PENALTY) if penalized else raw
            why = dict(why)
            why["diversity_penalized"] = penalized
            results.append(RecallResult(cid, text, adjusted, raw, why))
        results.sort(key=lambda r: (-r.score, r.candidate_id))
        return results[:k]


def why_summary(why):
    """One deterministic line summarizing a why-payload, for the
    journal: the shared lemmas, the best synset path when one
    carried weight, and the two term scores."""
    parts = []
    shared = [s["lemma"] for s in why.get("shared_lemmas") or []]
    if shared:
        parts.append("shared lemmas: " + ", ".join(shared))
    path = why.get("best_path")
    if path:
        parts.append(
            "best path: {query_lemma} ~ {candidate_lemma} via "
            "{query_synset} / {candidate_synset} ({similarity})".format(**path)
        )
    parts.append("lemma {lemma_score}, wordnet {wordnet_score}".format(**why))
    associations = why.get("associations") or []
    if associations:
        parts.append(
            "her associations: "
            + ", ".join(
                "{query_lemma}~{candidate_lemma}".format(**a) for a in associations
            )
            + f" (assoc {why.get('assoc_score')})"
        )
    if why.get("diversity_penalized"):
        parts.append("diversity-penalized")
    return "; ".join(parts)
