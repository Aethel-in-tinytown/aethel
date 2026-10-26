"""Lexical lenses: each council voice's way of seeing words (v0.36,
NLTK plan Phase 5).

A lens is DATA, not code that hides in the council: for each of the
nine voices this module names (a) a set of WordNet lexicographer
categories (lexnames — the files WordNet itself sorts its synsets
into, e.g. noun.feeling, verb.emotion) and (b) a small curated seed
lemma list in that voice's spirit. A text scores under a voice's lens
by a plain, documented measure over its DISTINCT content lemmas:

    hit weight  = SEED_HIT_WEIGHT    if the lemma is a seed lemma
                  LEXNAME_HIT_WEIGHT if the lemma's chosen synset
                                     (the notebook/recall rule: POS-
                                     filtered first match) lives in
                                     one of the voice's lexnames
                  0                  otherwise
    lens score  = sum(hit weights) / (SEED_HIT_WEIGHT * lemma count)

so a text made entirely of a voice's seed words scores 1.0, a text
made entirely of words from its categories scores 0.5, and a text
with nothing for the voice scores 0. Distinct lemmas, not token
counts: repeating "power power power" must not shout a lens awake,
because a lens is about what a text is ABOUT, not how loud it is.

Design choices, argued (the Kevin standard — docstrings argue):

PLAIN MEASURE, NOT IDF. Phase 2's recall already supplies rarity
weights where they belong (ranking her memories against each other).
The rejected alternative for lenses, reusing those IDF weights,
would make a voice's vote on the SAME impulse drift as her corpus
grows — the council's arithmetic would depend on how much she
happened to have read this month, and a golden deliberation would
need a golden corpus to mean anything. A lens score here is a pure
function of (the text, pinned WordNet, this table): same text, same
score, in any life, after any restart. Her history enters the
deliberation through case law (the precedent citation), which is
journaled; it does not also sneak in through the lens weights.

AMPLIFY ONLY. The council factor is 1 + LENS_WEIGHT_SCALE * score,
capped at LENS_MAX_FACTOR (1.25). A voice is never DISCOUNTED for a
text outside its lens: irrelevance is already handled by the
council's abstention rule (a voice with no axiom in the text does
not vote at all), and discounting non-firing voters on top of that
would double-count absence and let a strong lens firing silently
outvote voices that did speak. Amplification is relative anyway —
the weighted mean divides by the sum of effective weights — so a
firing voice gains exactly by standing taller among the voters.

SEEDS OVERLAP ON PURPOSE. 'harm' is a Care seed and a Utilitarian
seed; 'fate' belongs to the Stoic and to Nietzsche. The voices are
not a partition of the dictionary, they are nine readers of the
same world, and honest overlap in what they notice is what makes
their disagreements interesting. The fixtures in the tests use
texts where the voices' centers of gravity differ, which is the
claim the data actually makes.

VALIDATION IS PART OF THE DATA. Every seed lemma must exist in
WordNet and every lexname must be one the provisioned WordNet
actually uses; validate_lens_data() checks both against the reader
it is handed, and the test suite asserts it returns no problems.
A typo'd seed that silently never fired would be a voice quietly
lobotomized, so the data proves itself on every test run.

FAIL-CLOSED / HEURISTIC GATE. This module is only ever called by
the organism in NLTK mode (its `_nlp` gate), with the backend's
pinned WordNet reader. With no reader, lens_scores returns {} —
absence is data, never a substitute algorithm.
"""

from . import grammar
from .config import AXIOMS
from .notebook import wn_pos

#: Closed-class words a lens does not see. Deliberately NOT the
#: config STOPWORDS list: that list is frequency-based (it exists to
#: keep common words out of her concept counts) and it contains
#: exactly the thematic words a lens exists to notice — mother,
#: family, know, learn, will, many are all "stopwords" there, and a
#: lens that inherited that filter would have dead seeds baked into
#: its data. A lens's stopwords are grammatical, not frequent:
#: articles, prepositions, conjunctions, pronouns, auxiliaries.
#: ('will' is absent on purpose: as a noun it is Nietzsche's seed,
#: and the auxiliary reading is acceptable noise at these weights.)
FUNCTION_WORDS = frozenset(
    "the a an and or but if then else of to in on at by for with from "
    "as is are was were be been being it its this that these those i "
    "you he she we they him her them his hers their our your my me us "
    "not no do does did have has had would shall should may might "
    "must there here when where who whom what which while than so "
    "such into over under again once".split()
)

#: Hit weights (see module docstring). A seed lemma is a word the
#: voice is DEFINED by; a lexname hit is a word in its territory.
SEED_HIT_WEIGHT = 2.0
LEXNAME_HIT_WEIGHT = 1.0

