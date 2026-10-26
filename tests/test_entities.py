"""v0.34: entity recognition, Route A (NLTK plan Phase 3).

Pins, in order: proper-noun phrase extraction with byte-for-byte
spans and the sentence-initial rule (POS is the first witness; a
gazetteer match rescues a known name the tagger called NN; the
WordNet common-lemma check rejects a common noun the tagger
promoted for standing first; corroboration rescues a name that
also appears mid-sentence); gazetteer seed determinism from her
world data; growth exactly at the second DISTINCT source; truthful
entity_met counts (the third meeting says "third"); belief links
in the Phase 2 candidate-id scheme; restart fidelity, including the
seeded 260-tick NLTK life; and the heuristic gate — entity code is
never invoked, never journaled, never saved in heuristic mode.

Precision fixtures are real public-domain excerpts in the style and
length of her classic-book reading (Pride and Prejudice; A Christmas
Carol and Bleak House by Dickens), run against the real backend and
skipped when NLTK data is not provisioned.

Isolation: in-memory stores via set_store and a temp AETHEL_HOME for
every organism built here — her live diary is never instantiated
against.
"""

import contextlib
import io
import os
import tempfile
import unittest
from unittest.mock import patch

import aethel_pkg.organism as org_mod
from aethel_pkg import config
from aethel_pkg.entities import (
    Gazetteer,
    belief_link,
    extract_phrases,
    normalize,
    ordinal,
    seed_entries,
)
from aethel_pkg.journal import set_store
from aethel_pkg.language import Analysis, Token
from aethel_pkg.organism import Aethel
from aethel_pkg.recall import candidate_id
from aethel_pkg.rng import Streams
from aethel_pkg.store import Store

from helpers import StubWorld


# ---------------------------------------------------------------- fakes
class FakeLemma:
    def __init__(self, name):
        self.name = name


class FakeSynset:
    def __init__(self, lemma_names):
        self._lemmas = [FakeLemma(n) for n in lemma_names]

    def lemmas(self):
        return list(self._lemmas)


class FakeWordNet:
    """lemma -> synsets. Common words carry a lowercase lemma spelled
    exactly like the surface; proper names carry capitalized ones —
    the distinction the sentence-initial check reads."""

    TABLE = {
        "happiness": [FakeSynset(["happiness", "felicity"])],
        "fog": [FakeSynset(["fog"])],
        "scrooge": [FakeSynset(["niggard", "scrooge"])],
        "marley": [FakeSynset(["Marley", "Bob_Marley"])],
        "elizabeth": [FakeSynset(["Elizabeth", "Elizabeth_I"])],
        "dickens": [FakeSynset(["Dickens", "Charles_Dickens"])],
    }

    def synsets(self, lemma, pos=None):
        return list(self.TABLE.get(str(lemma).lower(), []))


FAKE_WN = FakeWordNet()


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


def austen_fake(happiness_pos="NN"):
    sentences = [
        "Elizabeth Bennet had been obliged to sit down for two dances.",
        "Mr. Darcy danced only once more with her.",
        "Happiness was entirely a matter of chance.",
    ]
    specs = [
        ("Elizabeth", "elizabeth", "NNP"),
        ("Bennet", "bennet", "NNP"),
        ("had", "have", "VBD"),
        ("been", "be", "VBN"),
        ("obliged", "oblige", "VBN"),
        ("to", "to", "TO"),
        ("sit", "sit", "VB"),
        ("down", "down", "RP"),
        ("for", "for", "IN"),
        ("two", "two", "CD"),
        ("dances", "dance", "NNS"),
        ("Mr.", "mr.", "NNP"),
        ("Darcy", "darcy", "NNP"),
        ("danced", "dance", "VBD"),
        ("only", "only", "RB"),
        ("once", "once", "RB"),
        ("more", "more", "RBR"),
        ("with", "with", "IN"),
        ("her", "her", "PRP"),
        ("Happiness", "happiness", happiness_pos),
        ("was", "be", "VBD"),
        ("entirely", "entirely", "RB"),
        ("a", "a", "DT"),
        ("matter", "matter", "NN"),
        ("of", "of", "IN"),
        ("chance", "chance", "NN"),
    ]
    return make_analysis(sentences, specs)


