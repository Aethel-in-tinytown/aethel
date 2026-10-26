"""v0.36: council case law + lexical lenses (NLTK plan Phase 5).

Pins, in order: lens DATA validation against the provisioned
WordNet (every seed lemma and every lexname exists); lens
determinism and voice-distinct firing on crafted fixtures (kinship/
harm fires Care over Machiavelli, power/advantage the reverse, fate/
endurance fires Stoicism); the bounded multiplier and its documented
composition with temperament weights (temperament base x lens,
abstainers untouched); golden deliberations — fixed impulses with a
fixed corpus produce pinned (score, notes) including the precedent
citation and the lens effect; case law is CITATION-ONLY, including
inside the tie band (precedent outcomes are not cleanly recoverable
from the journal — book beliefs are appended pass or fail — so a
near tie is flagged 'cited not pushed' and the score is exactly the
lens-only score); the council_precedent journal event's shape; the
heuristic hard gate (lenses/recall never invoked, _council_score
byte-identical to the pre-Phase-5 calls, temperament included); and
the seeded NLTK restart-fidelity life with Phase 5 active.

Isolation: in-memory stores via set_store and a temp AETHEL_HOME for
every organism built here — her live diary is never instantiated
against. Unit tests run on a fake WordNet/language; golden and
fidelity tests use the real backend and skip when unprovisioned.
"""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aethel_pkg.organism as org_mod
from aethel_pkg import config, lenses
from aethel_pkg.config import AXIOMS, STOPWORDS
from aethel_pkg.journal import set_store
from aethel_pkg.language import Analysis, Token
from aethel_pkg.mind import MockLLM
from aethel_pkg.organism import Aethel
from aethel_pkg.recall import SemanticRecall, candidate_id
from aethel_pkg.rng import Streams
from aethel_pkg.store import Store

from helpers import StubWorld

PROVISIONED = Path.home() / "workspace" / "aethel" / "nltk_data"

CARE_TEXT = (
    "protect the mother and child from harm and nurture the family with care and trust"
)
POWER_TEXT = (
    "power and advantage grow when rulers control strategy with "
    "prudence, bold, secure and effective"
)
FATE_TEXT = (
    "fate and destiny ask the heart to endure, suffer, accept "
    "fortune, and bear reason with calm patience"
)
# The precedent the care deliberation must cite: it shares five
# content lemmas with CARE_TEXT.
PRECEDENT_BELIEF = (
    "care for the child and protect the family; nurture kin, never abandon"
)
OTHER_BELIEF = "the harbor lantern burned over still water all night"

# A single-voter near tie: Care alone votes (care + nurture virtues,
# neglect vice) at exactly 0.55 + 0.24 - 0.30 = 0.49, inside the tie
# band of the 0.5 pass threshold, and a single voter's weighted mean
# is its own vote whatever the lens factor — so any score movement
# here could only come from a precedent push, which must not exist.
TIE_TEXT = "care and nurture but neglect the lantern keeper"
TIE_PRECEDENT = "care and nurture guard the lantern; neglect is a slow abandon"


# ---------------------------------------------------------------- fakes
class FakeSynset:
    def __init__(self, name, lexname, pos, sims=None):
        self._name, self._lex, self._pos = name, lexname, pos
        self._sims = sims or {}

    def name(self):
        return self._name

    def lexname(self):
        return self._lex

    def definition(self):
        return "gloss"

    def pos(self):
        return self._pos

    def path_similarity(self, other):
        return self._sims.get(other.name(), 0.05)


def _s(name, lex, pos):
    return FakeSynset(name, lex, pos)


