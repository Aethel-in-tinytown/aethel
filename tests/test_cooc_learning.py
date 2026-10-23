"""v0.37: counting learning — co-occurrence, extended (NLTK plan Phase 6a).

The graph itself is NOT new: organism.cooc has learned from meals
and fed dream generation since long before the NLTK plan. Phase 6a
pins what this version adds on top of it:

- coverage: in NLTK mode her own generated texts (dreams, letters /
  notes — verses ride as letter bodies — and beliefs at settling)
  update the same graph through the same update path; in heuristic
  mode they NEVER do (the parity gate: her generated texts exist in
  both backends, so an ungated hook would rewrite heuristic lives);
- recall: the Phase 2 score gains a bounded personal-association
  term read off the graph (ASSOC_WEIGHT cap, saturating strength),
  with the association evidence in the why-payload; the Phase 2
  goldens still rank first, with and without a realistic graph;
- notebook: the derived "keeps company with" view (companions),
  computed from the graph at read time, stored nowhere, and visible
  in the notebook_hers journal event;
- migration: a v0.36-shaped state blob loads losslessly, its cooc
  edges intact; the persisted graph's shape (lemma -> lemma -> int)
  is unchanged, so the new code writes nothing the old code cannot
  read;
- restart fidelity with 6a active: a seeded NLTK life stopped
  mid-run and rebuilt matches the uninterrupted life, journal and
  state (graph included), and the run demonstrably exercised the
  new coverage (cooc_learned events present).

Isolation: in-memory stores via set_store and a temp AETHEL_HOME for
every organism built here — her live diary is never instantiated
against. Unit tests run on a fake backend so they need no NLTK
data; integration tests use the real backend and skip when it is
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
from aethel_pkg.notebook import Notebook
from aethel_pkg.organism import Aethel
from aethel_pkg.recall import (
    ASSOC_SATURATION,
    ASSOC_WEIGHT,
    SemanticRecall,
    candidate_id,
)
from aethel_pkg.rng import Streams
from aethel_pkg.store import Store

from helpers import StubWorld
from test_notebook import make_bare as notebook_make_bare
from test_notebook import whale_passage


# ---------------------------------------------------------------- fakes
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
    lowercased surface, NN everywhere, no WordNet (the recall
    WordNet term is 0, which isolates the association arithmetic)."""

    def __init__(self, name="nltk"):
        self.name = name
        self.wordnet = None

    def analyze(self, text):
        import re as _re

        sentences = [
            (m.start(), m.end())
            for m in _re.finditer(r"[^.!?]+[.!?]?", text)
        ]
        tokens = []
        for m in _re.finditer(r"[A-Za-z]+", text):
            surface = m.group()
            tokens.append(
                Token(surface, m.start(), m.end(), surface.lower(), "NN")
            )
        return Analysis(text, tuple(sentences), tuple(tokens))

    def content(self, token):
        return is_content(token)


CONCEPTS = {"whale": 9, "ocean": 8, "captain": 7, "lantern": 6, "harbor": 5}


def make_bare(language=None, seed=42):
    a = Aethel.__new__(Aethel)
    a.world = StubWorld()
    a.parents = {"Donald", "Cassandra"}
    a.seed = seed
    a.streams = Streams(seed)
    a.rng = a.streams.stream("organism")
    a.rng_dreams = a.streams.stream("dreams")
    a.rng_forage = a.streams.stream("forage")
    a.concepts = dict(CONCEPTS)
    a.lemma_index = {w: {w: c} for w, c in CONCEPTS.items()}
    a.beliefs = []
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


def graph_weight(cooc):
    return sum(sum(row.values()) for row in cooc.values())


