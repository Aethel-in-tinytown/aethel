"""Entity recognition, Route A (v0.34, NLTK plan Phase 3).

She learns who is who in what she reads, using only what the tagger
already gives her: POS-driven proper-noun phrase extraction from an
Analysis, matched against a growing gazetteer. No ne_chunk, no new
data downloads (Route B stays unbuilt until Route A measurably
underperforms on her real reading — the plan gates it on evidence
one build run cannot produce).

Design choices, argued (the Kevin standard — docstrings argue):

EXTRACTION. A phrase is a maximal run of NNP/NNPS tokens within one
sentence, and its name is the passage slice from the run's first
token start to its last token end, byte-for-byte ("Mr" + "Darcy"
yields "Mr. Darcy" because the slice carries the punctuation and
space between them). Possessives split by the tokenizer ('s is its
own token) never join a run, so "Scrooge's" extracts as "Scrooge".

THE SENTENCE-INITIAL RULE. Capitalization at a sentence start is
evidence of nothing — every sentence starts capitalized — so an
initial token is held to a stricter standard than a mid-sentence
one, in this order:
  1. POS is the first witness. An initial token the tagger calls a
     common noun (NN/NNS) is NOT an entity, unless the phrase
     starting there matches the gazetteer (the tagger can mistag a
     known name as NN at a boundary; a known name outranks a tag).
  2. An initial token the tagger calls proper (NNP/NNPS) is accepted
     when it is gazetteer-known, or when the same surface appears
     as a proper token in a non-initial position in the same
     passage (corroboration: "Scrooge signed it. ... upon Scrooge's
     name" — the second sighting is mid-sentence, where capitals
     mean something).
  3. Otherwise the WordNet common-lemma check decides: if any
     synset for the word carries a lemma spelled exactly like the
     lowercase surface ("happiness", "fog", "scrooge" the miser),
     the word is a common noun the tagger promoted for standing
     first, and it is rejected. Proper names in WordNet carry
     capitalized lemma forms ("Marley", "Elizabeth"), so they pass.
     This is precision bought at a stated price: a genuine entity
     that appears only sentence-initially, only once, and shares its
     spelling with a common noun will be missed. Route A prefers
     missing a name to inventing one.
  4. With no WordNet reader the check cannot run; initial,
     uncorroborated, unknown proper tokens are then accepted on the
     tagger's word alone (absence of the check is data, and the
     organism only ever builds this in NLTK mode, where the reader
     exists). Multi-token initial runs are judged by their head
     token; a rejected head rejects the run.
Mid-sentence, POS is trusted outright: a capital there is the
writer's own signal.

GAZETTEER STORAGE. The registry rides inside the organism state
blob under the "gazetteer" key, beside the notebook, for the
notebook's own reason: a separate kv blob would commit on its own
schedule and fork from the heartbeat's transaction, and the
restart-fidelity harness compares state blobs. In heuristic mode
the key is omitted entirely, so a heuristic life's blob stays
bit-identical to a pre-entity one.

SEED. The seed is a deterministic pure function of her world data,
imported (lazily, to keep this module cycle-free) from its canonical
homes, never invented here: her parents and the five denizens from
town_pkg.town's rosters (kind person), the town's place names from
town_pkg.places.PLACES (kind place), and the authors of her classic
reading list from config.CLASSIC_SEEDS (kind author, duplicates
collapsed in list order). Seed entries carry origin "world".

GROWTH. A phrase that is not in the gazetteer is tracked as a
candidate: every sighting is journaled by the organism as
entity_seen, and the candidate's distinct sources are persisted in
the registry itself (the notebook's counting discipline: distinct
SOURCE LABELS, the meal-source strings Phase 1 defined sources by —
"classic", "wikipedia", ... — not raw repetitions). At
GROWTH_SOURCES distinct sources the candidate joins the gazetteer
with kind "unknown" and origin "growth". No stronger kind is
claimed: POS alone cannot tell a person from a place, and the one
author pattern that could justify "author" (the phrase is a seeded
book's author) is already in the seed, so it can never fire for a
grown entry. An honest "unknown" beats a guessed "person".

MATCHING. A surface matches an entry exactly, under article
variants ("Library" for "the Library"), or — for people and
authors — by unique surname ("Dickens" for Charles Dickens).
Shared surnames match nothing: "Brontë" names two seeded authors,
and picking a sister would be inventing an attribution.

COUNTS. An entry's met_count counts entity_met journal events, and
nothing else: it increments exactly when the organism journals a
reading's entity_met naming that entry (a just-promoted candidate's
promotion reading is its first met, count 1; its earlier sightings
stand in the journal as entity_seen). A count quoted in narration
("third time") is therefore derivable from the journal by
construction, never a second, driftable tally.
"""

