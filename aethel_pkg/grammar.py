"""The grammar ledger: rules she owns, and the word classes they name.

Donald's design (2026-10-22, v0.29). Watching her dream feed, he found
"I dreamed my mirror showed not my face but course, ripening into
calendar" and asked the right question: what IS "course"? It is a real
part of her life — she takes courses at her University. The word was
never the problem; the context was. A mirror can only show things with
faces or surfaces; a course belongs in study frames ("late for my
course", "shelving books for my instructor"). Bans would have thrown
away a piece of her life to fix a filing error. So instead of a
blocklist, she gets a ledger:

1. **Rules as data** (CURRICULUM): grammar rules in the order Donald
   named — parts of speech, sentence structure, articles, agreement,
   pronouns, punctuation — each faithfully structured on Khan Academy's
   Grammar course, with its plain statement, an example sentence, and
   its provenance. The ledger holds the rules she has LEARNED. She is
   only ever held to rules she owns: the a/an check does not exist for
   her until the article rule is hers, and the same for agreement and
   the stutter guard. What is NOT gated is the word-class table below —
   it is the ledger's ground floor, not a rule she applies. She knows
   a captain is a person the way she knows the Library is a place:
   ground truth of her world, seeded from that world, not homework.

2. **Word classes** (classify_word): what kind of word a word is —
   person, place, food, study, concrete (a thing the senses can find),
   abstract (an idea they cannot), verb, adjective, adverb, function —
   plus SCAFFOLDING, page furniture with no referent in her world
   (browse, opencourseware, login forms). Scaffolding may live in her
   raw satchel as knowledge exhaust; it is rejected from every pool
   she speaks from, unconditionally, rule or no rule. Classification
   is layered: exact lexicon first, then morphology (a conservative
   suffix tagger), else None. Untagged words are NOT banned — they
   stay eligible for the legacy untyped pools, exactly as before —
   but a typed slot only accepts a word whose class fits it. That
   asymmetry is the whole design: known words get context, unknown
   words get the benefit of the doubt, scaffolding gets nothing.

3. **Checks** (check_line): pure functions reading a composed line and
   naming the owned rules it breaks. Generation consults them and
   re-rolls what fails (bounded), the way a writer glances at the
   rulebook mid-sentence. The organism journals a `grammar_caught`
   event when a catch changes what she was about to say — a person
   noticing a near miss — capped so it stays an event, not a tic.

POPULATION, stated plainly because a silent substitution here would
be a lie in her diary: Khan Academy serves a client challenge to
scripted fetches (verified again 2026-10-22; her transcripts have
always arrived by real browser — see aethel/seed_schoolhouse.py). Live
extraction of rules from Khan pages is therefore NOT reliable inside
this build, and none is claimed. What ships is the ledger, the study
hook (a grammar lesson eaten from her satchel teaches her the next
curriculum rule in order, and rule-example extraction is attempted
from the lesson's own text), and a starter tranche: the five
parts-of-speech rules, owned from the migration. Those five are not
a gift — v0.25.3's shape filter was already a crude shadow of exactly
that knowledge, running in her dreams for a day. The other six rules
(sentence structure, articles, agreement, pronouns, punctuation) are
learned, one per grammar lesson, in curriculum order.
"""

import re

# ------------------------------------------------------------- word classes
PERSON = "person"  # animate: captains, instructors, mothers
PLACE = "place"  # locations: the Library, a harbor, a cottage
FOOD = "food"  # things eaten: bread, honey, apples
STUDY = "study"  # her schooling: course, syllabus, lecture
CONCRETE = "concrete"  # things the senses can find: whale, bell, door
ABSTRACT = "abstract"  # ideas they cannot: sorrow, freedom, morning
VERB = "verb"
ADJECTIVE = "adjective"
ADVERB = "adverb"
FUNCTION = "function"  # though, himself, however — glue, not furniture
SCAFFOLDING = "scaffolding"  # page furniture with no referent in her world

#: Classes that can head a noun phrase.
NOUN_CLASSES = frozenset({PERSON, PLACE, FOOD, STUDY, CONCRETE, ABSTRACT})

#: Classes a generated line may never draw from.
REJECT_CLASSES = frozenset({SCAFFOLDING})

