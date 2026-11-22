"""v0.31: the source-backed vocabulary notebook (NLTK plan Phase 1).

Pins, in order: synset choice is a deterministic pure function
(POS-filtered first match, tagger-slip fallback); provenance sentences
match the source passage byte-for-byte; graduation fires exactly on
the third DISTINCT source and hers-marking fires when she generates
the word; the notebook round-trips a restart and continues identically
from a snapshot; generation (dream pools, verse slots) draws known /
hers words first; and the heuristic gate — with the heuristic backend
the notebook is never fed, never marked, never saved, so a heuristic
life stays bit-identical.

Isolation: in-memory stores via set_store and a temp AETHEL_HOME for
every organism built here — her live diary is never instantiated
against. (The pre-sqlite config.STATE / journal.JOURNAL knobs this
repo's older notes describe no longer exist; set_store + temp home
is the harness every current test file uses.) Notebook unit tests run
on a fake WordNet so they need no NLTK data; organism integration
tests use the real backend and skip when it is not provisioned.
"""
import contextlib
import io
import os
import tempfile
import unittest
from unittest.mock import patch

import aethel_pkg.journal as journal_mod
import aethel_pkg.organism as org_mod
from aethel_pkg import config
from aethel_pkg.config import STOPWORDS
from aethel_pkg.journal import get_store, set_store
from aethel_pkg.language import Analysis, Token
from aethel_pkg.notebook import KNOWN, HERS, PRESSED, Notebook, choose_synset
from aethel_pkg.organism import Aethel
from aethel_pkg.rng import Streams
from aethel_pkg.store import Store

from helpers import StubWorld


# ---------------------------------------------------------------- fakes
class FakeSynset:
    def __init__(self, name, definition, examples=()):
        self._name, self._def, self._ex = name, definition, list(examples)

    def name(self):
        return self._name

    def definition(self):
        return self._def

    def examples(self):
        return list(self._ex)


class FakeWordNet:
    """lemma -> {pos letter: [synsets in frequency order]}."""

    def __init__(self, table):
        self.table = table

    def synsets(self, lemma, pos=None):
        senses = self.table.get(lemma, {})
        if pos is not None:
            return list(senses.get(pos, []))
        out = []
        for p in ("n", "v", "a", "r"):
            out.extend(senses.get(p, []))
        return out


WORDNET = FakeWordNet(
    {
        "whale": {
            "n": [
                FakeSynset("giant.n.04", "a very large person"),
                FakeSynset(
                    "whale.n.02",
                    "any of the larger cetacean mammals",
                    ["the whale surfaced at dawn"],
                ),
            ]
        },
        "record": {
            "n": [FakeSynset("record.n.01", "a documented account")],
            "v": [FakeSynset("record.v.01", "to register information")],
        },
        "lantern": {
            "n": [FakeSynset("lantern.n.01", "a portable lamp with a case")]
        },
        "swim": {"v": [FakeSynset("swim.v.01", "to propel the body in water")]},
    }
)


def is_content(token):
    """The content rule, restated over fake tokens (the real one is
    NltkLanguage.content; STOPWORDS reuse is the shared half)."""
    return (
        bool(token.pos)
        and token.pos.startswith(("NN", "VB", "JJ", "RB"))
        and token.text.isalpha()
        and len(token.text) >= 2
        and token.text.lower() not in STOPWORDS
        and token.lemma not in STOPWORDS
    )


def make_analysis(sentences, specs):
    """Build an Analysis with true offsets. `specs` are
    (surface, lemma, pos) in order of appearance."""
    text = " ".join(sentences)
    spans, cursor = [], 0
    for s in sentences:
        i = text.index(s, cursor)
        spans.append((i, i + len(s)))
        cursor = i + len(s)
    tokens, cursor = [], 0
    for surface, lemma, pos in specs:
        start = text.index(surface, cursor)
        tokens.append(Token(surface, start, start + len(surface), lemma, pos))
        cursor = start + len(surface)
    return Analysis(text, tuple(spans), tuple(tokens))