#: The council multiplier: factor = 1 + SCALE * lens_score, hard
#: capped at MAX_FACTOR. 0.25 is the plan's bounded shift: a voice
#: whose lens fires at full strength weighs a quarter more than it
#: otherwise would — enough to break the council's old habit of
#: near-identical verdicts on differently-textured texts, far too
#: little to let vocabulary alone overturn a voice's actual vote
#: (votes move in 0.12/0.30 axiom steps; a 25% weight shift on one
#: voice of several moves the mean by hundredths).
LENS_WEIGHT_SCALE = 0.25
LENS_MAX_FACTOR = 1.0 + LENS_WEIGHT_SCALE

#: At or above this lens score the firing is material: the voice's
#: deliberation note gains a citation of its top lens lemmas. Below
#: it the factor still applies (it is small) but the note stays
#: clean — a diary that annotates every whisper annotates nothing.
LENS_MATERIAL_SCORE = 0.25

#: How many lemmas a material citation names.
LENS_CITATION_LEMMAS = 3


LENSES = {
    "Stoicism (Aurelius)": {
        # Fate arrives as events and states; endurance is stative.
        "lexnames": ("noun.event", "noun.state", "verb.stative", "verb.cognition"),
        "seeds": (
            "fate",
            "destiny",
            "fortune",
            "endure",
            "suffer",
            "accept",
            "duty",
            "discipline",
            "reason",
            "calm",
            "bear",
            "patience",
        ),
        "rationale": "Fate and endurance: what arrives, and bearing it.",
    },
    "Utilitarianism (Mill)": {
        # Consequences are acts and feelings, weighed over groups.
        "lexnames": ("noun.act", "noun.feeling", "noun.group", "verb.social"),
        "seeds": (
            "benefit",
            "welfare",
            "happiness",
            "pleasure",
            "suffering",
            "harm",
            "help",
            "share",
            "greatest",
            "outcome",
            "many",
        ),
        "rationale": "Benefit and harm, summed over the many.",
    },
    "Ethics of Care (Gilligan)": {
        # Persons first, their feelings, and the social/emotional
        # verbs that bind or break them.
        "lexnames": ("noun.person", "noun.feeling", "verb.social", "verb.emotion"),
        "seeds": (
            "mother",
            "father",
            "family",
            "kin",
            "child",
            "care",
            "nurture",
            "protect",
            "harm",
            "hurt",
            "abandon",
            "neglect",
            "trust",
            "listen",
            "relationship",
        ),
        "rationale": "Kinship, nurture, and the harm of abandonment.",
    },
    "Cynicism (Diogenes)": {
        # Animals (the Dog), attributes like wealth, plain things.
        "lexnames": ("noun.animal", "noun.attribute", "noun.state"),
        "seeds": (
            "simple",
            "nature",
            "honest",
            "free",
            "enough",
            "luxury",
            "status",
            "wealth",
            "pretend",
            "shameless",
            "dog",
            "hunger",
        ),
        "rationale": "Nature and enough, against luxury and status.",
    },
    "Platonism (Plato)": {
        # Cognition and attributes: forms are known, not touched.
        "lexnames": ("noun.cognition", "noun.attribute", "noun.state"),
        "seeds": (
            "truth",
            "reason",
            "justice",
            "harmony",
            "wisdom",
            "order",
            "form",
            "soul",
            "idea",
            "shadow",
            "appearance",
        ),
        "rationale": "Truth and form, against shadow and appearance.",
    },
    "Socratic (Socrates)": {
        # Questions are communication; examining is cognition.
        "lexnames": (
            "verb.cognition",
            "verb.communication",
            "noun.cognition",
            "noun.communication",
        ),
        "seeds": (
            "question",
            "examine",
            "know",
            "knowledge",
            "virtue",
            "honest",
            "learn",
            "wisdom",
            "ignorance",
            "assume",
        ),
        "rationale": "Examine and question; ignorance named is progress.",
    },
    "Nietzschean (Nietzsche)": {
        # Creation and change; motives are where ressentiment hides.
        "lexnames": ("verb.creation", "verb.change", "noun.attribute", "noun.motive"),
        "seeds": (
            "overcome",
            "create",
            "strong",
            "strength",
            "fate",
            "will",
            "become",
            "resent",
            "pity",
            "herd",
            "guilt",
            "noble",
        ),
        "rationale": "Overcoming and becoming, against pity and the herd.",
    },
    "Machiavellian (Machiavelli)": {
        # Competition and social maneuver, planned in cognition.
        "lexnames": ("noun.cognition", "verb.social", "verb.competition", "noun.act"),
        "seeds": (
            "power",
            "advantage",
            "control",
            "rule",
            "strategy",
            "prudence",
            "bold",
            "secure",
            "effective",
            "foresight",
            "deceive",
            "fear",
        ),
        "rationale": "Power and advantage, prudently secured.",
    },
    "Gandhian (Gandhi)": {
        # Acts and feelings in the social world, without violence.
        "lexnames": ("noun.act", "noun.feeling", "verb.social", "noun.attribute"),
        "seeds": (
            "nonviolence",
            "truth",
            "serve",
            "humble",
            "patient",
            "peace",
            "violence",
            "hate",
            "revenge",
            "suffering",
            "love",
            "forgiveness",
        ),
        "rationale": "Nonviolence and service; violence and revenge named to be refused.",
    },
}