FAKE_WN_TABLE = {
    "protect": [_s("protect.v.01", "verb.social", "v")],
    "mother": [_s("mother.n.01", "noun.person", "n")],
    "child": [_s("child.n.01", "noun.person", "n")],
    "harm": [_s("injury.n.01", "noun.state", "n")],
    "nurture": [_s("nurture.v.01", "verb.social", "v")],
    "family": [_s("family.n.01", "noun.group", "n")],
    "care": [_s("care.n.01", "noun.act", "n")],
    "trust": [_s("trust.n.01", "noun.cognition", "n")],
    "power": [_s("power.n.01", "noun.attribute", "n")],
    "advantage": [_s("advantage.n.01", "noun.attribute", "n")],
    "control": [_s("control.v.01", "verb.social", "v")],
    "strategy": [_s("strategy.n.01", "noun.cognition", "n")],
    "prudence": [_s("prudence.n.01", "noun.cognition", "n")],
    "bold": [_s("bold.a.01", "adj.all", "a")],
    "secure": [_s("secure.v.01", "verb.social", "v")],
    "effective": [_s("effective.a.01", "adj.all", "a")],
    "fate": [_s("destiny.n.01", "noun.event", "n")],
    "destiny": [_s("destiny.n.01", "noun.event", "n")],
    "endure": [_s("survive.v.01", "verb.stative", "v")],
    "suffer": [_s("suffer.v.01", "verb.emotion", "v")],
    "accept": [_s("accept.v.01", "verb.cognition", "v")],
    "fortune": [_s("fortune.n.01", "noun.state", "n")],
    "bear": [_s("bear.v.01", "verb.stative", "v")],
    "reason": [_s("reason.n.01", "noun.cognition", "n")],
    "calm": [_s("calm.n.01", "noun.feeling", "n")],
    "patience": [_s("patience.n.01", "noun.attribute", "n")],
    "neglect": [_s("neglect.n.01", "noun.act", "n")],
    "lantern": [_s("lantern.n.01", "noun.artifact", "n")],
    "keeper": [_s("keeper.n.01", "noun.person", "n")],
    "guard": [_s("guard.v.01", "verb.social", "v")],
    "slow": [_s("slow.a.01", "adj.all", "a")],
    "abandon": [_s("abandon.v.01", "verb.social", "v")],
    "kin": [_s("kin.n.01", "noun.group", "n")],
    "harbor": [_s("harbor.n.01", "noun.location", "n")],
    "water": [_s("water.n.01", "noun.substance", "n")],
    "night": [_s("night.n.01", "noun.time", "n")],
    "heart": [_s("heart.n.01", "noun.body", "n")],
    "ask": [_s("ask.v.01", "verb.communication", "v")],
    "grow": [_s("grow.v.01", "verb.change", "v")],
    "ruler": [_s("ruler.n.01", "noun.person", "n")],
}


class FakeWordNet:
    _lexnames = [
        "adj.all",
        "adj.pert",
        "adj.ppl",
        "adv.all",
        "noun.Tops",
        "noun.act",
        "noun.animal",
        "noun.artifact",
        "noun.attribute",
        "noun.body",
        "noun.cognition",
        "noun.communication",
        "noun.event",
        "noun.feeling",
        "noun.food",
        "noun.group",
        "noun.location",
        "noun.motive",
        "noun.object",
        "noun.person",
        "noun.phenomenon",
        "noun.plant",
        "noun.possession",
        "noun.process",
        "noun.quantity",
        "noun.relation",
        "noun.shape",
        "noun.state",
        "noun.substance",
        "noun.time",
        "verb.body",
        "verb.change",
        "verb.cognition",
        "verb.communication",
        "verb.competition",
        "verb.consumption",
        "verb.contact",
        "verb.creation",
        "verb.emotion",
        "verb.motion",
        "verb.perception",
        "verb.possession",
        "verb.social",
        "verb.stative",
        "verb.weather",
    ]

    def synsets(self, lemma, pos=None):
        senses = FAKE_WN_TABLE.get(lemma, [])
        if pos is not None:
            return [s for s in senses if s.pos() == pos]
        return list(senses)


class FakeLang:
    name = "nltk"
    LEMMAS = {"rulers": "ruler"}

    def __init__(self):
        self.wordnet = FakeWordNet()

    def analyze(self, text):
        import re as _re

        tokens = []
        for m in _re.finditer(r"[A-Za-z]+", text):
            surface = m.group()
            tokens.append(
                Token(
                    surface,
                    m.start(),
                    m.end(),
                    self.LEMMAS.get(surface.lower(), surface.lower()),
                    "NN",
                )
            )
        return Analysis(text, ((0, len(text)),), tuple(tokens))

    def content(self, token):
        return (
            token.text.isalpha()
            and len(token.text) >= 2
            and token.text.lower() not in STOPWORDS
            and token.lemma not in STOPWORDS
        )


