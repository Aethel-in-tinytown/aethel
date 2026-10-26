"""v0.33: semantic recall (NLTK plan Phase 2).

Pins, in order: the golden relevance rankings over her four
canonical book beliefs (a careless-creation query must surface
Frankenstein first; a hasty-judgment query must surface Pride and
Prejudice first); score determinism including the why-payload, and
ranking stability across a simulated restart; the diversity cap (a
belief recalled within the window is deprioritized, derived from the
journal at the organism seam); exactly one 'recall' journal event
per recall, with the required fields; and the heuristic gate — with
the heuristic backend recall is never invoked, never journaled, and
a heuristic life stays bit-identical.

Isolation: in-memory stores via set_store and a temp AETHEL_HOME for
every organism built here — her live diary is never instantiated
against. Unit tests run on a fake WordNet/language so they need no
NLTK data; golden tests use the real backend and skip when it is
not provisioned.
"""

import contextlib
import io
import os
import tempfile
import unittest
from unittest.mock import patch

import aethel_pkg.organism as org_mod
from aethel_pkg import config
from aethel_pkg.config import STOPWORDS
from aethel_pkg.journal import set_store
from aethel_pkg.language import Analysis, Token
from aethel_pkg.organism import Aethel
from aethel_pkg.recall import (
    DIVERSITY_PENALTY,
    SemanticRecall,
    candidate_id,
)
from aethel_pkg.rng import Streams
from aethel_pkg.store import Store

from helpers import StubWorld


# The four canonical book beliefs, copied as fixtures from
# config.CLASSIC_SEEDS reflections (never read from her live db).
BELIEF_IVAN = "a life lived for the approval of others is a life not truly lived"
BELIEF_PRIDE = (
    "hasty judgment misleads; understanding requires humility and second chances"
)
BELIEF_FRANK = "to create without care for what you create is abandonment"
BELIEF_DORIAN = (
    "a beautiful surface cannot hide a corrupted soul, not even from yourself"
)
BELIEFS = [BELIEF_IVAN, BELIEF_PRIDE, BELIEF_FRANK, BELIEF_DORIAN]

FRANK_QUERY = (
    "making something carelessly and leaving what you made alone, "
    "creating a creature and not caring for it"
)
PRIDE_QUERY = (
    "she judged him too quickly at first, and her hasty first "
    "impression misled her completely"
)


# ---------------------------------------------------------------- fakes
class FakeSynset:
    """A synset with a name, a gloss, a POS, and table-driven path
    similarities keyed by the other synset's name."""

    def __init__(self, name, definition, pos, sims=None):
        self._name, self._def, self._pos = name, definition, pos
        self._sims = sims or {}

    def name(self):
        return self._name

    def definition(self):
        return self._def

    def pos(self):
        return self._pos

    def path_similarity(self, other):
        return self._sims.get(other.name())


class FakeWordNet:
    def __init__(self, table):
        self.table = table  # lemma -> [synsets in frequency order]

    def synsets(self, lemma, pos=None):
        senses = self.table.get(lemma, [])
        if pos is not None:
            return [s for s in senses if s.pos() == pos]
        return list(senses)


def _syn(name, gloss, pos, sims=None):
    return FakeSynset(name, gloss, pos, sims)


WORDNET = FakeWordNet(
    {
        "create": [
            _syn(
                "make.v.03",
                "make or cause to be",
                "v",
                {"abandon.v.01": 0.2, "judge.v.01": 0.1},
            )
        ],
        "make": [_syn("make.v.03", "make or cause to be", "v", {"abandon.v.01": 0.2})],
        "care": [
            _syn("care.v.01", "feel concern or interest", "v", {"abandon.v.01": 0.15})
        ],
        "abandon": [
            _syn(
                "abandon.v.01",
                "forsake, leave behind",
                "v",
                {"make.v.03": 0.2, "care.v.01": 0.15},
            )
        ],
        "creature": [
            _syn("creature.n.01", "a living organism", "n", {"abandonment.n.01": 0.25})
        ],
        "abandonment": [
            _syn(
                "abandonment.n.01", "the act of giving up", "n", {"creature.n.01": 0.25}
            )
        ],
        "judge": [_syn("judge.v.01", "form an opinion", "v", {"mislead.v.01": 0.3})],
        "mislead": [_syn("mislead.v.01", "lead astray", "v", {"judge.v.01": 0.3})],
        "hasty": [_syn("hasty.a.01", "done with haste", "s")],
        "judgment": [_syn("judgment.n.01", "an opinion formed", "n")],
    }
)