def available_lexnames(wordnet):
    """The lexnames the handed WordNet actually uses. Prefers the
    reader's own inventory when it exposes one; otherwise derives
    the set from its synsets (slower, still pure)."""
    inv = getattr(wordnet, "_lexnames", None)
    if inv:
        return set(inv)
    return {s.lexname() for s in wordnet.all_synsets()}


def validate_lens_data(wordnet):
    """Problems with LENSES against a real WordNet reader, as a list
    of strings (empty = the data is sound): one entry per voice —
    the table covers exactly the council's voices — every lexname
    provisioned, every seed lemma present in WordNet."""
    problems = []
    if set(LENSES) != set(AXIOMS):
        problems.append(
            f"lens voices {sorted(LENSES)} != council voices {sorted(AXIOMS)}"
        )
    if wordnet is None:
        problems.append("no WordNet reader")
        return problems
    known = available_lexnames(wordnet)
    for voice, lens in LENSES.items():
        for lexname in lens["lexnames"]:
            if lexname not in known:
                problems.append(f"{voice}: lexname {lexname} not in WordNet")
        for seed in lens["seeds"]:
            if not wordnet.synsets(seed):
                problems.append(f"{voice}: seed lemma {seed!r} not in WordNet")
            if seed in FUNCTION_WORDS:
                problems.append(
                    f"{voice}: seed lemma {seed!r} is a lens function word "
                    "and could never fire"
                )
    return problems


def _content_lemmas(language, text):
    """lemma -> POS tag of first occurrence, over the lens's own
    view of a text: alphabetic tokens minus FUNCTION_WORDS and page
    scaffolding (see the FUNCTION_WORDS note for why this view is
    wider than the backend's acquisition predicate)."""
    analysis = language.analyze(text)
    out = {}
    for token in analysis.tokens:
        if not token.text.isalpha() or len(token.text) < 2:
            continue
        if token.text.lower() in FUNCTION_WORDS or token.lemma in FUNCTION_WORDS:
            continue
        if token.lemma in grammar.SCAFFOLDING_WORDS:
            continue
        if token.lemma not in out:
            out[token.lemma] = token.pos
    return out


def _chosen_lexname(wordnet, lemma, pos_tag):
    """The lexname of a lemma's chosen synset, by the one synset
    rule she has (POS-filtered first match, first-synset fallback —
    see notebook.choose_synset). None when unknown to WordNet."""
    synsets = wordnet.synsets(lemma, pos=wn_pos(pos_tag))
    if not synsets:
        synsets = wordnet.synsets(lemma)
    return synsets[0].lexname() if synsets else None


def lens_scores(language, text):
    """Per-voice lens results for one text:
    {voice: {"score": float, "top_lemmas": [lemma, ...]}}.

    Pure function of the text and the pinned WordNet behind
    `language`. Returns {} when the backend carries no WordNet
    reader (heuristic mode never calls this; see module docstring).
    """
    wordnet = getattr(language, "wordnet", None)
    if wordnet is None or not text:
        return {}
    lemmas = _content_lemmas(language, text)
    if not lemmas:
        return {voice: {"score": 0.0, "top_lemmas": []} for voice in LENSES}
    results = {}
    for voice, lens in LENSES.items():
        seeds = set(lens["seeds"])
        lexnames = set(lens["lexnames"])
        hits = []  # (weight, lemma)
        for lemma, pos_tag in lemmas.items():
            if lemma in seeds:
                hits.append((SEED_HIT_WEIGHT, lemma))
            elif _chosen_lexname(wordnet, lemma, pos_tag) in lexnames:
                hits.append((LEXNAME_HIT_WEIGHT, lemma))
        total = sum(w for w, _ in hits)
        score = total / (SEED_HIT_WEIGHT * len(lemmas)) if lemmas else 0.0
        top = [
            lemma
            for _, lemma in sorted(hits, key=lambda h: (-h[0], h[1]))[
                :LENS_CITATION_LEMMAS
            ]
        ]
        results[voice] = {"score": round(score, 6), "top_lemmas": top}
    return results


def lens_factor(score):
    """The bounded council multiplier for one lens score: amplify
    only, hard-capped at LENS_MAX_FACTOR (see module docstring)."""
    return min(1.0 + LENS_WEIGHT_SCALE * score, LENS_MAX_FACTOR)


def lens_citation(result):
    """The deterministic note fragment for a material firing:
    'lens mother, harm (+20%)' — the top lemmas and the exact
    percentage the voice's weight grew by."""
    pct = lens_factor(result["score"]) - 1.0
    return f"lens {', '.join(result['top_lemmas'])} (+{pct:.0%})"