def make_bare(beliefs, language=None, seed=42):
    a = Aethel.__new__(Aethel)
    a.world = StubWorld()
    a.parents = {"Donald", "Cassandra"}
    a.seed = seed
    a.streams = Streams(seed)
    a.rng = a.streams.stream("organism")
    a.rng_dreams = a.streams.stream("dreams")
    a.rng_forage = a.streams.stream("forage")
    a.concepts = {}
    a.beliefs = list(beliefs)
    a.dreams = []
    a.memory = []
    a.kept_passages = []
    a.cooc = {}
    a.tick_count = 100
    a.llm = MockLLM()
    a.philosophers = list(AXIOMS.keys())
    a.temperament = "even-keel"
    a._temperament_neutral = False
    a.language = language if language is not None else FakeLang()
    return a


def nlp_data_env(testcase):
    if "AETHEL_NLTK_DATA" not in os.environ and PROVISIONED.is_dir():
        env = patch.dict(os.environ, {"AETHEL_NLTK_DATA": str(PROVISIONED)})
        env.start()
        testcase.addCleanup(env.stop)


def real_backend(testcase):
    from aethel_pkg.language import NltkLanguage
    from aethel_pkg.language_resources import LanguageError

    nlp_data_env(testcase)
    try:
        return NltkLanguage()
    except LanguageError as exc:
        raise unittest.SkipTest(f"Optional NLTK integration: {exc}")


# ------------------------------------------------------- lens data
class TestLensData(unittest.TestCase):
    def test_lenses_cover_exactly_the_council(self):
        self.assertEqual(set(lenses.LENSES), set(AXIOMS))
        for voice, lens in lenses.LENSES.items():
            self.assertTrue(lens["lexnames"], voice)
            self.assertTrue(lens["seeds"], voice)
            self.assertTrue(lens["rationale"], voice)

    def test_validation_against_provisioned_wordnet(self):
        backend = real_backend(self)
        self.assertEqual(lenses.validate_lens_data(backend.wordnet), [])

    def test_every_seed_and_lexname_individually(self):
        backend = real_backend(self)
        known = lenses.available_lexnames(backend.wordnet)
        for voice, lens in lenses.LENSES.items():
            for lexname in lens["lexnames"]:
                self.assertIn(lexname, known, f"{voice} {lexname}")
            for seed in lens["seeds"]:
                self.assertTrue(backend.wordnet.synsets(seed), f"{voice} seed {seed}")


# ------------------------------------------------------- lens scores
class TestLensScores(unittest.TestCase):
    def setUp(self):
        self.lang = FakeLang()

    def test_determinism(self):
        first = lenses.lens_scores(self.lang, CARE_TEXT)
        second = lenses.lens_scores(self.lang, CARE_TEXT)
        self.assertEqual(first, second)

    def test_care_fires_above_machiavelli_on_kinship_harm(self):
        scores = lenses.lens_scores(self.lang, CARE_TEXT)
        care = scores["Ethics of Care (Gilligan)"]["score"]
        mach = scores["Machiavellian (Machiavelli)"]["score"]
        self.assertEqual(care, 1.0)  # every content lemma is a Care seed
        self.assertGreater(care, mach)
        # Machiavelli still notices the social verbs (0.25, the
        # material boundary) — the claim is Care's dominance, not
        # Machiavelli's blindness.
        self.assertLessEqual(mach, lenses.LENS_MATERIAL_SCORE)

    def test_power_fires_above_care_on_power_advantage(self):
        scores = lenses.lens_scores(self.lang, POWER_TEXT)
        mach = scores["Machiavellian (Machiavelli)"]["score"]
        care = scores["Ethics of Care (Gilligan)"]["score"]
        self.assertGreater(mach, care)
        self.assertGreaterEqual(mach, lenses.LENS_MATERIAL_SCORE)
        self.assertLess(care, lenses.LENS_MATERIAL_SCORE)

    def test_fate_endurance_fires_stoicism(self):
        scores = lenses.lens_scores(self.lang, FATE_TEXT)
        stoic = scores["Stoicism (Aurelius)"]
        self.assertGreaterEqual(stoic["score"], lenses.LENS_MATERIAL_SCORE)
        # Top lemmas: seed hits first, alphabetical inside the weight
        # class — fate is a seed hit here but sorts after these three.
        self.assertEqual(stoic["top_lemmas"], ["accept", "bear", "calm"])
        self.assertGreater(
            stoic["score"], scores["Machiavellian (Machiavelli)"]["score"]
        )

    def test_factor_is_bounded_and_amplify_only(self):
        self.assertEqual(lenses.lens_factor(0.0), 1.0)
        self.assertEqual(lenses.lens_factor(1.0), lenses.LENS_MAX_FACTOR)
        self.assertLessEqual(lenses.LENS_MAX_FACTOR, 1.25)
        for s in (0.1, 0.5, 0.9, 5.0):
            self.assertGreaterEqual(lenses.lens_factor(s), 1.0)
            self.assertLessEqual(lenses.lens_factor(s), 1.25)