class FakeLang:
    """Minimal NLTK-shaped backend for the organism seam: the seam
    receives Analysis objects built by the tests; the language only
    supplies the _nlp gate, the WordNet reader, and analyze() for
    belief-text scans."""

    def __init__(self, name="nltk"):
        self.name = name
        self.wordnet = FAKE_WN

    def analyze(self, text):
        import re as _re

        sentences = [(m.start(), m.end()) for m in _re.finditer(r"[^.!?]+[.!?]?", text)]
        tokens = tuple(
            Token(m.group(), m.start(), m.end(), m.group().lower(), "NN")
            for m in _re.finditer(r"[A-Za-z]+", text)
        )
        return Analysis(text, tuple(sentences), tokens)


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
    a.lemma_index = {}  # v0.37: every real NLTK organism carries one
    # (set by _init_language_knowledge in __init__); Phase 6a's
    # belief-settling cooc hook reads concept counts through it.
    a.beliefs = []
    a.dreams = []
    a.memory = []
    a.kept_passages = []
    a.cooc = {}
    a.tick_count = 100
    a.impressions = {}
    a.company = []
    a.open_questions = []
    a.reading_list = []
    a.moral_log = []
    a.longing = 0.0
    a.vitals = {
        "satiety": 0.8,
        "hydration": 0.8,
        "oxygen": 1.0,
        "vitality": 0.8,
        "excitement": 0.0,
    }
    a.language = language if language is not None else FakeLang()
    return a


# ------------------------------------------------------------- extraction
class TestExtraction(unittest.TestCase):
    def setUp(self):
        self.gaz = Gazetteer.seeded()
        self.known = self.gaz.match_keys()

    def test_phrases_and_spans_byte_for_byte(self):
        analysis = austen_fake()
        phrases = extract_phrases(analysis, self.known, FAKE_WN)
        names = [p["name"] for p in phrases]
        self.assertEqual(names, ["Elizabeth Bennet", "Mr. Darcy"])
        for p in phrases:
            self.assertEqual(analysis.text[p["start"] : p["end"]], p["name"])
        self.assertTrue(phrases[0]["sentence_initial"])

    def test_sentence_initial_common_noun_tagged_nn_not_promoted(self):
        phrases = extract_phrases(austen_fake("NN"), self.known, FAKE_WN)
        self.assertNotIn("Happiness", [p["name"] for p in phrases])

    def test_sentence_initial_common_noun_mistagged_nnp_rejected(self):
        # The real tagger calls "Happiness" NNP at a sentence start;
        # the WordNet common-lemma check must still refuse it.
        phrases = extract_phrases(austen_fake("NNP"), self.known, FAKE_WN)
        self.assertNotIn("Happiness", [p["name"] for p in phrases])

    def test_sentence_initial_nn_gazetteer_match_rescued(self):
        sentences = ["Dickens wrote of London for years."]
        specs = [
            ("Dickens", "dickens", "NN"),
            ("wrote", "write", "VBD"),
            ("of", "of", "IN"),
            ("London", "london", "NNP"),
            ("for", "for", "IN"),
            ("years", "year", "NNS"),
        ]
        phrases = extract_phrases(make_analysis(sentences, specs), self.known, FAKE_WN)
        self.assertEqual([p["name"] for p in phrases], ["Dickens", "London"])

    def test_initial_proper_name_with_capitalized_lemma_accepted(self):
        sentences = ["Marley was dead, to begin with."]
        specs = [
            ("Marley", "marley", "NNP"),
            ("was", "be", "VBD"),
            ("dead", "dead", "JJ"),
            ("to", "to", "TO"),
            ("begin", "begin", "VB"),
            ("with", "with", "IN"),
        ]
        phrases = extract_phrases(make_analysis(sentences, specs), self.known, FAKE_WN)
        self.assertEqual([p["name"] for p in phrases], ["Marley"])

    def test_corroboration_rescues_common_spelled_name(self):
        # "scrooge" is a common noun in WordNet, but the passage also
        # uses Scrooge mid-sentence, where the capital means something.
        sentences = [
            "Scrooge signed it.",
            "And Scrooge's name was good upon the Exchange.",
        ]
        specs = [
            ("Scrooge", "scrooge", "NNP"),
            ("signed", "sign", "VBD"),
            ("it", "it", "PRP"),
            ("And", "and", "CC"),
            ("Scrooge", "scrooge", "NNP"),
            ("name", "name", "NN"),
            ("was", "be", "VBD"),
            ("good", "good", "JJ"),
            ("upon", "upon", "IN"),
            ("the", "the", "DT"),
            ("Exchange", "exchange", "NNP"),
        ]
        phrases = extract_phrases(make_analysis(sentences, specs), self.known, FAKE_WN)
        self.assertEqual(
            [p["name"] for p in phrases], ["Scrooge", "Scrooge", "Exchange"]
        )

    def test_punctuation_token_tagged_proper_is_not_an_entity(self):
        # Found live on her first v0.34 newsroom meal: the tagger
        # calls a stray quote mark NNP, and an unguarded run would
        # christen an entity named '""'.
        sentences = ['He said "" and left for London.']
        specs = [
            ("He", "he", "PRP"),
            ("said", "say", "VBD"),
            ('""', '""', "NNP"),
            ("and", "and", "CC"),
            ("left", "leave", "VBD"),
            ("for", "for", "IN"),
            ("London", "london", "NNP"),
        ]
        phrases = extract_phrases(make_analysis(sentences, specs), self.known, FAKE_WN)
        self.assertEqual([p["name"] for p in phrases], ["London"])

    def test_ordinal_words_and_suffixes(self):
        self.assertEqual(
            [ordinal(n) for n in (1, 2, 3, 4, 11, 12)],
            ["first", "second", "third", "fourth", "eleventh", "twelfth"],
        )
        self.assertEqual(
            [ordinal(n) for n in (21, 22, 23, 24)], ["21st", "22nd", "23rd", "24th"]
        )