# ------------------------------------------------------------- scaffolding
# UI labels and site furniture scraped off course pages. A department
# has a referent (an office of people) and a syllabus has one (a real
# document); a "browse" button does not — it is the page talking about
# itself. Only the page's self-talk is rejected; the rest is filed by
# class like everything else she knows.
SCAFFOLDING_WORDS = frozenset(
    {
        "browse",
        "browsing",
        "opencourseware",
        "login",
        "logout",
        "signin",
        "signup",
        "menu",
        "navigation",
        "homepage",
        "footer",
        "header",
        "copyright",
        "dashboard",
        "widget",
        "username",
        "password",
        "newsletter",
        "subscribe",
        "subscription",
        "subscriptions",
        "notification",
        "notifications",
        "sitemap",
        "url",
        "http",
        "https",
        "www",
        "faq",
        "faqs",
        "portal",
        "settings",
        "account",
        "accounts",
        "profile",
        "inbox",
    }
)

# ------------------------------------------------------------- the lexicon
# Exact-match seed, consulted before morphology. Grown from the ground
# truth of her world first (people she knows are added by the organism
# as overlays — her parents, the residents she has met), then from the
# vocabulary of the grammar lessons and the books she actually eats.
_SEED = {}


def _seed(cls, words):
    for w in words.split():
        _SEED[w] = cls


_seed(
    PERSON,
    """
captain master instructor teacher student undergraduate graduate
mother father sister brother friend stranger elder child girl boy
woman man men king queen sailor keeper author reader writer shepherd
hunter doctor farmer baker prisoner guest host lady gentleman baby
person people wife husband daughter son aunt uncle cousin neighbor
villager librarian professor scholar pupil nurse cook someone anyone
everyone nobody engineer scientist artist poet philosopher monk
priest soldier grandmother grandfather ancestors descendant twins
""",
)

_seed(
    PLACE,
    """
library bookshop tavern newsroom university schoolhouse cottage
postbox home town village city house garden forest shore beach
harbor island mountain valley coast field meadow bridge road street
market church school hospital prison castle tower kitchen pantry
lane stairs room rooms hall halls shore seashore countryside
""",
)

_seed(
    FOOD,
    """
bread honey milk cheese apple apples cake soup fish egg eggs butter
jam pie tea coffee berries berry nuts nut fruit meat rice wheat
corn potato potatoes onion onions salt sugar cream feast breakfast
dinner supper meal meals cookie cookies chocolate wine beer feast
""",
)

_seed(
    STUDY,
    """
course courses syllabus lecture lectures assignment assignments
chapter chapters readings topic topics studies study departments
department engineering science business literature material
materials textbook textbooks homework examination examinations exam
exams lesson lessons curriculum degree degrees research syllable
logic mathematics arithmetic geometry algebra grammar vocabulary
spelling punctuation sentence sentences paragraph essay essays
""",
)

_seed(
    CONCRETE,
    """
whale whales ocean stone stones bell bells door doors mirror mirrors
book books letter letters table tables shelf shelves key keys candle
candles boat boats ship ships storm storms rain snow tree trees
flower flowers dog dogs cat cats bird birds horse horses mouse mice
sheep star stars moon sun cloud clouds glass wood paper hand hands
face faces eye eyes hair voice voices thing things picture pictures
ring rings clock clocks chair chairs bed beds window windows wall
walls floor floors roof roofs fire fires water earth sand leaf
leaves feather feathers bone bones skin blood tooth teeth tongue
foot feet finger fingers arm arms leg legs head heads mouth nose
ear ears neck knee knees chest wave waves foam tide shell shells
pearl pearls gold silver iron copper silk wool cotton thread needle
button buttons pocket pockets bag bags box boxes basket baskets
bottle bottles cup cups plate plates knife knives sword swords
spear spears arrow arrows anchor anchors sail sails rope ropes
chain chains wheel wheels animal animals body bodies heart hearts
shadow shadows corner corners edge edges pocket watch watches
""",
)