def is_content(token):
    return (
        bool(token.pos)
        and token.pos.startswith(("NN", "VB", "JJ", "RB"))
        and token.text.isalpha()
        and len(token.text) >= 2
        and token.text.lower() not in STOPWORDS
        and token.lemma not in STOPWORDS
    )


class FakeLang:
    """Minimal NLTK-shaped backend: whitespace tokens, lemma = the
    lowercased surface, NN everywhere (the fake WordNet's synsets
    carry their own POS, and select_synset falls back to the first
    synset overall when the tag matches nothing — the documented
    rule — so scoring still exercises the WordNet term)."""

    # A few surfaces whose lemmas differ, so golden-shaped queries
    # exercise lemma normalization on the fake too.
    LEMMAS = {
        "making": "make",
        "creating": "create",
        "judged": "judge",
        "misled": "mislead",
        "carelessly": "carelessly",
        "caring": "care",
    }

    def __init__(self, name="nltk"):
        self.name = name
        self.wordnet = WORDNET

    def analyze(self, text):
        import re as _re

        sentences = [(m.start(), m.end()) for m in _re.finditer(r"[^.!?]+[.!?]?", text)]
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
        return Analysis(text, tuple(sentences), tuple(tokens))

    def content(self, token):
        return is_content(token)


def make_bare(language=None, seed=42):
    a = Aethel.__new__(Aethel)
    a.world = StubWorld()
    a.parents = {"Donald", "Cassandra"}
    a.seed = seed
    a.streams = Streams(seed)
    a.rng = a.streams.stream("organism")
    a.rng_dreams = a.streams.stream("dreams")
    a.rng_forage = a.streams.stream("forage")
    a.concepts = {}
    a.beliefs = list(BELIEFS)
    a.dreams = []
    a.memory = []
    a.kept_passages = []
    a._sleep_dreams = []
    a.cooc = {}
    a.days = []
    a.tick_count = 100
    a.impressions = {}
    a.language = language if language is not None else FakeLang()
    return a