# ------------------------------------------------------------------- seed
class TestSeed(unittest.TestCase):
    def test_seed_contents_by_kind(self):
        rows = seed_entries()
        by_kind = {}
        for r in rows:
            by_kind.setdefault(r["kind"], []).append(r["name"])
        # The cast stays pinned on purpose: a denizen joining or
        # leaving is a canon decision, and this test is where it must
        # be acknowledged, not absorbed.
        self.assertEqual(
            sorted(by_kind["person"]),
            ["Cassandra", "Donald", "John", "Julius", "Octavia", "Star", "Trey"],
        )
        self.assertIn("the Library", by_kind["place"])
        # Places and authors are DERIVED from their sources of truth
        # (town_pkg.places.PLACES, config.CLASSIC_SEEDS), replaying
        # the seed's own rule: first occurrence wins on the
        # normalized key, across kinds, in seed order. Both
        # registries grow by design, and a pinned census broke on
        # exactly that growth twice in spirit (33 rows before the
        # v0.40 classics restock, 36 after, the count re-pinned by
        # hand each time) with nothing actually wrong. A derived
        # expectation cannot drift from the registries it checks.
        from town_pkg.places import PLACES

        seen = {normalize(name) for name in by_kind["person"]}

        def replay(names):
            out = []
            for name in names:
                key = normalize(name)
                if key and key not in seen:
                    seen.add(key)
                    out.append(name)
            return out

        expected_places = replay(list(PLACES.values()))
        expected_authors = replay(
            [book["author"] for book in config.CLASSIC_SEEDS if book.get("author")]
        )
        self.assertEqual(by_kind["place"], expected_places)
        self.assertEqual(by_kind["author"], expected_authors)
        self.assertEqual(
            len(rows),
            len(by_kind["person"]) + len(expected_places) + len(expected_authors),
        )
        for author in ("Charles Dickens", "Jane Austen", "Leo Tolstoy"):
            self.assertIn(author, by_kind["author"])
        self.assertTrue(all(r["origin"] == "world" for r in rows))

    def test_seed_determinism_and_idempotent_rebuild(self):
        first = Gazetteer.seeded().to_dict()
        second = Gazetteer.seeded().to_dict()
        self.assertEqual(first, second)
        rebuilt = Gazetteer.from_dict(first).to_dict()
        self.assertEqual(rebuilt, first)

    def test_unique_surname_matches_shared_surname_does_not(self):
        gaz = Gazetteer.seeded()
        self.assertEqual(gaz.get("Dickens")["name"], "Charles Dickens")
        self.assertEqual(gaz.get("Austen")["name"], "Jane Austen")
        self.assertIsNone(gaz.get("Brontë"))
        self.assertEqual(gaz.get("Library")["name"], "the Library")
        self.assertIsNone(gaz.get("Heathcliff"))