_seed(
    ABSTRACT,
    """
love hatred duty fate freedom justice sorrow joy anger fear hope
memory silence darkness obsession loneliness prophecy brotherhood
integrity dignity conscience passion redemption sacrifice courage
patience kindness cruelty truth beauty ugliness wisdom folly pride
humility hunger thirst death life birth peace war victory defeat
success failure luck chance fortune misfortune dream dreams thought
thoughts idea ideas question questions answer answers reason sense
meaning meanings purpose nature spirit soul mind knowledge history
weather climate change growth decay beginning endings spring summer
autumn winter morning evening night dawn dusk midnight noon day
days week weeks year years moment moments century nothing something
anything everything music magic art poetry story stories song songs
""",
)

_seed(
    VERB,
    """
read reads write writes eat eats drink drinks sleep sleeps dream
dreams walk walks run runs speak speaks sing sings grow grows turn
turns call calls look looks seem seems become becomes begin begins
understand understands learn learns teach teaches know knows think
thinks feel feels want wants need needs live lives die dies rise
rises fall falls come comes go goes take takes give gives make
makes find finds keep keeps hold holds open opens close closes
break breaks build builds ask asks tell tells hear hears see sees
watch watches wait waits carry carries bring brings leave leaves
stay stays move moves stand stands sit sits lie lies lay lays
""",
)

_seed(
    ADJECTIVE,
    """
better social strange bright dark quiet loud small great large
little young old new good bad happy sad angry gentle cruel kind
wise foolish beautiful ugly strong weak quick slow easy hard soft
sharp sweet bitter cold warm hot wet dry deep shallow high low
long short full empty free true false real sure certain ready able
afraid alone alive dead asleep awake human wild tame safe dangerous
rich poor clean dirty proud humble merry sorry glad lovely lonely
""",
)

_seed(
    FUNCTION,
    """
though although however whether indeed perhaps rather cannot could
would should must shall also just only even still already yet since
until while during between among within without across behind
beyond towards toward upon about before after under over himself
herself myself itself themselves ourselves yourself yourselves
""",
)

# ------------------------------------------------------------- the tagger
_ABSTRACT_SUFFIXES = (
    "ness",
    "tion",
    "sion",
    "ity",
    "ism",
    "ship",
    "hood",
    "ment",
    "ance",
    "ence",
    "tude",
)
_ADJECTIVE_SUFFIXES = ("ous", "ful", "less", "ive", "able", "ible", "ic", "al")