#: Distinct source labels at which an unknown phrase joins.
GROWTH_SOURCES = 2

PROPER_POS = ("NNP", "NNPS")
COMMON_POS = ("NN", "NNS")

_LEADING_STRIP = ("the ", "my ")


def normalize(name):
    """The matching key for a name: whitespace collapsed, edge
    punctuation shed, lowercased. "Mr." and "Mr" share a key."""
    out = []
    for part in str(name).replace("\u00a0", " ").split():
        part = part.strip(".,;:!?\"'()[]")
        if part:
            out.append(part.lower())
    return " ".join(out)


def _key_variants(name):
    """All keys a surface may match under: the normalized name, and
    the same with a leading article/possessive shed or supplied —
    her places are seeded as "the Library" but texts say "Library",
    and texts say "the Library" for a place seeded bare."""
    key = normalize(name)
    variants = {key}
    for prefix in _LEADING_STRIP:
        if key.startswith(prefix):
            variants.add(key[len(prefix):])
    variants.add("the " + key)
    return variants


def ordinal(n):
    """1 -> 'first', 2 -> 'second', ..., 12 -> 'twelfth', then
    numeric with the correct suffix (21st, 22nd, 23rd, 24th)."""
    words = [
        "first", "second", "third", "fourth", "fifth", "sixth",
        "seventh", "eighth", "ninth", "tenth", "eleventh", "twelfth",
    ]
    if 1 <= n <= len(words):
        return words[n - 1]
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _is_common_word(wordnet, surface):
    """True when WordNet knows the lowercase surface as a common
    lemma (a lemma spelled exactly like it, all lowercase). Proper
    names carry capitalized lemma forms and do not trip this."""
    if wordnet is None or not surface:
        return False
    lowered = surface.lower()
    try:
        synsets = wordnet.synsets(lowered)
    except Exception:
        return False
    for syn in synsets or ():
        try:
            lemmas = syn.lemmas()
        except Exception:
            continue
        for lemma in lemmas:
            attr = getattr(lemma, "name", None)
            name = attr() if callable(attr) else (attr or str(lemma))
            if name.replace("_", " ").lower() == lowered and name == name.lower():
                return True
    return False


def extract_phrases(analysis, known_keys=(), wordnet=None):
    """Proper-noun phrases in one Analysis, in passage order.

    Returns [{"name", "start", "end", "sentence_initial"}] with the
    name sliced byte-for-byte from the source text. `known_keys` are
    normalized gazetteer keys (Gazetteer.match_keys); `wordnet` is
    the backend's reader, or None (see the module docstring for what
    each witness decides). Pure: no state, no randomness."""
    known = set(known_keys)

    def name_like(tok):
        """A token that can carry a name at all: news text tags
        stray punctuation (a quote mark) NNP often enough that a
        run built from it would christen an entity named '""'."""
        return any(c.isalpha() for c in tok.text)

    tokens = list(analysis.tokens)
    if not tokens:
        return []
    # Sentence membership and first-token flags, from the spans.
    sentences = list(analysis.sentences) or [(0, len(analysis.text))]

    def sentence_of(tok):
        for idx, (s, e) in enumerate(sentences):
            if s <= tok.start < e:
                return idx
        return len(sentences) - 1

    sent_idx = [sentence_of(t) for t in tokens]
    initial = []
    seen_sent = set()
    for i, sidx in enumerate(sent_idx):
        initial.append(sidx not in seen_sent)
        seen_sent.add(sidx)
    # Corroboration set: surfaces seen proper in non-initial spots.
    corroborated = {
        normalize(tokens[i].text)
        for i in range(len(tokens))
        if not initial[i] and tokens[i].pos in PROPER_POS and name_like(tokens[i])
    }

    def gazetteer_match_at(i):
        """Longest gazetteer phrase starting at token i (<=4 tokens),
        as a token count, or 0. Used for the sentence-initial NN
        exception and to accept known initial proper runs outright."""
        best = 0
        parts = []
        for j in range(i, min(i + 4, len(tokens))):
            if sent_idx[j] != sent_idx[i]:
                break
            parts.append(tokens[j].text)
            if _key_variants(" ".join(parts)) & known:
                best = j - i + 1
        return best

    phrases = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.pos in PROPER_POS and name_like(tok):
            j = i
            while (
                j + 1 < len(tokens)
                and tokens[j + 1].pos in PROPER_POS
                and name_like(tokens[j + 1])
                and sent_idx[j + 1] == sent_idx[i]
            ):
                j += 1
            if initial[i] and not gazetteer_match_at(i):
                head = tok.text
                if normalize(head) not in corroborated and _is_common_word(
                    wordnet, head
                ):
                    i = j + 1
                    continue
            phrases.append(
                {
                    "name": analysis.text[tok.start:tokens[j].end],
                    "start": tok.start,
                    "end": tokens[j].end,
                    "sentence_initial": bool(initial[i]),
                }
            )
            i = j + 1
            continue
        if (
            initial[i]
            and tok.pos in COMMON_POS
            and tok.text[:1].isupper()
            and name_like(tok)
        ):
            span = gazetteer_match_at(i)
            if span:
                last = tokens[i + span - 1]
                phrases.append(
                    {
                        "name": analysis.text[tok.start:last.end],
                        "start": tok.start,
                        "end": last.end,
                        "sentence_initial": True,
                    }
                )
                i += span
                continue
        i += 1
    return phrases