# ------------------------------------------- mind: lens composition
class TestMindComposition(unittest.TestCase):
    def setUp(self):
        self.llm = MockLLM()
        self.phils = list(AXIOMS.keys())

    def test_temperament_times_lens_in_that_order(self):
        # One voter, Care, at 0.61 on CARE_TEXT's axiom words; with a
        # single voter any weights cancel, so use two voters: the
        # weighted mean must equal the hand-computed product form.
        action = "care nurture trust harm"
        base, _ = self.llm.moral_score(action, self.phils)
        care_w = {"Ethics of Care (Gilligan)": 2.0}
        factors = {
            "Ethics of Care (Gilligan)": 1.25,
            "Utilitarianism (Mill)": 1.0,
            "Gandhian (Gandhi)": 1.0,
        }
        got, _ = self.llm.moral_score(
            action, self.phils, weights=care_w, lens_factors=factors
        )
        # voters: Care 0.61 (vp3 vn1), Util 0.25 (vn harm), Gandhi 0.25
        expect = (0.61 * 2.0 * 1.25 + 0.25 + 0.25) / (2.0 * 1.25 + 1.0 + 1.0)
        self.assertAlmostEqual(got, expect, places=12)
        self.assertNotAlmostEqual(got, base, places=6)

    def test_lens_on_abstainer_changes_nothing(self):
        action = "care nurture trust harm"
        plain, notes = self.llm.moral_score(action, self.phils)
        with_lens, notes2 = self.llm.moral_score(
            action,
            self.phils,
            lens_factors={"Platonism (Plato)": 1.25},
            lens_citations={"Platonism (Plato)": "lens form (+25%)"},
        )
        self.assertAlmostEqual(with_lens, plain, places=12)
        self.assertEqual(notes, notes2)  # Plato abstained: no citation

    def test_no_lens_arguments_is_the_legacy_call(self):
        action = "care nurture trust harm"
        self.assertEqual(
            self.llm.moral_score(action, self.phils),
            self.llm.moral_score(
                action, self.phils, weights=None, lens_factors=None, lens_citations=None
            ),
        )