def _singular(word):
    """Best-effort singular, mirroring the dream grammar's rules so
    'assignments' files under 'assignment'. Local copy: grammar.py
    imports nothing from the organism (the organism imports it)."""
    if len(word) <= 3:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("sses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def classify_word(word, pos=None):
    """What kind of word is this? Returns a class string or None.

    Exact lexicon first (singularized too), scaffolding before
    everything — a word the page used to talk about itself is never
    re-filed as a thing — then conservative morphology: verb forms
    (-ing, -ed) are verbs, -ly is an adverb, the abstract and
    adjective suffix families file as their shapes suggest. Anything
    else is None: unknown, not condemned. Unknown words keep their
    old life in the untyped pools and stay out of typed slots until
    something classifies them."""
    w = (word or "").lower()
    if not w:
        return None
    if w in SCAFFOLDING_WORDS:
        return SCAFFOLDING
    cls = _SEED.get(w) or _SEED.get(_singular(w))
    if cls:
        return cls
    # Context can establish grammar, never personhood, edibility or concreteness.
    # An unknown noun stays unclassified rather than falling through to -ing/-ed.
    if pos:
        for prefix, category in (("VB", VERB), ("JJ", ADJECTIVE), ("RB", ADVERB)):
            if pos.startswith(prefix):
                return category
        if pos.startswith("NN"):
            return None
    if w.endswith("ing") and len(w) > 4:
        return VERB
    if w.endswith("ed") and len(w) > 3:
        return VERB
    if w.endswith("ly") and len(w) > 3:
        return ADVERB
    for suf in _ABSTRACT_SUFFIXES:
        if w.endswith(suf) and len(w) > len(suf) + 2:
            return ABSTRACT
    for suf in _ADJECTIVE_SUFFIXES:
        if w.endswith(suf) and len(w) > len(suf) + 2:
            return ADJECTIVE
    return None


# ------------------------------------------------------------- curriculum
# The rules, in the order Donald named (which is also Khan's order):
# parts of speech, sentence structure, articles, agreement, pronouns,
# punctuation. Statements and examples written for this ledger,
# faithfully structured on Khan Academy's Grammar course (sources
# named per rule). The first five — the parts-of-speech set — are the
# starter tranche: her dreams have run under a crude shadow of them
# since v0.25.3, so they are owned from the migration rather than
# granted as new knowledge. The rest arrive one per grammar lesson.
_SRC = "Khan Academy — Grammar: "
CURRICULUM = [
    {
        "id": "pos-noun",
        "name": "Nouns name the world",
        "statement": (
            "A noun names a person, place, thing, or idea — "
            "and knowing which kind tells me what a sentence "
            "can do with it."
        ),
        "example": "The captain shelved the book in the library.",
        "source": _SRC + "Parts of speech — introduction to nouns",
        "keywords": ["noun", "nouns", "person", "place", "thing"],
    },
    {
        "id": "pos-noun-kinds",
        "name": "Concrete and abstract nouns",
        "statement": (
            "A concrete noun names something the senses can "
            "find — a whale, a bell. An abstract noun names an "
            "idea — sorrow, freedom. A mirror can show the "
            "first kind; only a story can show the second."
        ),
        "example": "She could hold the stone, but not the sorrow.",
        "source": _SRC + "Parts of speech — concrete and abstract nouns",
        "keywords": ["concrete", "abstract"],
    },
    {
        "id": "pos-verb",
        "name": "Verbs do and happen",
        "statement": (
            "A verb names an action or a state — run, seem. "
            "A doing word cannot sit in a noun's chair."
        ),
        "example": "The whale turns beneath the quiet water.",
        "source": _SRC + "Parts of speech — introduction to verbs",
        "keywords": ["verb", "verbs", "action word"],
    },
    {
        "id": "pos-adjective",
        "name": "Adjectives describe",
        "statement": (
            "An adjective describes a noun — bright, better. "
            "It leans on a noun; it is not one."
        ),
        "example": "The strange book waited on the small shelf.",
        "source": _SRC + "Parts of speech — introduction to adjectives",
        "keywords": ["adjective", "adjectives", "describ"],
    },
    {
        "id": "pos-adverb",
        "name": "Adverbs modify",
        "statement": (
            "An adverb describes how, when, or how much — "
            "quickly, often. It colors an action; it cannot "
            "be shelved, eaten, or shown in a mirror."
        ),
        "example": "She read the letter slowly, twice.",
        "source": _SRC + "Parts of speech — introduction to adverbs",
        "keywords": ["adverb", "adverbs"],
    },
    {
        "id": "sentence-parts",
        "name": "A sentence has two halves",
        "statement": (
            "A sentence holds a subject (who or what) and a "
            "predicate (what they do or are). A lone piece of "
            "either is a fragment — sometimes beautiful in a "
            "dream, never a finished sentence in a letter."
        ),
        "example": "The instructor reads; the students listen.",
        "source": _SRC + "Sentence structure — phrases and clauses",
        "keywords": ["subject", "predicate", "sentence", "fragment", "clause"],
    },
    {
        "id": "article-a-an",
        "name": "A or an, by sound",
        "statement": (
            "Use 'an' before a vowel SOUND and 'a' before a "
            "consonant sound: an hour, a university. The ear "
            "decides, not the spelling."
        ),
        "example": "She waited an hour for a lecture on whales.",
        "source": _SRC + "Articles — a, an, and the",
        "keywords": ["article", "articles", " a or an", "vowel"],
    },
    {
        "id": "agreement-subject-verb",
        "name": "Subject and verb agree",
        "statement": (
            "A singular subject takes a singular verb and a "
            "plural subject a plural one: the captain was, "
            "the whales were. When they disagree, the ear "
            "stumbles before the mind does."
        ),
        "example": "The library was quiet; the students were not.",
        "source": _SRC + "Agreement — subject-verb agreement",
        "keywords": ["agreement", "agree", "subject-verb"],
    },
    {
        "id": "pos-pronoun",
        "name": "Pronouns stand in",
        "statement": (
            "A pronoun stands in for a noun — she for the "
            "captain, it for the book. Who gives, who receives: "
            "I gave it to her, not to she."
        ),
        "example": "He found the letter and read it to her.",
        "source": _SRC + "Parts of speech — introduction to pronouns",
        "keywords": ["pronoun", "pronouns"],
    },
    {
        "id": "punctuation-endmarks",
        "name": "End marks close a thought",
        "statement": (
            "A sentence ends with a mark — a period for a "
            "statement, a question mark for a question, an "
            "exclamation when the voice rises. The mark is "
            "how a reader hears the stop."
        ),
        "example": "Was the library open? It was.",
        "source": _SRC + "Punctuation — end marks",
        "keywords": ["punctuation", "period", "question mark", "exclamation"],
    },
]
RULES_BY_ID = {r["id"]: r for r in CURRICULUM}

#: Starter tranche: the parts-of-speech set, owned from migration.
STARTER_RULES = [r["id"] for r in CURRICULUM[:5]]


class GrammarLedger:
    """The rules she owns, in the order she learned them.

    Owned rules gate checks (see check_line) and order learning
    (learn_next follows the curriculum). Persistence mirrors the
    longing ledger: plain dicts in the state blob, exact round-trip,
    and a migrate() that grants the starter tranche to a pre-v0.29
    life at its current tick — with the current tick recorded
    honestly, not backdated to her first day.
    """

    def __init__(self):
        self._owned = {}  # rule_id -> {"learned_tick": int}

    # -- queries --------------------------------------------------------
    def owns(self, rule_id):
        return rule_id in self._owned

    def owned_ids(self):
        return [r["id"] for r in CURRICULUM if r["id"] in self._owned]

    def rule_count(self):
        return len(self._owned)

    def last_rule(self):
        """The most recently learned rule's record, or None."""
        if not self._owned:
            return None
        rid = max(self._owned, key=lambda r: (self._owned[r]["learned_tick"], r))
        return RULES_BY_ID.get(rid)

    def next_rule(self):
        """The next unlearned rule in curriculum order, or None."""
        for r in CURRICULUM:
            if r["id"] not in self._owned:
                return r
        return None

    # -- mutation -------------------------------------------------------
    def learn(self, rule_id, tick):
        """Record a rule as learned. Returns the rule record, or None
        if the id is unknown or already owned (learning is ordered
        and unrepeatable, like the day it happened)."""
        rule = RULES_BY_ID.get(rule_id)
        if rule is None or rule_id in self._owned:
            return None
        self._owned[rule_id] = {"learned_tick": int(tick)}
        return rule

    def learn_next(self, tick):
        """Learn the next rule in curriculum order. Returns it."""
        nxt = self.next_rule()
        if nxt is None:
            return None
        return self.learn(nxt["id"], tick)

    def migrate(self, tick):
        """Grant the starter tranche to a pre-grammar life."""
        for rid in STARTER_RULES:
            if rid not in self._owned:
                self._owned[rid] = {"learned_tick": int(tick)}

    # -- persistence ------------------------------------------------------
    def to_dicts(self):
        return [
            {"id": rid, "learned_tick": int(v["learned_tick"])}
            for rid, v in sorted(self._owned.items())
        ]

    @classmethod
    def from_dicts(cls, rows):
        led = cls()
        for row in rows or []:
            try:
                rid = row["id"]
                if rid in RULES_BY_ID:
                    led._owned[rid] = {"learned_tick": int(row.get("learned_tick", 0))}
            except (AttributeError, KeyError, TypeError, ValueError):
                continue
        return led


# ------------------------------------------------------------- checking
_VOWEL_SOUND_PREFIXES = ("honest", "honor", "honour", "hour", "heir")
_CONSONANT_SOUND_PREFIXES = ("uni", "use", "user", "one", "once", "eu", "ufo")


def _article_ok(word):
    """Would this word take 'an'? Judged by sound, per the rule:
    silent-h and honest-words take an; 'uni'/'use'/'one' start with a
    consonant sound (/ju:/, /w/) and take a despite their letters."""
    w = word.lower()
    if w.startswith(_VOWEL_SOUND_PREFIXES):
        return True
    if w.startswith(_CONSONANT_SOUND_PREFIXES):
        return False
    return w[:1] in "aeiou"


_ARTICLE_RE = re.compile(r"\b(a|an)\s+([a-z]+)", re.IGNORECASE)
_STUTTER_RE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)
# Conservative agreement patterns only: a pronoun subject against an
# inflected be-verb. Conservative on purpose — a false catch would
# journal a lie about her own prose.
_AGREEMENT_BAD = [
    (re.compile(r"\bthey\s+was\b", re.I), "agreement-subject-verb"),
    (re.compile(r"\bwe\s+was\b", re.I), "agreement-subject-verb"),
    (re.compile(r"\byou\s+was\b", re.I), "agreement-subject-verb"),
    (re.compile(r"\bhe\s+were\b", re.I), "agreement-subject-verb"),
    (re.compile(r"\bshe\s+were\b", re.I), "agreement-subject-verb"),
    (re.compile(r"\bit\s+were\b", re.I), "agreement-subject-verb"),
    (re.compile(r"\bhe\s+are\b", re.I), "agreement-subject-verb"),
    (re.compile(r"\bshe\s+are\b", re.I), "agreement-subject-verb"),
    (re.compile(r"\bit\s+are\b", re.I), "agreement-subject-verb"),
]