def seed_entries():
    """The world's seed registry, deterministically ordered:
    parents and denizens (person), town places (place), classic
    authors (author). Returns entry dicts in seed order; callers
    key them by normalize(name). Imports are lazy: town_pkg pulls
    in the organism's RNG/world modules, and this module must stay
    importable without that weight at organism import time."""
    from .config import CLASSIC_SEEDS
    from town_pkg.places import PLACES
    from town_pkg.town import DEFAULT_PARENTS, DEFAULT_ROSTER

    out = []
    seen = set()

    def add(name, kind):
        key = normalize(name)
        if key and key not in seen:
            seen.add(key)
            out.append({"name": name, "kind": kind, "origin": "world"})

    for name, *_rest in DEFAULT_PARENTS:
        add(name, "person")
    for name, *_rest in DEFAULT_ROSTER:
        add(name, "person")
    for place in PLACES.values():
        add(place, "place")
    for book in CLASSIC_SEEDS:
        if book.get("author"):
            add(book["author"], "author")
    return out


def belief_link(belief_text, entity_names):
    """The journal payload linking a belief to its entities: the
    belief id is the Phase 2 scheme (first 12 hex of the SHA-256 of
    the belief text, recall.candidate_id), so a link names a belief
    the same way every recall event does."""
    from .recall import candidate_id

    return {
        "belief_id": candidate_id(belief_text),
        "belief": belief_text[:120],
        "entities": list(entity_names),
    }