def whale_passage(source_word="harbor"):
    sentences = [
        "The captain kept a lantern by the door.",
        f"A whale surfaced beyond the {source_word} at dawn.",
    ]
    specs = [
        ("captain", "captain", "NN"),
        ("kept", "keep", "VBD"),
        ("lantern", "lantern", "NN"),
        ("door", "door", "NN"),
        ("whale", "whale", "NN"),
        ("surfaced", "surface", "VBD"),
        (source_word, source_word, "NN"),
        ("dawn", "dawn", "NN"),
    ]
    return sentences, make_analysis(sentences, specs)


# ------------------------------------------------------- synset choice
class TestSynsetChoice(unittest.TestCase):
    def test_pos_filter_picks_the_matching_sense(self):
        # Unfiltered, "record" the noun outranks the verb; the token's
        # POS must steer the choice, not raw frequency.
        self.assertEqual(
            choose_synset(WORDNET, "record", "NN")[0], "a documented account"
        )
        self.assertEqual(
            choose_synset(WORDNET, "record", "VBP")[0],
            "to register information",
        )

    def test_first_match_is_the_frequent_sense(self):
        definition, example, name = choose_synset(WORDNET, "whale", "NN")
        self.assertEqual(name, "giant.n.04")
        self.assertEqual(definition, "a very large person")
        self.assertIsNone(example)

    def test_tagger_slip_falls_back_to_first_synset(self):
        # "whale" mistagged JJ has no adjective synset; the word must
        # not lose its gloss over the slip.
        self.assertEqual(choose_synset(WORDNET, "whale", "JJ")[2], "giant.n.04")

    def test_unknown_word_and_missing_reader_are_honest_nones(self):
        self.assertEqual(choose_synset(WORDNET, "quokka", "NN"), (None, None, None))
        self.assertEqual(choose_synset(None, "whale", "NN"), (None, None, None))

    def test_choice_is_deterministic(self):
        self.assertEqual(
            choose_synset(WORDNET, "record", "VBD"),
            choose_synset(WORDNET, "record", "VBD"),
        )


# ------------------------------------------------------------ feeding
class TestFeed(unittest.TestCase):
    def test_entry_shape_and_provenance_byte_for_byte(self):
        sentences, analysis = whale_passage()
        nb = Notebook()
        events = nb.feed(analysis, "classic", 1234, WORDNET, is_content)
        entry = nb.get("whale")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["first_form"], "whale")
        self.assertEqual(entry["pos"], "NN")
        self.assertEqual(entry["definition"], "a very large person")
        self.assertEqual(entry["synset"], "giant.n.04")
        self.assertEqual(entry["sources"], ["classic"])
        self.assertEqual(entry["met_count"], 1)
        self.assertEqual(entry["status"], PRESSED)
        prov = entry["provenance"]
        self.assertEqual(prov["source"], "classic")
        self.assertEqual(prov["tick"], 1234)
        # Byte-for-byte: the quoted sentence is exactly the passage's
        # second sentence, and exactly the analysis's span slice.
        self.assertEqual(prov["sentence"], sentences[1])
        start, end = analysis.sentences[1]
        self.assertEqual(prov["sentence"], analysis.text[start:end])
        self.assertIn(("notebook_pressed", entry), events)

    def test_first_form_keeps_the_surface_as_met(self):
        sentences = ["Whale songs carry far."]
        analysis = make_analysis(
            sentences,
            [("Whale", "whale", "NN"), ("songs", "song", "NNS"),
             ("carry", "carry", "VB"), ("far", "far", "RB")],
        )
        nb = Notebook()
        nb.feed(analysis, "wikipedia", 7, WORDNET, is_content)
        self.assertEqual(nb.get("whale")["first_form"], "Whale")

    def test_non_content_tokens_are_not_pressed(self):
        sentences = ["The whale and the door."]
        analysis = make_analysis(
            sentences,
            [("The", "the", "DT"), ("whale", "whale", "NN"),
             ("and", "and", "CC"), ("the", "the", "DT"),
             ("door", "door", "NN")],
        )
        nb = Notebook()
        nb.feed(analysis, "classic", 1, WORDNET, is_content)
        self.assertNotIn("the", nb)
        self.assertNotIn("and", nb)
        self.assertIn("whale", nb)

    def test_met_count_counts_passages_not_token_hits(self):
        sentences = ["Whale, whale, whale."]
        analysis = make_analysis(
            sentences,
            [("Whale", "whale", "NN"), ("whale", "whale", "NN"),
             ("whale", "whale", "NN")],
        )
        nb = Notebook()
        nb.feed(analysis, "classic", 1, WORDNET, is_content)
        self.assertEqual(nb.get("whale")["met_count"], 1)
        nb.feed(analysis, "classic", 2, WORDNET, is_content)
        self.assertEqual(nb.get("whale")["met_count"], 2)
        self.assertEqual(nb.get("whale")["sources"], ["classic"])

    def test_same_passage_twice_identical_notebook(self):
        _, analysis = whale_passage()
        nb1, nb2 = Notebook(), Notebook()
        nb1.feed(analysis, "classic", 5, WORDNET, is_content)
        nb2.feed(analysis, "classic", 5, WORDNET, is_content)
        self.assertEqual(nb1.to_dict(), nb2.to_dict())