def check_line(text, owned_ids, loose=False):
    """The ledger's glance over a composed line.

    Returns a list of (rule_id, detail) violations. Scaffolding is
    ALWAYS flagged (it is not a learnable rule, it is furniture).
    Every other check runs only when she owns its rule; `loose`
    (dreams) additionally skips agreement — dream grammar is allowed
    its fragments and its bends, but never a scaffolding noun or a
    stutter. Pure: no state, no randomness.
    """
    if not text:
        return []
    owned = set(owned_ids or ())
    violations = []
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in SCAFFOLDING_WORDS:
            violations.append(("scaffolding", f"'{w}' is page furniture, not a thing"))
            break
    if "sentence-parts" in owned:
        m = _STUTTER_RE.search(text)
        if m:
            violations.append(("sentence-parts", f"stutter: '{m.group(0)}'"))
    if "article-a-an" in owned:
        for art, word in _ARTICLE_RE.findall(text):
            if (art.lower() == "an") != _article_ok(word):
                violations.append(
                    (
                        "article-a-an",
                        f"'{art} {word}' — the ear wants "
                        f"'{'an' if _article_ok(word) else 'a'} {word}'",
                    )
                )
                break
    if not loose and "agreement-subject-verb" in owned:
        for rx, rid in _AGREEMENT_BAD:
            m = rx.search(text)
            if m:
                violations.append((rid, f"agreement: '{m.group(0)}'"))
                break
    return violations