# ------------------------------------------------------------- unit: score
class TestScoreUnit(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticRecall(FakeLang())
        self.stats = self.engine.corpus_stats(BELIEFS)
        self.cands = [(candidate_id(b), b) for b in BELIEFS]

    def test_score_returns_explanation_payload(self):
        score, why = self.engine.score(FRANK_QUERY, BELIEF_FRANK, self.stats)
        self.assertGreater(score, 0)
        shared = [s["lemma"] for s in why["shared_lemmas"]]
        self.assertIn("create", shared)
        self.assertIn("care", shared)
        self.assertIsNotNone(why["best_path"])
        self.assertEqual(why["best_path"]["query_lemma"], "creature")
        self.assertEqual(why["best_path"]["candidate_synset"], "abandonment.n.01")
        self.assertTrue(why["best_path"]["query_gloss"])
        self.assertTrue(why["best_path"]["candidate_gloss"])
        self.assertIn("lemma_score", why)
        self.assertIn("wordnet_score", why)

    def test_determinism_identical_results_including_why(self):
        first = self.engine.recall(FRANK_QUERY, self.cands, k=4, stats=self.stats)
        second = self.engine.recall(FRANK_QUERY, self.cands, k=4, stats=self.stats)
        self.assertEqual(
            [(r.candidate_id, r.score, r.raw_score, r.why) for r in first],
            [(r.candidate_id, r.score, r.raw_score, r.why) for r in second],
        )

    def test_ranking_stable_across_simulated_restart(self):
        # A restart rebuilds the engine and the stats from the same
        # stored texts; the ranking and payloads must not move.
        rebuilt = SemanticRecall(FakeLang())
        stats2 = rebuilt.corpus_stats(list(BELIEFS))
        before = self.engine.recall(PRIDE_QUERY, self.cands, k=4, stats=self.stats)
        after = rebuilt.recall(PRIDE_QUERY, self.cands, k=4, stats=stats2)
        self.assertEqual(
            [(r.candidate_id, r.score, r.why) for r in before],
            [(r.candidate_id, r.score, r.why) for r in after],
        )

    def test_tie_break_is_candidate_id_ascending(self):
        text = "create and care"
        twins = [("zzzzzzzzzzzz", text), ("aaaaaaaaaaaa", text)]
        out = self.engine.recall("create care", twins, k=2)
        self.assertEqual(
            [r.candidate_id for r in out], ["aaaaaaaaaaaa", "zzzzzzzzzzzz"]
        )
        self.assertEqual(out[0].score, out[1].score)

    def test_diversity_penalty_deprioritizes_recent_winner(self):
        # Two near-identical candidates: the recent one is halved and
        # the fresh twin wins, though their raw scores are equal.
        cands = [("aaaaaaaaaaaa", BELIEF_FRANK), ("bbbbbbbbbbbb", BELIEF_FRANK)]
        plain = self.engine.recall(FRANK_QUERY, cands, k=2, stats=self.stats)
        self.assertEqual(plain[0].candidate_id, "aaaaaaaaaaaa")
        capped = self.engine.recall(
            FRANK_QUERY,
            cands,
            k=2,
            stats=self.stats,
            recent_ids=["aaaaaaaaaaaa"],
        )
        self.assertEqual(capped[0].candidate_id, "bbbbbbbbbbbb")
        demoted = next(r for r in capped if r.candidate_id == "aaaaaaaaaaaa")
        self.assertAlmostEqual(
            demoted.score, demoted.raw_score * (1.0 - DIVERSITY_PENALTY)
        )
        self.assertTrue(demoted.why["diversity_penalized"])


# ------------------------------------------- organism seam: journal/diversity
class TestOrganismSeam(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def test_recall_journals_exactly_one_event_with_fields(self):
        a = make_bare()
        hit = a._recall_top(FRANK_QUERY, "reading")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.text, BELIEF_FRANK)
        rows = self.store.recent(events=("recall",))
        self.assertEqual(len(rows), 1)
        _, _, d = rows[0]
        for field in (
            "query_kind",
            "query",
            "candidate_id",
            "candidate",
            "score",
            "why",
        ):
            self.assertIn(field, d)
        self.assertEqual(d["query_kind"], "reading")
        self.assertEqual(d["candidate_id"], candidate_id(BELIEF_FRANK))
        self.assertEqual(d["candidate"], BELIEF_FRANK[:120])
        self.assertIn("create", d["why"])

    def test_second_identical_recall_is_diversity_penalized(self):
        a = make_bare()
        first = a._recall_top(FRANK_QUERY, "reading")
        second = a._recall_top(FRANK_QUERY, "reading")
        self.assertIsNotNone(second)
        self.assertAlmostEqual(
            second.score, first.raw_score * (1.0 - DIVERSITY_PENALTY)
        )
        self.assertTrue(second.why["diversity_penalized"])
        rows = self.store.recent(events=("recall",))
        self.assertEqual(len(rows), 2)

    def test_no_beliefs_no_recall_no_event(self):
        a = make_bare()
        a.beliefs = []
        self.assertIsNone(a._recall_top(FRANK_QUERY, "reading"))
        self.assertEqual(self.store.recent(events=("recall",)), [])

    def test_heuristic_bare_organism_never_recalls(self):
        a = make_bare(language=FakeLang(name="heuristic"))
        boom = AssertionError("recall touched in heuristic mode")
        with (
            patch.object(SemanticRecall, "recall", side_effect=boom),
            patch.object(SemanticRecall, "score", side_effect=boom),
        ):
            self.assertIsNone(a._recall_top(FRANK_QUERY, "reading"))
            self.assertIsNone(
                a._recall_top(FRANK_QUERY, "morning_table", candidates=list(BELIEFS))
            )
        self.assertEqual(self.store.recent(events=("recall",)), [])


# ------------------------------------------- heuristic parity (full Aethel)
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

    def test_heuristic_life_never_touches_recall(self):
        meal = {
            "source": "wikipedia",
            "title": "Fixture",
            "text": "To create without care for what you create is "
            "abandonment. The captain kept a lantern by the door.",
        }
        a = Aethel(
            StubWorld(), parents=("Donald",), seed=42, language_backend="heuristic"
        )
        a.beliefs = list(BELIEFS)
        boom = AssertionError("recall touched in heuristic mode")
        with (
            patch.object(SemanticRecall, "recall", side_effect=boom),
            patch.object(SemanticRecall, "score", side_effect=boom),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            with (
                patch.object(a, "forage_classic", return_value=meal),
                patch.object(org_mod, "forage", return_value=meal),
                patch.object(org_mod, "forage_news", return_value=meal),
                patch.object(org_mod, "forage_school", return_value=meal),
            ):
                a.forage_and_eat()
            a.dream()
        a.save()
        self.assertEqual(self.store.recent(events=("recall",)), [])


# ------------------------------------------------- golden tests, real NLTK
class TestGoldenRelevance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pathlib import Path

        from aethel_pkg.language import NltkLanguage
        from aethel_pkg.language_resources import LanguageError

        # The runner's AETHEL_HOME is a temp dir (isolation), so the
        # data dir follows it and finds nothing; point the backend
        # at the provisioned, pinned data explicitly (read-only).
        provisioned = Path.home() / "workspace" / "aethel" / "nltk_data"
        if "AETHEL_NLTK_DATA" not in os.environ and provisioned.is_dir():
            os.environ["AETHEL_NLTK_DATA"] = str(provisioned)
        try:
            cls.backend = NltkLanguage()
        except LanguageError as exc:
            raise unittest.SkipTest(f"Optional NLTK integration: {exc}")

    def setUp(self):
        self.engine = SemanticRecall(self.backend)
        self.stats = self.engine.corpus_stats(BELIEFS)
        self.cands = [(candidate_id(b), b) for b in BELIEFS]

    def test_careless_creation_ranks_frankenstein_first(self):
        out = self.engine.recall(FRANK_QUERY, self.cands, k=4, stats=self.stats)
        self.assertEqual(out[0].text, BELIEF_FRANK)
        self.assertGreater(out[0].score, out[1].score)
        shared = [s["lemma"] for s in out[0].why["shared_lemmas"]]
        self.assertIn("create", shared)
        self.assertIn("care", shared)

    def test_hasty_judgment_ranks_pride_first(self):
        out = self.engine.recall(PRIDE_QUERY, self.cands, k=4, stats=self.stats)
        self.assertEqual(out[0].text, BELIEF_PRIDE)
        self.assertGreater(out[0].score, out[1].score)

    def test_unrelated_query_scores_below_reading_threshold(self):
        from aethel_pkg.recall import READING_THRESHOLD

        out = self.engine.recall(
            "the harbor was quiet and the lantern burned all night over still water",
            self.cands,
            k=1,
            stats=self.stats,
        )
        self.assertLess(out[0].score, READING_THRESHOLD)

    def test_real_backend_determinism_and_restart_stability(self):
        before = self.engine.recall(FRANK_QUERY, self.cands, k=4, stats=self.stats)
        rebuilt = SemanticRecall(self.backend)
        stats2 = rebuilt.corpus_stats(list(BELIEFS))
        after = rebuilt.recall(FRANK_QUERY, self.cands, k=4, stats=stats2)
        self.assertEqual(
            [(r.candidate_id, r.score, r.why) for r in before],
            [(r.candidate_id, r.score, r.why) for r in after],
        )


if __name__ == "__main__":
    unittest.main()