# --------------------------------------------------------- graduation
class TestGraduation(unittest.TestCase):
    def _feed_source(self, nb, source, tick):
        _, analysis = whale_passage()
        return nb.feed(analysis, source, tick, WORDNET, is_content)

    def test_known_fires_exactly_on_third_distinct_source(self):
        def known_for(events, lemma="whale"):
            return [
                n for n, e in events
                if n == "notebook_known" and e["lemma"] == lemma
            ]

        nb = Notebook()
        self._feed_source(nb, "classic", 1)
        events = self._feed_source(nb, "classic", 2)  # same source again
        self.assertEqual(nb.get("whale")["status"], PRESSED)
        self.assertEqual(known_for(events), [])
        events = self._feed_source(nb, "wikipedia", 3)  # second distinct
        self.assertEqual(nb.get("whale")["status"], PRESSED)
        self.assertEqual(known_for(events), [])
        events = self._feed_source(nb, "university", 4)  # third distinct
        self.assertEqual(nb.get("whale")["status"], KNOWN)
        self.assertEqual(len(known_for(events)), 1)
        events = self._feed_source(nb, "newsroom", 5)  # no re-firing
        self.assertEqual(known_for(events), [])
        self.assertEqual(nb.get("whale")["status"], KNOWN)

    def test_hers_marking_and_terminality(self):
        nb = Notebook()
        self._feed_source(nb, "classic", 1)
        out = nb.mark_hers({"whale", "neverseen"})
        self.assertEqual([e["lemma"] for e in out], ["whale"])
        self.assertEqual(nb.get("whale")["status"], HERS)
        self.assertNotIn("neverseen", nb)  # no retroactive pressing
        self.assertEqual(nb.mark_hers({"whale"}), [])  # already hers
        # Further breadth never demotes hers, and no known event
        # fires for the hers word itself.
        self._feed_source(nb, "wikipedia", 2)
        events = self._feed_source(nb, "university", 3)
        self.assertEqual(nb.get("whale")["status"], HERS)
        self.assertFalse(
            any(
                n == "notebook_known" and e["lemma"] == "whale"
                for n, e in events
            )
        )

    def test_usable_words_hers_first_then_alphabetical(self):
        nb = Notebook()
        for src in ("a", "b", "c"):
            self._feed_source(nb, src, 1)
        # The whole passage graduated; hers must still lead, and the
        # known remainder must be alphabetical (a pure function of
        # the notebook, no randomness in what she may say).
        nb.mark_hers({"whale"})
        self.assertEqual(
            nb.usable_words(),
            ["whale", "captain", "dawn", "door", "harbor", "lantern",
             "surface"],
        )
        self.assertEqual(
            nb.usable_words(statuses=(KNOWN,)),
            ["captain", "dawn", "door", "harbor", "lantern", "surface"],
        )