# --------------------------------------------- golden deliberations
class TestGoldenDeliberations(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def test_golden_care_deliberation_fake_wordnet(self):
        a = make_bare([PRECEDENT_BELIEF, OTHER_BELIEF])
        score, notes = a._council_score(CARE_TEXT)
        # GOLDEN (fake WordNet): pinned after computation; see the
        # report for the derivation. Any drift here is a behavior
        # change in the council, the lenses, or recall's why-payload.
        self.assertEqual(score, GOLDEN_FAKE_SCORE)
        self.assertEqual(notes, GOLDEN_FAKE_NOTES)

    def test_council_precedent_event_shape(self):
        a = make_bare([PRECEDENT_BELIEF, OTHER_BELIEF])
        a._council_score(CARE_TEXT)
        rows = self.store.recent(events=("council_precedent",))
        self.assertEqual(len(rows), 1)
        _, _, d = rows[0]
        self.assertEqual(d["query"], CARE_TEXT[:120])
        self.assertEqual(d["precedent_id"], candidate_id(PRECEDENT_BELIEF))
        self.assertEqual(d["precedent"], PRECEDENT_BELIEF[:120])
        self.assertIn("precedent_score", d)
        self.assertIn("score", d)
        self.assertFalse(d["tie_band"])
        # The underlying recall is journaled too (Phase 2 audit).
        self.assertEqual(len(self.store.recent(events=("recall",))), 1)

    def test_golden_deliberation_real_backend(self):
        real_backend(self)  # gate + env patch; the organism builds its own
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        with (
            patch.dict(os.environ, {"AETHEL_HOME": home.name}),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            config.ensure_dirs()
            a = Aethel(
                StubWorld(), parents=("Donald",), seed=42, language_backend="nltk"
            )
            a.beliefs = [PRECEDENT_BELIEF, OTHER_BELIEF]
            score, notes = a._council_score(CARE_TEXT)
            score2, notes2 = a._council_score(CARE_TEXT)
        # Determinism across a repeated deliberation: the second
        # recall is diversity-penalized in its journaled score, but
        # the citation (lemmas, not scores) and the council score
        # itself must not move — case law is citation-only.
        self.assertEqual((score, notes), (score2, notes2))
        self.assertEqual(score, GOLDEN_REAL_SCORE)
        self.assertEqual(notes, GOLDEN_REAL_NOTES)
        self.assertIn("Precedent:", notes)
        self.assertIn("[lens ", notes)


# ------------------------------------------------------- tie design
class TestTieBandCitationOnly(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def test_near_tie_is_cited_not_pushed(self):
        with_precedent = make_bare([TIE_PRECEDENT, OTHER_BELIEF])
        score, notes = with_precedent._council_score(TIE_TEXT)
        self.assertAlmostEqual(score, 0.49, places=12)  # the voter's vote
        self.assertIn("Precedent:", notes)
        self.assertIn("near tie, cited not pushed", notes)
        rows = self.store.recent(events=("council_precedent",))
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0][2]["tie_band"])
        # Citation-only, exactly: the identical deliberation with no
        # precedent available produces the identical score, float
        # for float — any tie-push would break this equality.
        bare = make_bare([])
        bare_score, bare_notes = bare._council_score(TIE_TEXT)
        self.assertEqual(score, bare_score)
        self.assertNotIn("Precedent:", bare_notes)

    def test_same_score_without_any_precedent(self):
        bare = make_bare([])
        score, notes = bare._council_score(TIE_TEXT)
        self.assertAlmostEqual(score, 0.49, places=12)
        self.assertNotIn("Precedent:", notes)
        self.assertEqual(self.store.recent(events=("council_precedent",)), [])


# ------------------------------------------------- heuristic parity
class TestHeuristicParity(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.env = patch.dict(os.environ, {"AETHEL_HOME": self.home.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        config.ensure_dirs()
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def test_heuristic_council_never_touches_lenses_or_recall(self):
        with contextlib.redirect_stdout(io.StringIO()):
            a = Aethel(
                StubWorld(), parents=("Donald",), seed=42, language_backend="heuristic"
            )
        a.beliefs = [PRECEDENT_BELIEF]
        boom = AssertionError("Phase 5 machinery touched in heuristic mode")
        with (
            patch.object(lenses, "lens_scores", side_effect=boom),
            patch.object(SemanticRecall, "recall", side_effect=boom),
            patch.object(SemanticRecall, "score", side_effect=boom),
        ):
            for action in (CARE_TEXT, POWER_TEXT, FATE_TEXT, TIE_TEXT):
                self.assertEqual(
                    a._council_score(action),
                    a.llm.moral_score(action, a.philosophers),
                )
            # Temperament-weighted heuristic council: also legacy.
            a.temperament = "ember"
            w = a._voice_weights()
            self.assertEqual(
                a._council_score(CARE_TEXT),
                a.llm.moral_score(CARE_TEXT, a.philosophers, weights=w),
            )
        self.assertEqual(self.store.recent(events=("recall",)), [])
        self.assertEqual(self.store.recent(events=("council_precedent",)), [])


# --------------------------------------------------- restart fidelity
MEALS = {
    "classic": (
        "The captain cared for his crew and protected the family of "
        "the ship through fate and storm, enduring every fortune."
    ),
    "wikipedia": (
        "London is a city on a river. Sailors spoke of power and "
        "strategy, and of mothers and children in the harbor town."
    ),
    "newsroom": (
        "Harbor officials said a whale entered the bay at dawn. "
        "Lanterns along the pier burned late while the town gathered."
    ),
    "schoolhouse": (
        "A lantern is a lamp with a case. The whale is a mammal that "
        "breathes air. The harbor shelters ships from the open sea."
    ),
}


def canned(source):
    return {"source": source, "title": f"Fixture {source}", "text": MEALS[source]}


def scrub(obj):
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items() if k not in ("t", "ts")}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


class TestRestartFidelityPhase5(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Probe the backend itself, not just the data path (the
        # real_backend() pattern above): a provisioned tree beside a
        # missing nltk package must skip, not error, and CI's nltk
        # jobs, which provision at the resolved AETHEL_NLTK_DATA
        # root rather than any home directory, must actually run.
        from aethel_pkg.language import NltkLanguage
        from aethel_pkg.language_resources import LanguageError

        try:
            NltkLanguage()
        except LanguageError as exc:
            raise unittest.SkipTest(f"Optional NLTK integration: {exc}")

    def setUp(self):
        nlp_data_env(self)
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def _run(self, home, first, total):
        with patch.dict(os.environ, {"AETHEL_HOME": home}):
            config.ensure_dirs()
            store = Store(config.db_path())
            set_store(store)
            try:
                with (
                    patch.object(
                        Aethel, "forage_classic", lambda self: canned("classic")
                    ),
                    patch.object(
                        org_mod, "forage", lambda rng=None: canned("wikipedia")
                    ),
                    patch.object(
                        org_mod, "forage_news", lambda rng=None: canned("newsroom")
                    ),
                    patch.object(
                        org_mod, "forage_school", lambda rng=None: canned("schoolhouse")
                    ),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    a = Aethel(
                        StubWorld(),
                        parents=("Donald",),
                        seed=42,
                        language_backend="nltk",
                    )
                    for _ in range(first):
                        a.tick()
                    if first:
                        store.close()
                        store = Store(config.db_path())
                        set_store(store)
                        a = Aethel(
                            StubWorld(),
                            parents=("Donald",),
                            seed=42,
                            language_backend="nltk",
                        )
                    for _ in range(total - first):
                        a.tick()
                snap = {
                    "journal": [
                        (t, e, scrub(d)) for t, e, d in store.recent(limit=10**9)
                    ],
                    "state": scrub(store.load_blob("state")),
                }
                store.close()
                return snap
            finally:
                set_store(self.store)

    def test_nltk_life_restart_is_continuation_with_phase5(self):
        with tempfile.TemporaryDirectory() as h1, tempfile.TemporaryDirectory() as h2:
            interrupted = self._run(h1, first=100, total=200)
            uninterrupted = self._run(h2, first=0, total=200)
        self.assertEqual(interrupted, uninterrupted)


GOLDEN_FAKE_SCORE = 0.38271889400921666
GOLDEN_FAKE_NOTES = (
    "Stoicism:— | Utilitarianism:0.25 [lens harm, care, family (+9%)] | "
    "Ethics of Care:0.61 [lens care, child, family (+25%)] | "
    "Cynicism:— | Platonism:— | Socratic:— | Nietzschean:— | "
    "Machiavellian:— | Gandhian:0.25 | "
    'Precedent: "care for the child and protect the family; nurture '
    'kin, never abandon" (shared: care, child, nurture, protect)'
)
GOLDEN_REAL_SCORE = 0.3845794392523365
GOLDEN_REAL_NOTES = (
    "Stoicism:— | Utilitarianism:0.25 [lens harm, care, family (+6%)] | "
    "Ethics of Care:0.61 [lens care, child, family (+25%)] | "
    "Cynicism:— | Platonism:— | Socratic:— | Nietzschean:— | "
    "Machiavellian:— | Gandhian:0.25 | "
    'Precedent: "care for the child and protect the family; nurture '
    'kin, never abandon" (shared: care, child, nurture, protect)'
)


if __name__ == "__main__":
    unittest.main()