class Gazetteer:
    """Known entities plus not-yet-known candidates. Pure
    bookkeeping: this class journals nothing; feed() returns the
    events and the organism journals them, so the registry is
    testable without a diary and restarts are dict round-trips."""

    def __init__(self):
        self.entries = {}  # normalize(name) -> entry dict
        self.candidates = {}  # normalize(name) -> candidate dict

    def __len__(self):
        return len(self.entries)

    def __contains__(self, name):
        return self.find_key(name) is not None

    @classmethod
    def seeded(cls):
        gaz = cls()
        for row in seed_entries():
            gaz.entries[normalize(row["name"])] = {
                "name": row["name"],
                "kind": row["kind"],
                "origin": row["origin"],
                "sources": [],
                "met_count": 0,
            }
        return gaz

    # -- matching -------------------------------------------------------
    def _surname_keys(self):
        """Unique-surname -> entry key, for people and authors.

        Texts overwhelmingly mention "Dickens", not "Charles
        Dickens", so a multi-token person/author entry also answers
        to its last token — but only when that surname is unique in
        the registry. "Brontë" names two seeded authors (Charlotte
        and Emily); a bare "Brontë" is genuinely ambiguous, and
        guessing which sister a text meant would be an invented
        attribution, so shared surnames match nothing."""
        counts = {}
        last_of = {}
        for key, entry in self.entries.items():
            if entry["kind"] not in ("person", "author"):
                continue
            parts = normalize(entry["name"]).split()
            if len(parts) >= 2:
                counts[parts[-1]] = counts.get(parts[-1], 0) + 1
                last_of[parts[-1]] = key
        return {s: last_of[s] for s, n in counts.items() if n == 1}

    def match_keys(self):
        """Every normalized key a surface may match under, seed and
        grown entries alike (article variants and unique surnames
        included)."""
        keys = set()
        for entry in self.entries.values():
            keys |= _key_variants(entry["name"])
        keys |= set(self._surname_keys())
        return keys

    def find_key(self, name):
        """The entry key a surface names, or None. Variants are
        tried in a fixed order (exact, article variants in
        sorted-key order, unique surname), so an ambiguous surface
        resolves the same way in every process."""
        variants = _key_variants(name)
        exact = normalize(name)
        if exact in self.entries:
            return exact
        for key in sorted(self.entries):
            if _key_variants(self.entries[key]["name"]) & variants:
                return key
        return self._surname_keys().get(exact)

    def get(self, name):
        key = self.find_key(name)
        return self.entries.get(key) if key else None

    # -- feeding ----------------------------------------------------------
    def feed(self, analysis, source, tick, wordnet=None):
        """Register one reading's entities.

        Returns {"met": [{"name", "count"}], "seen": [{"name"}],
        "learned": [{"name", "kind", "sources"}]} in passage order.
        Known entries met in the passage have their met_count
        incremented once per passage (not per token hit — a count is
        a count of readings, as in the notebook). Unknown phrases are
        tracked as candidates by distinct source; the sighting that
        reaches GROWTH_SOURCES distinct sources promotes the phrase,
        and that same reading then counts as its first met."""
        phrases = extract_phrases(analysis, self.match_keys(), wordnet)
        ordered = []
        seen_keys = set()
        for phrase in phrases:
            key = self.find_key(phrase["name"]) or normalize(phrase["name"])
            if key not in seen_keys:
                seen_keys.add(key)
                ordered.append((key, phrase["name"]))
        met, seen, learned = [], [], []
        for key, surface in ordered:
            entry = self.entries.get(key)
            if entry is None:
                cand = self.candidates.get(key)
                if cand is None:
                    cand = {"name": surface, "sources": [], "seen_count": 0}
                    self.candidates[key] = cand
                cand["seen_count"] += 1
                if source not in cand["sources"]:
                    cand["sources"] = sorted(cand["sources"] + [source])
                seen.append({"name": cand["name"]})
                if len(cand["sources"]) < GROWTH_SOURCES:
                    continue
                entry = {
                    "name": cand["name"],
                    "kind": "unknown",
                    "origin": "growth",
                    "sources": list(cand["sources"]),
                    "met_count": 0,
                }
                self.entries[key] = entry
                del self.candidates[key]
                learned.append(
                    {
                        "name": entry["name"],
                        "kind": entry["kind"],
                        "sources": list(entry["sources"]),
                    }
                )
            if source not in entry["sources"]:
                entry["sources"] = sorted(entry["sources"] + [source])
            entry["met_count"] += 1
            met.append({"name": entry["name"], "count": entry["met_count"]})
        return {"met": met, "seen": seen, "learned": learned}

    # -- persistence ------------------------------------------------------
    def to_dict(self):
        """The whole registry as plain JSON-shaped data, keyed in
        sorted order for a stable serialized form."""
        def row(e):
            return {
                "name": e["name"],
                "kind": e["kind"],
                "origin": e["origin"],
                "sources": sorted(e["sources"]),
                "met_count": int(e["met_count"]),
            }

        return {
            "version": 1,
            "entries": {k: row(self.entries[k]) for k in sorted(self.entries)},
            "candidates": {
                k: {
                    "name": c["name"],
                    "sources": sorted(c["sources"]),
                    "seen_count": int(c["seen_count"]),
                }
                for k, c in sorted(self.candidates.items())
            },
        }

    @classmethod
    def from_dict(cls, data):
        """Rebuild from to_dict() output; malformed rows are skipped
        rather than fatal, mirroring the notebook's loader. A
        registry with no valid seed rows is re-seeded only by the
        caller (from_dict itself never invents entries)."""
        gaz = cls()
        rows = (data or {}).get("entries") or {}
        if isinstance(rows, list):
            rows = {r.get("name", ""): r for r in rows if isinstance(r, dict)}
        for key, row in rows.items():
            try:
                name = row.get("name") or key
                if not any(c.isalpha() for c in str(name)):
                    continue  # punctuation cannot be an entity's name
                gaz.entries[normalize(name)] = {
                    "name": name,
                    "kind": row.get("kind", "unknown"),
                    "origin": row.get("origin", "world"),
                    "sources": sorted(row.get("sources") or []),
                    "met_count": int(row.get("met_count", 0)),
                }
            except (AttributeError, TypeError, ValueError):
                continue
        cands = (data or {}).get("candidates") or {}
        if isinstance(cands, list):
            cands = {r.get("name", ""): r for r in cands if isinstance(r, dict)}
        for key, row in cands.items():
            try:
                name = row.get("name") or key
                if not any(c.isalpha() for c in str(name)):
                    continue  # punctuation cannot be an entity's name
                gaz.candidates[normalize(name)] = {
                    "name": name,
                    "sources": sorted(row.get("sources") or []),
                    "seen_count": int(row.get("seen_count", 0)),
                }
            except (AttributeError, TypeError, ValueError):
                continue
        return gaz