# --------------------------------------------------------- persistence
class TestPersistence(unittest.TestCase):
    def test_round_trip_through_restart(self):
        nb = Notebook()
        for src in ("classic", "wikipedia", "university"):
            _, analysis = whale_passage()
            nb.feed(analysis, src, 9, WORDNET, is_content)
        nb.mark_hers({"lantern"})
        blob = nb.to_dict()
        rebuilt = Notebook.from_dict(blob)
        self.assertEqual(rebuilt.to_dict(), blob)
        self.assertEqual(rebuilt.get("whale")["status"], KNOWN)
        self.assertEqual(rebuilt.get("lantern")["status"], HERS)
        self.assertEqual(
            rebuilt.get("whale")["provenance"]["sentence"],
            nb.get("whale")["provenance"]["sentence"],
        )

    def test_continuation_from_snapshot_matches_uninterrupted(self):
        _, analysis = whale_passage()
        live = Notebook()
        live.feed(analysis, "classic", 1, WORDNET, is_content)
        snap = live.to_dict()
        rebuilt = Notebook.from_dict(snap)
        for nb in (live, rebuilt):
            nb.feed(analysis, "wikipedia", 2, WORDNET, is_content)
            nb.feed(analysis, "university", 3, WORDNET, is_content)
        self.assertEqual(live.to_dict(), rebuilt.to_dict())
        self.assertEqual(live.get("whale")["status"], KNOWN)

    def test_malformed_rows_are_skipped_not_fatal(self):
        nb = Notebook.from_dict(
            {"entries": {"whale": {"status": "bogus", "met_count": "x"},
                         "door": {"status": "known", "met_count": 2}}}
        )
        self.assertNotIn("whale", nb)
        self.assertEqual(nb.get("door")["status"], KNOWN)


# ------------------------------------------------- organism, fake NLP
class FakeLang:
    """Minimal NLTK-shaped backend for bare-organism tests."""

    def __init__(self, name="nltk"):
        self.name = name
        self.wordnet = WORDNET

    def analyze(self, text):
        import re as _re

        tokens, sentences = [], []
        cursor = 0
        for m in _re.finditer(r"[^.!?]+[.!?]?", text):
            sentences.append((m.start(), m.end()))
        for m in _re.finditer(r"[A-Za-z]+", text):
            tokens.append(
                Token(m.group(), m.start(), m.end(), m.group().lower(), "NN")
            )
        return Analysis(text, tuple(sentences), tuple(tokens))

    def content(self, token):
        return is_content(token)


def make_bare(language=None, seed=42):
    # The caller's setUp owns the store (set_store(Store(":memory:")));
    # building her must not swap it out from under the assertions.
    a = Aethel.__new__(Aethel)
    a.world = StubWorld()
    a.parents = {"Donald", "Cassandra"}
    a.seed = seed
    a.streams = Streams(seed)
    a.rng = a.streams.stream("organism")
    a.rng_dreams = a.streams.stream("dreams")
    a.rng_forage = a.streams.stream("forage")
    a.concepts = {}
    a.beliefs = []
    a.dreams = []
    a._sleep_dreams = []
    a.cooc = {}
    a.kept_passages = []
    a.days = []
    a.tick_count = 100
    a.impressions = {}
    a.language = language if language is not None else FakeLang()
    return a