# ----------------------------------------------------------------- growth
def heathcliff_analysis():
    sentences = ["Heathcliff glowered at the moor."]
    specs = [
        ("Heathcliff", "heathcliff", "NNP"),
        ("glowered", "glower", "VBD"),
        ("at", "at", "IN"),
        ("the", "the", "DT"),
        ("moor", "moor", "NN"),
    ]
    return make_analysis(sentences, specs)


class TestGrowth(unittest.TestCase):
    def test_two_distinct_sources_promote_one_source_never_does(self):
        gaz = Gazetteer.seeded()
        analysis = heathcliff_analysis()
        out = gaz.feed(analysis, "classic", 1)
        self.assertEqual(out["met"], [])
        self.assertEqual([s["name"] for s in out["seen"]], ["Heathcliff"])
        self.assertIsNone(gaz.get("Heathcliff"))
        # Many sightings in the SAME source still do not promote.
        for tick in (2, 3, 4):
            gaz.feed(analysis, "classic", tick)
        self.assertIsNone(gaz.get("Heathcliff"))
        out = gaz.feed(analysis, "wikipedia", 5)
        self.assertEqual([l["name"] for l in out["learned"]], ["Heathcliff"])
        entry = gaz.get("Heathcliff")
        self.assertEqual(entry["kind"], "unknown")
        self.assertEqual(entry["origin"], "growth")
        self.assertEqual(entry["sources"], ["classic", "wikipedia"])
        # The promotion reading is its first met.
        self.assertEqual(out["met"], [{"name": "Heathcliff", "count": 1}])
        self.assertEqual(entry["met_count"], 1)

    def test_candidate_tracking_round_trips_restart(self):
        gaz = Gazetteer.seeded()
        gaz.feed(heathcliff_analysis(), "classic", 1)
        snap = gaz.to_dict()
        rebuilt = Gazetteer.from_dict(snap)
        self.assertEqual(rebuilt.to_dict(), snap)
        out = rebuilt.feed(heathcliff_analysis(), "wikipedia", 2)
        self.assertEqual([l["name"] for l in out["learned"]], ["Heathcliff"])


# ------------------------------------------------------------ organism seam
def dickens_analysis():
    sentences = ["Dickens wrote of London, and London answered him."]
    specs = [
        ("Dickens", "dickens", "NNP"),
        ("wrote", "write", "VBD"),
        ("of", "of", "IN"),
        ("London", "london", "NNP"),
        ("and", "and", "CC"),
        ("London", "london", "NNP"),
        ("answered", "answer", "VBD"),
        ("him", "him", "PRP"),
    ]
    return make_analysis(sentences, specs)