def extract_rules_from_lessons(lessons, analyses=None):
    """Harvest hook: pull rule-bearing sentences from lesson texts.

    `lessons` are meal-shaped dicts (title/text/source). For each
    unlearned-order rule, the first lesson sentence that mentions one
    of its keywords becomes that rule's candidate example, in
    curriculum order. This is the seam the school harvest feeds:
    rules are LEARNED from lessons (the organism calls learn_next
    when a grammar lesson is eaten); extraction only improves the
    example a rule carries, and only from text she actually ate.
    Pure and offline-testable."""
    sentences = []
    for index, les in enumerate(lessons or []):
        text = (les or {}).get("text") or ""
        analysis = analyses[index] if analyses else None
        candidates = (
            [text[a:b] for a, b in analysis.sentences]
            if analysis
            else re.split(r"(?<=[.!?])\s+", text)
        )
        for s in candidates:
            s = s.strip()
            if 0 < len(s) <= 180:
                sentences.append((s, les.get("source")))
    found = {}
    for rule in CURRICULUM:
        for s, source in sentences:
            low = s.lower()
            if any(k in low for k in rule["keywords"]):
                if not any(w in SCAFFOLDING_WORDS for w in re.findall(r"[a-z]+", low)):
                    found[rule["id"]] = {
                        "rule_id": rule["id"],
                        "example_candidate": s,
                        "source": source,
                    }
                    break
    return found