class TestOrganismSeamsFakeNlp(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def test_feed_journals_pressed_with_provenance_fields(self):
        a = make_bare()
        _, analysis = whale_passage()
        a._notebook_feed(analysis, analysis.tokens, "classic")
        self.assertIn("whale", a._notebook())
        rows = self.store.recent(events=("notebook_pressed",))
        lemmas = {d["lemma"] for _, _, d in rows}
        self.assertIn("whale", lemmas)
        whale_row = next(d for _, _, d in rows if d["lemma"] == "whale")
        self.assertEqual(whale_row["source"], "classic")
        self.assertEqual(whale_row["synset"], "giant.n.04")

    def test_mark_generated_journals_hers(self):
        a = make_bare()
        _, analysis = whale_passage()
        a._notebook_feed(analysis, analysis.tokens, "classic")
        a._notebook_mark_generated("The whale returned.", via="dream")
        self.assertEqual(a._notebook().get("whale")["status"], HERS)
        rows = self.store.recent(events=("notebook_hers",))
        self.assertEqual([(d["lemma"], d["via"]) for _, _, d in rows],
                         [("whale", "dream")])

    def _whale_only_notebook(self):
        """A notebook whose only graduate is 'whale', so pool and
        verse assertions name exactly the word that must lead."""
        nb = Notebook()
        sentences = ["A whale surfaced."]
        analysis = make_analysis(sentences, [("whale", "whale", "NN")])
        for src in ("classic", "wikipedia", "university"):
            nb.feed(analysis, src, 1, WORDNET, is_content)
        self.assertEqual(nb.get("whale")["status"], KNOWN)
        return nb

    def test_dream_pools_augmented_hers_first(self):
        a = make_bare()
        a._vocab_notebook = self._whale_only_notebook()
        pools = {"concrete": ["stone"], "abstract": ["sorrow"]}
        legacy = ["stone", "sorrow"]
        out = a._notebook_augment_pools(pools, legacy)
        self.assertEqual(pools["concrete"][0], "whale")
        self.assertEqual(out[0], "whale")
        self.assertIn("stone", out)

    def test_verse_slots_prefer_notebook_words(self):
        class StubRng:
            def choice(self, seq):
                return "verse" if "verse" in seq else seq[0]

            def randbelow(self, n):
                return 0

        a = make_bare()
        a._vocab_notebook = self._whale_only_notebook()
        a.rng = StubRng()
        verse = a._compose_note(["course"], "the Library", "a book", "everything")
        self.assertIn("I held whale in my palm", verse)

    def test_heuristic_bare_organism_is_untouched(self):
        a = make_bare(language=FakeLang(name="heuristic"))
        _, analysis = whale_passage()
        a._notebook_feed(analysis, analysis.tokens, "classic")
        a._notebook_mark_generated("The whale returned.", via="dream")
        self.assertEqual(len(a._notebook()), 0)
        pools = {"concrete": ["stone"]}
        out = a._notebook_augment_pools(pools, ["stone"])
        self.assertEqual(out, ["stone"])
        self.assertEqual(pools, {"concrete": ["stone"]})
        self.assertEqual(
            self.store.recent(
                events=("notebook_pressed", "notebook_known", "notebook_hers")
            ),
            [],
        )


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

    def test_heuristic_life_never_touches_the_notebook(self):
        meal = {
            "source": "wikipedia",
            "title": "Fixture",
            "text": "The whale surfaced beyond the harbor at dawn. "
                    "The captain kept a lantern by the door.",
        }
        a = Aethel(StubWorld(), parents=("Donald",), seed=42,
                   language_backend="heuristic")
        boom = AssertionError("notebook touched in heuristic mode")
        with patch.object(Notebook, "feed", side_effect=boom), \
                patch.object(Notebook, "mark_hers", side_effect=boom), \
                contextlib.redirect_stdout(io.StringIO()):
            with patch.object(a, "forage_classic", return_value=meal), \
                    patch.object(org_mod, "forage", return_value=meal), \
                    patch.object(org_mod, "forage_news", return_value=meal), \
                    patch.object(org_mod, "forage_school", return_value=meal):
                a.forage_and_eat()
            a.dream()
        a.save()
        blob = self.store.load_blob("state")
        self.assertNotIn("notebook", blob)
        self.assertEqual(
            self.store.recent(
                events=("notebook_pressed", "notebook_known", "notebook_hers")
            ),
            [],
        )


# ------------------------------------------- real-backend integration
class TestNotebookIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from aethel_pkg.language import NltkLanguage
        from aethel_pkg.language_resources import LanguageError

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

    def organism(self):
        return Aethel(StubWorld(), parents=("Donald",), seed=42,
                      language_backend="nltk")

    PASSAGE = (
        "The captain kept a brass lantern beside the chart table. "
        "Beyond the harbor, a whale surfaced and breathed, and the "
        "whole crew fell silent to watch it."
    )

    def test_meal_presses_words_with_byte_exact_provenance(self):
        a = self.organism()
        analysis = self.backend.analyze(self.PASSAGE)
        tokens = [t for t in analysis.tokens if self.backend.content(t)]
        with contextlib.redirect_stdout(io.StringIO()):
            a._notebook_feed(analysis, tokens, "classic")
        nb = a._notebook()
        self.assertGreater(len(nb), 3)
        for lemma in ("lantern", "whale", "harbor"):
            self.assertIn(lemma, nb)
            entry = nb.get(lemma)
            sentence = entry["provenance"]["sentence"]
            # The quote is a verbatim slice of the passage she read.
            self.assertIn(sentence, self.PASSAGE)
            self.assertTrue(sentence.endswith("."))
            self.assertEqual(entry["provenance"]["source"], "classic")
            self.assertEqual(entry["status"], PRESSED)
        self.assertTrue(nb.get("whale")["definition"])
        rows = self.store.recent(events=("notebook_pressed",))
        self.assertEqual({d["lemma"] for _, _, d in rows}, set(nb.entries))

    def test_graduation_and_hers_through_the_seams(self):
        a = self.organism()
        analysis = self.backend.analyze(self.PASSAGE)
        tokens = [t for t in analysis.tokens if self.backend.content(t)]
        with contextlib.redirect_stdout(io.StringIO()):
            for src in ("classic", "wikipedia"):
                a._notebook_feed(analysis, tokens, src)
            self.assertEqual(a._notebook().get("whale")["status"], PRESSED)
            a._notebook_feed(analysis, tokens, "university")
            self.assertEqual(a._notebook().get("whale")["status"], KNOWN)
            a._notebook_mark_generated(
                "I dreamed the whale came back to the harbor.",
                via="dream",
            )
        self.assertEqual(a._notebook().get("whale")["status"], HERS)
        kinds = {e for _, e, _ in self.store.recent(
            events=("notebook_pressed", "notebook_known", "notebook_hers"))}
        self.assertEqual(
            kinds, {"notebook_pressed", "notebook_known", "notebook_hers"}
        )

    def test_notebook_round_trip_through_simulated_restart(self):
        a = self.organism()
        analysis = self.backend.analyze(self.PASSAGE)
        tokens = [t for t in analysis.tokens if self.backend.content(t)]
        with contextlib.redirect_stdout(io.StringIO()):
            a._notebook_feed(analysis, tokens, "classic")
        a.save()
        before = a._notebook().to_dict()
        self.assertEqual(self.store.load_blob("state")["notebook"], before)
        rebuilt = self.organism()
        self.assertEqual(rebuilt._notebook().to_dict(), before)

    def test_nltk_life_restart_is_continuation_not_rebirth(self):
        """A seeded NLTK life stopped mid-run, rebuilt, and continued
        must match the uninterrupted life — journal and state blob,
        notebook included. This is the restart-fidelity gate for the
        state shape this phase adds."""
        meals = {
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
                    "text": meals[source]}

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
        # Sanity: the life actually used the notebook (words pressed,
        # at least one graduation) — otherwise the gate proves nothing.
        events = [e for _, e, _ in interrupted["journal"]]
        self.assertIn("notebook_pressed", events)
        self.assertIn("notebook", uninterrupted["state"])
        self.assertGreater(
            len(uninterrupted["state"]["notebook"]["entries"]), 3
        )
        self.assertEqual(interrupted, uninterrupted)

    def test_synset_selection_deterministic_across_notebooks(self):
        analysis = self.backend.analyze(self.PASSAGE)
        dicts = []
        for _ in range(2):
            nb = Notebook()
            nb.feed(
                analysis,
                "classic",
                3,
                wordnet=self.backend.wordnet,
                is_content=self.backend.content,
            )
            dicts.append(nb.to_dict())
        self.assertEqual(dicts[0], dicts[1])


if __name__ == "__main__":
    unittest.main()