class TestOrganismSeam(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def test_entity_met_events_and_truthful_third_time(self):
        a = make_bare()
        analysis = dickens_analysis()
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            for _ in range(3):
                a._entities_feed(analysis, "classic")
        rows = self.store.recent(events=("entity_met",), limit=10)
        self.assertEqual(len(rows), 3)
        counts = [d["counts"] for _, _, d in reversed(rows)]
        self.assertEqual(
            counts,
            [{"Charles Dickens": 1}, {"Charles Dickens": 2}, {"Charles Dickens": 3}],
        )
        for _, _, d in rows:
            self.assertEqual(d["entities"], ["Charles Dickens"])
            self.assertEqual(d["source"], "classic")
        # London was tracked as an unknown sighting each time, never
        # silently met: it is not in the gazetteer yet.
        seen = self.store.recent(events=("entity_seen",), limit=10)
        self.assertEqual({d["entity"] for _, _, d in seen}, {"London"})
        out = buf.getvalue()
        self.assertIn("Charles Dickens again", out)
        self.assertIn("second time", out)
        self.assertIn("third time", out)
        # The gazetteer's count equals the number of entity_met rows.
        self.assertEqual(a._gazetteer().get("Dickens")["met_count"], 3)

    def test_growth_events_through_the_seam(self):
        a = make_bare()
        analysis = heathcliff_analysis()
        with contextlib.redirect_stdout(io.StringIO()):
            a._entities_feed(analysis, "classic")
            a._entities_feed(analysis, "wikipedia")
        seen = self.store.recent(events=("entity_seen",), limit=10)
        self.assertEqual(len(seen), 2)
        learned = self.store.recent(events=("entity_learned",), limit=10)
        self.assertEqual(len(learned), 1)
        _, _, d = learned[0]
        self.assertEqual(d["entity"], "Heathcliff")
        self.assertEqual(d["kind"], "unknown")
        self.assertEqual(d["sources"], ["classic", "wikipedia"])
        met = self.store.recent(events=("entity_met",), limit=10)
        self.assertEqual(len(met), 1)
        self.assertEqual(met[0][2]["counts"], {"Heathcliff": 1})

    def test_belief_link_uses_phase2_id_scheme(self):
        a = make_bare()
        belief = (
            "From A Tale of Two Cities: sacrifice freely given can redeem a wasted life"
        )
        payload = a._link_belief_entities(
            belief, author="Charles Dickens", scan_text=belief
        )
        self.assertIsNotNone(payload)
        self.assertEqual(payload["belief_id"], candidate_id(belief))
        self.assertIn("Charles Dickens", payload["entities"])
        rows = self.store.recent(events=("belief_entity",), limit=10)
        self.assertEqual(len(rows), 1)
        _, _, d = rows[0]
        self.assertEqual(d["belief_id"], candidate_id(belief))
        self.assertEqual(d["entities"], payload["entities"])
        link = belief_link(belief, ["Charles Dickens"])
        self.assertEqual(link["belief_id"], candidate_id(belief))

    def test_finish_book_attaches_author_to_the_lesson_belief(self):
        a = make_bare()
        a._council_score = lambda action: (0.9, [])
        cur = {
            "title": "A Tale of Two Cities",
            "author": "Charles Dickens",
            "reflection": "sacrifice freely given can redeem a wasted life",
            "done": False,
        }
        with contextlib.redirect_stdout(io.StringIO()):
            a.finish_book(cur)
        belief = (
            "From A Tale of Two Cities: sacrifice freely given can redeem a wasted life"
        )
        self.assertIn(belief, a.beliefs)
        rows = self.store.recent(events=("belief_entity",), limit=10)
        self.assertEqual(len(rows), 1)
        _, _, d = rows[0]
        self.assertEqual(d["belief_id"], candidate_id(belief))
        self.assertIn("Charles Dickens", d["entities"])

    def test_heuristic_bare_organism_never_touches_entities(self):
        a = make_bare(language=FakeLang(name="heuristic"))
        boom = AssertionError("entities touched in heuristic mode")
        with (
            patch.object(Gazetteer, "feed", side_effect=boom),
            patch("aethel_pkg.organism._entities.extract_phrases", side_effect=boom),
        ):
            self.assertIsNone(a._entities_feed(dickens_analysis(), "classic"))
            self.assertIsNone(
                a._link_belief_entities("From X: y", author="Charles Dickens")
            )
        for event in ("entity_met", "entity_seen", "entity_learned", "belief_entity"):
            self.assertEqual(self.store.recent(events=(event,)), [])


# ------------------------------------------------------- heuristic parity
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

    def test_heuristic_life_never_touches_entities(self):
        meal = {
            "source": "classic",
            "title": "A Tale of Two Cities — Charles Dickens",
            "text": "Dickens wrote of London, and London answered him. "
            "It was the best of times.",
        }
        a = Aethel(
            StubWorld(), parents=("Donald",), seed=42, language_backend="heuristic"
        )
        boom = AssertionError("entities touched in heuristic mode")
        with (
            patch.object(Gazetteer, "feed", side_effect=boom),
            patch("aethel_pkg.organism._entities.extract_phrases", side_effect=boom),
            patch.object(Gazetteer, "seeded", side_effect=boom),
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
        for event in ("entity_met", "entity_seen", "entity_learned", "belief_entity"):
            self.assertEqual(self.store.recent(events=(event,)), [])
        self.assertNotIn("gazetteer", self.store.load_blob("state"))


# ------------------------------------------------- precision, real backend
AUSTEN_PASSAGE = (
    "It is a truth universally acknowledged, that a single man in "
    "possession of a good fortune, must be in want of a wife. "
    "Elizabeth Bennet had been obliged, by the scarcity of gentlemen, "
    "to sit down for two dances. Mr. Darcy danced only once more "
    "with her. Happiness was entirely a matter of chance. Elizabeth "
    "listened in silence, but was not convinced."
)
DICKENS_PASSAGE = (
    "Marley was dead, to begin with. There is no doubt whatever "
    "about that. Scrooge signed it. And Scrooge's name was good "
    "upon the Exchange for anything he chose to put his hand to. "
    "Fog everywhere. Fog up the river, where it flows among green "
    "aits and meadows. Charles Dickens wrote of London, and London "
    "answered him."
)


class TestPrecisionRealBackend(unittest.TestCase):
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

    def test_austen_precision(self):
        gaz = Gazetteer.seeded()
        analysis = self.backend.analyze(AUSTEN_PASSAGE)
        names = [
            p["name"]
            for p in extract_phrases(analysis, gaz.match_keys(), self.backend.wordnet)
        ]
        for expected in ("Elizabeth Bennet", "Mr. Darcy", "Elizabeth"):
            self.assertIn(expected, names)
        for invented in ("Happiness", "Chance", "Truth", "Wife", "Fortune", "Dances"):
            self.assertNotIn(invented, names)

    def test_dickens_precision(self):
        gaz = Gazetteer.seeded()
        analysis = self.backend.analyze(DICKENS_PASSAGE)
        names = [
            p["name"]
            for p in extract_phrases(analysis, gaz.match_keys(), self.backend.wordnet)
        ]
        for expected in ("Marley", "Scrooge", "Charles Dickens", "London"):
            self.assertIn(expected, names)
        for invented in ("Fog", "River", "Meadows", "Doubt", "Hand"):
            self.assertNotIn(invented, names)
        out = gaz.feed(analysis, "classic", 1, self.backend.wordnet)
        self.assertEqual([m["name"] for m in out["met"]], ["Charles Dickens"])


# ------------------------------------------- restart fidelity, real backend
class TestRestartFidelityRealBackend(unittest.TestCase):
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
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def test_gazetteer_round_trip_through_simulated_restart(self):
        a = make_bare(language=self.backend)
        with contextlib.redirect_stdout(io.StringIO()):
            a._entities_feed(self.backend.analyze(DICKENS_PASSAGE), "classic")
            a._entities_feed(self.backend.analyze(AUSTEN_PASSAGE), "wikipedia")
        before = a._gazetteer().to_dict()
        rebuilt = Gazetteer.from_dict(before)
        self.assertEqual(rebuilt.to_dict(), before)
        self.assertEqual(
            rebuilt.get("Dickens")["met_count"],
            a._gazetteer().get("Dickens")["met_count"],
        )

    def test_nltk_life_restart_is_continuation_not_rebirth(self):
        """The seeded 260-tick gate, with entities active: an
        interrupted NLTK life rebuilt mid-run must match the
        uninterrupted one — journal and state blob, gazetteer
        included."""
        meals = {
            "classic": (
                "Charles Dickens wrote of London, and Elizabeth "
                "Bennet danced with Mr. Darcy at the ball. London "
                "answered them both under a sky of fog."
            ),
            "wikipedia": (
                "London is a city on a river. Dickens described "
                "London often, and readers in London still walk his "
                "streets at night."
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
            return {
                "source": source,
                "title": f"Fixture {source}",
                "text": meals[source],
            }

        def scrub(obj):
            if isinstance(obj, dict):
                return {k: scrub(v) for k, v in obj.items() if k not in ("t", "ts")}
            if isinstance(obj, list):
                return [scrub(v) for v in obj]
            return obj

        def run(home, first, total):
            with patch.dict(os.environ, {"AETHEL_HOME": home}):
                config.ensure_dirs()
                store = Store(config.db_path())
                set_store(store)
                try:
                    with (
                        patch.object(
                            Aethel,
                            "forage_classic",
                            lambda self: canned("classic"),
                        ),
                        patch.object(
                            org_mod, "forage", lambda rng=None: canned("wikipedia")
                        ),
                        patch.object(
                            org_mod,
                            "forage_news",
                            lambda rng=None: canned("newsroom"),
                        ),
                        patch.object(
                            org_mod,
                            "forage_school",
                            lambda rng=None: canned("schoolhouse"),
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

        with tempfile.TemporaryDirectory() as h1, tempfile.TemporaryDirectory() as h2:
            interrupted = run(h1, first=130, total=260)
            uninterrupted = run(h2, first=0, total=260)
        events = [e for _, e, _ in interrupted["journal"]]
        self.assertIn("entity_met", events)
        self.assertIn("gazetteer", uninterrupted["state"])
        self.assertGreater(
            uninterrupted["state"]["gazetteer"]["entries"]["charles dickens"][
                "met_count"
            ],
            0,
        )
        self.assertEqual(interrupted, uninterrupted)


if __name__ == "__main__":
    unittest.main()