# ------------------------------------------- coverage: her own writing
class TestGeneratedCoverage(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def test_generated_text_adds_symmetric_edges(self):
        a = make_bare()
        a._cooc_learn_generated(
            "The whale crossed the ocean with the captain.", via="dream"
        )
        self.assertEqual(a.cooc["whale"]["ocean"], Aethel.COOC_GENERATED_WEIGHT)
        self.assertEqual(a.cooc["ocean"]["whale"], Aethel.COOC_GENERATED_WEIGHT)
        self.assertEqual(a.cooc["whale"]["captain"], Aethel.COOC_GENERATED_WEIGHT)

    def test_generated_counts_once_per_text_not_per_token(self):
        a = make_bare()
        a._cooc_learn_generated("Whale, whale, whale — the ocean.", via="note")
        self.assertEqual(a.cooc["whale"]["ocean"], 1)
        a._cooc_learn_generated("The whale and the ocean again.", via="note")
        self.assertEqual(a.cooc["whale"]["ocean"], 2)

    def test_cooc_learned_event_journaled_with_via(self):
        a = make_bare()
        a._cooc_learn_generated("The lantern lit the harbor.", via="belief")
        rows = self.store.recent(events=("cooc_learned",))
        self.assertEqual(len(rows), 1)
        _, _, d = rows[0]
        self.assertEqual(d["via"], "belief")
        self.assertEqual(d["words"], 2)  # lantern, harbor participate

    def test_words_outside_her_concepts_form_no_edges(self):
        a = make_bare()
        a._cooc_learn_generated("The zebra met the quokka.", via="dream")
        self.assertEqual(a.cooc, {})
        self.assertEqual(self.store.recent(events=("cooc_learned",)), [])

    def test_updates_are_pure_functions_of_the_texts(self):
        # Same event sequence -> same graph, regardless of wall
        # clock: two bares fed the same meals and the same generated
        # texts in the same order agree edge for edge.
        seq = []
        a, b = make_bare(), make_bare()
        for x in (a, b):
            x._update_cooc(["whale", "ocean", "captain"])
            x._cooc_learn_generated("The lantern over the harbor.", via="note")
            x._cooc_learn_generated("The whale and the lantern.", via="dream")
            seq.append(x.cooc)
        self.assertEqual(seq[0], seq[1])
        self.assertEqual(a.cooc["lantern"]["harbor"], 1)
        self.assertEqual(a.cooc["whale"]["lantern"], 1)

    def test_graph_identical_after_simulated_restart(self):
        a = make_bare()
        a._update_cooc(["whale", "ocean"])
        a._cooc_learn_generated("The captain and the lantern.", via="dream")
        snapshot = {w: dict(row) for w, row in a.cooc.items()}
        rebuilt = make_bare()
        rebuilt.cooc = {w: dict(row) for w, row in snapshot.items()}
        self.assertEqual(rebuilt.cooc, a.cooc)


# ------------------------------------------------------- heuristic gate
class TestHeuristicGate(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def test_generated_texts_never_touch_the_graph_in_heuristic_mode(self):
        a = make_bare(language=FakeLang(name="heuristic"))
        a._update_cooc(["whale", "ocean"])  # the meal path, as always
        before = {w: dict(r) for w, r in a.cooc.items()}
        a._cooc_learn_generated("The whale and the captain.", via="dream")
        a._cooc_learn_generated("The lantern lit the harbor.", via="note")
        self.assertEqual(a.cooc, before)
        self.assertEqual(self.store.recent(events=("cooc_learned",)), [])

    def test_meal_path_unchanged_in_heuristic_mode(self):
        a = make_bare(language=FakeLang(name="heuristic"))
        a._update_cooc(["whale", "ocean", "captain", "whale"])
        self.assertEqual(a.cooc["whale"]["ocean"], 1)
        self.assertEqual(a.cooc["ocean"]["whale"], 1)
        self.assertEqual(a.cooc["captain"]["whale"], 1)


# ------------------------------------------------- recall: association
class TestRecallAssociation(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticRecall(FakeLang())
        # Her graph: whale keeps company with ocean (3 texts) — and
        # nothing else in these fixtures.
        self.cooc = {"whale": {"ocean": 3}, "ocean": {"whale": 3}}

    def test_association_fires_with_weak_lexical_overlap(self):
        # Neither candidate shares a lemma with the query, so both
        # base scores are 0 and candidate-id order decides — until
        # her own association speaks for the ocean text.
        cands = [
            ("aaaaaaaaaaaa", "ocean deep and still"),
            ("bbbbbbbbbbbb", "mountain high and cold"),
        ]
        plain = self.engine.recall("whale song", cands, k=2)
        self.assertEqual(plain[0].candidate_id, "aaaaaaaaaaaa")
        self.assertEqual(plain[0].score, plain[1].score)
        boosted = self.engine.recall("whale song", cands, k=2, cooc=self.cooc)
        self.assertEqual(boosted[0].candidate_id, "aaaaaaaaaaaa")
        self.assertGreater(boosted[0].score, 0)
        self.assertEqual(boosted[1].score, 0)
        why = boosted[0].why
        self.assertEqual(len(why["associations"]), 1)
        ev = why["associations"][0]
        self.assertEqual(ev["query_lemma"], "whale")
        self.assertEqual(ev["candidate_lemma"], "ocean")
        self.assertEqual(ev["count"], 3)
        # assoc = mean over the query's content lemmas of best
        # strength: whale -> 3/(3+K); any other query lemma -> 0.
        # (The fake's content rule shares config STOPWORDS, so the
        # divisor is read off the engine's own content map rather
        # than assumed from the raw query string.)
        n_query = len(self.engine.content_map("whale song"))
        expected_assoc = (3 / (3 + ASSOC_SATURATION)) / n_query
        self.assertAlmostEqual(why["assoc_score"], round(expected_assoc, 6))
        self.assertAlmostEqual(
            boosted[0].raw_score, ASSOC_WEIGHT * expected_assoc, places=6
        )

    def test_association_bonus_is_capped_by_the_documented_arithmetic(self):
        # Full lemma overlap: base is the pure lemma term (no
        # WordNet on the fake). Even with a maximal graph the bonus
        # cannot exceed ASSOC_WEIGHT * (1 - base).
        query = "whale ocean captain"
        candidate = "whale ocean captain"
        base, base_why = self.engine.score(query, candidate)
        self.assertAlmostEqual(base, 0.75, places=6)
        heavy = {
            w: {o: 10000 for o in ("whale", "ocean", "captain") if o != w}
            for w in ("whale", "ocean", "captain")
        }
        total, why = self.engine.score(query, candidate, cooc=heavy)
        self.assertLessEqual(total, base + ASSOC_WEIGHT * (1 - base) + 1e-9)
        self.assertLess(total, base + ASSOC_WEIGHT)
        self.assertLessEqual(total, 1.0)
        self.assertTrue(why["associations"])

    def test_no_graph_no_bonus_bit_for_bit(self):
        # Without a graph the score is the pre-6a score exactly:
        # 0.75 * lemma overlap + 0.25 * wordnet (0 on the fake).
        score, why = self.engine.score("whale song", "whale deep")
        self.assertAlmostEqual(score, 0.75 * why["lemma_score"], places=5)
        self.assertEqual(why["assoc_score"], 0)
        self.assertEqual(why["associations"], [])

    def test_identical_lemmas_earn_no_association(self):
        # whale~whale is already paid by the overlap term; the graph
        # must not pay it twice.
        score, why = self.engine.score(
            "whale", "whale", cooc={"whale": {"whale": 9}}
        )
        self.assertEqual(why["assoc_score"], 0)
        self.assertAlmostEqual(score, 0.75, places=6)


# ------------------------------------------------- notebook: companions
class TestNotebookCompanions(unittest.TestCase):
    def setUp(self):
        self.nb = Notebook()
        _, analysis = whale_passage()
        self.nb.feed(analysis, "classic", 1, None, is_content)
        self.cooc = {
            "whale": {"ocean": 5, "captain": 5, "lantern": 2},
            "lantern": {"whale": 2},
        }

    def test_companions_ranked_count_desc_then_name(self):
        self.assertEqual(
            self.nb.companions("whale", self.cooc),
            [("captain", 5), ("ocean", 5), ("lantern", 2)],
        )
        self.assertEqual(
            self.nb.companions("whale", self.cooc, k=2),
            [("captain", 5), ("ocean", 5)],
        )

    def test_companions_deterministic_and_derived_not_stored(self):
        first = self.nb.companions("whale", self.cooc)
        second = self.nb.companions("whale", self.cooc)
        self.assertEqual(first, second)
        self.assertNotIn("companions", self.nb.get("whale"))

    def test_absent_lemma_and_rowless_entry_are_empty(self):
        self.assertEqual(self.nb.companions("zebra", self.cooc), [])
        self.assertEqual(self.nb.companions("captain", self.cooc), [])
        self.assertEqual(self.nb.companions("whale", {}), [])
        self.assertEqual(self.nb.companions("whale", None), [])

    def test_hers_event_carries_the_companions_view(self):
        store = Store(":memory:")
        set_store(store)
        self.addCleanup(store.close)
        a = notebook_make_bare()
        _, analysis = whale_passage()
        a._notebook_feed(analysis, analysis.tokens, "classic")
        a.cooc = {"whale": {"ocean": 4, "lantern": 1}}
        a._notebook_mark_generated("The whale returned.", via="dream")
        rows = store.recent(events=("notebook_hers",))
        self.assertEqual(len(rows), 1)
        _, _, d = rows[0]
        self.assertEqual(d["lemma"], "whale")
        self.assertEqual(d["companions"], ["ocean", "lantern"])


# ------------------------------------------- real-backend integration
MEAL = {
    "source": "wikipedia",
    "title": "Fixture",
    "text": (
        "The captain kept a brass lantern beside the chart table. "
        "Beyond the harbor, a whale surfaced and breathed, and the "
        "whole crew fell silent to watch it."
    ),
}


class TestIntegrationRealBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pathlib import Path

        from aethel_pkg.language import NltkLanguage
        from aethel_pkg.language_resources import LanguageError

        provisioned = Path.home() / "workspace" / "aethel" / "nltk_data"
        if "AETHEL_NLTK_DATA" not in os.environ and provisioned.is_dir():
            os.environ["AETHEL_NLTK_DATA"] = str(provisioned)
        try:
            cls.backend = NltkLanguage()
        except LanguageError as exc:
            raise unittest.SkipTest(f"Optional NLTK integration: {exc}")

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

    def organism(self, backend="nltk"):
        return Aethel(StubWorld(), parents=("Donald",), seed=42,
                      language_backend=backend)

    def _feed_meals(self, a, times=3):
        with contextlib.redirect_stdout(io.StringIO()):
            for _ in range(times):
                with patch.object(a, "forage_classic", return_value=MEAL), \
                        patch.object(org_mod, "forage", return_value=MEAL), \
                        patch.object(org_mod, "forage_news", return_value=MEAL), \
                        patch.object(org_mod, "forage_school",
                                     return_value=MEAL):
                    a.forage_and_eat()

    def test_dream_and_letter_hooks_fire_in_nltk_life(self):
        a = self.organism()
        self._feed_meals(a)
        self.assertTrue(a.cooc, "sanity: meals built the graph")
        with contextlib.redirect_stdout(io.StringIO()):
            a.dream()
            a.express()
        rows = self.store.recent(events=("cooc_learned",))
        vias = {d["via"] for _, _, d in rows}
        self.assertIn("dream", vias)
        self.assertTrue(
            vias & {"note", "question", "nudge"},
            f"letter hook did not fire; vias={vias}",
        )

    def test_heuristic_life_gains_no_generated_edges(self):
        a = self.organism(backend="heuristic")
        self._feed_meals(a, times=1)
        before = {w: dict(r) for w, r in a.cooc.items()}
        with contextlib.redirect_stdout(io.StringIO()):
            a.dream()
        self.assertEqual(a.cooc, before)
        self.assertEqual(self.store.recent(events=("cooc_learned",)), [])

    def test_v036_state_loads_losslessly(self):
        # A state blob in the v0.36 shape — same keys the old save()
        # wrote, cooc included — must load under this version with
        # its graph preserved edge for edge.
        store = Store(config.db_path())
        set_store(store)
        self.addCleanup(store.close)
        fixture_cooc = {"whale": {"ocean": 2, "lantern": 1},
                        "ocean": {"whale": 2},
                        "lantern": {"whale": 1}}
        store.save_blob("state", {
            "seed": 42,
            "language": self.backend.metadata,
            "concepts": {"whale": 3, "ocean": 2, "lantern": 1},
            "lemma_index": {"whale": {"whale": 3}, "ocean": {"ocean": 2},
                            "lantern": {"lantern": 1}},
            "cooc": fixture_cooc,
            "tick_count": 500,
        })
        a = self.organism()
        self.assertEqual(a.cooc, fixture_cooc)
        # And the shape this version writes back is the shape the
        # old version read: plain lemma -> lemma -> int, no new keys.
        a.save()
        blob = store.load_blob("state")
        self.assertEqual(set(blob["cooc"]), set(fixture_cooc))
        for row in blob["cooc"].values():
            for count in row.values():
                self.assertIsInstance(count, int)

    def test_nltk_restart_fidelity_with_6a_active(self):
        # Phase 1's seeded-life harness shape (canned meals, scrubbed
        # wall clock, same 260-tick span its restart gate uses);
        # assert the run actually exercised 6a coverage, then that
        # interruption changes nothing.
        canned_texts = {
            "classic": (
                "The captain kept a brass lantern beside the chart "
                "table. Beyond the harbor, a whale surfaced and "
                "breathed, and the whole crew fell silent."
            ),
            "wikipedia": (
                "A lantern burns oil inside a glass chimney. Whales "
                "surface in the harbor to breathe, and sailors watch "
                "the water for their return."
            ),
            "newsroom": (
                "Harbor officials said a whale entered the bay at "
                "dawn. Lanterns along the pier burned late while the "
                "town gathered to watch."
            ),
            "schoolhouse": (
                "A lantern is a lamp with a case. The whale is a "
                "mammal that breathes air. The harbor shelters ships "
                "from the open sea."
            ),
        }

        def canned(source):
            return {"source": source, "title": f"Fixture {source}",
                    "text": canned_texts[source]}

        def scrub(obj):
            if isinstance(obj, dict):
                return {k: scrub(v) for k, v in obj.items()
                        if k not in ("t", "ts")}
            if isinstance(obj, list):
                return [scrub(v) for v in obj]
            return obj

        def run(home, first, total):
            with patch.dict(os.environ, {"AETHEL_HOME": home}):
                config.ensure_dirs()
                store = Store(config.db_path())
                set_store(store)
                try:
                    with patch.object(
                        Aethel, "forage_classic",
                        lambda self: canned("classic"),
                    ), patch.object(
                        org_mod, "forage", lambda rng=None: canned("wikipedia")
                    ), patch.object(
                        org_mod, "forage_news",
                        lambda rng=None: canned("newsroom"),
                    ), patch.object(
                        org_mod, "forage_school",
                        lambda rng=None: canned("schoolhouse"),
                    ), contextlib.redirect_stdout(io.StringIO()):
                        a = Aethel(StubWorld(), parents=("Donald",),
                                   seed=42, language_backend="nltk")
                        for _ in range(first):
                            a.tick()
                        if first:
                            store.close()
                            store = Store(config.db_path())
                            set_store(store)
                            a = Aethel(StubWorld(), parents=("Donald",),
                                       seed=42, language_backend="nltk")
                        for _ in range(total - first):
                            a.tick()
                    snap = {
                        "journal": [
                            (t, e, scrub(d))
                            for t, e, d in store.recent(limit=10 ** 9)
                        ],
                        "state": scrub(store.load_blob("state")),
                    }
                    store.close()
                    return snap
                finally:
                    set_store(self.store)

        with tempfile.TemporaryDirectory() as h1, \
                tempfile.TemporaryDirectory() as h2:
            interrupted = run(h1, first=130, total=260)
            uninterrupted = run(h2, first=0, total=260)
        events = [e for _, e, _ in uninterrupted["journal"]]
        self.assertIn("cooc_learned", events,
                      "sanity: the run exercised Phase 6a coverage")
        self.assertTrue(uninterrupted["state"]["cooc"])
        self.assertEqual(interrupted, uninterrupted)


# ------------------------------------------- goldens with a real graph
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


class TestGoldenWithGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pathlib import Path

        from aethel_pkg.language import NltkLanguage
        from aethel_pkg.language_resources import LanguageError

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
        # A graph such as her meals of these very texts would have
        # built: every pair of content lemmas that shared a belief
        # keeps company once.
        self.cooc = {}
        for belief in BELIEFS:
            words = list(dict.fromkeys(self.engine.content_map(belief)))
            for i, x in enumerate(words):
                for y in words[i + 1:]:
                    row = self.cooc.setdefault(x, {})
                    row[y] = row.get(y, 0) + 1
                    back = self.cooc.setdefault(y, {})
                    back[x] = back.get(x, 0) + 1

    def test_frankenstein_golden_holds_with_graph(self):
        out = self.engine.recall(FRANK_QUERY, self.cands, k=4,
                                 stats=self.stats, cooc=self.cooc)
        self.assertEqual(out[0].text, BELIEF_FRANK)
        self.assertGreater(out[0].score, out[1].score)

    def test_pride_golden_holds_with_graph(self):
        out = self.engine.recall(PRIDE_QUERY, self.cands, k=4,
                                 stats=self.stats, cooc=self.cooc)
        self.assertEqual(out[0].text, BELIEF_PRIDE)
        self.assertGreater(out[0].score, out[1].score)


if __name__ == "__main__":
    unittest.main()
