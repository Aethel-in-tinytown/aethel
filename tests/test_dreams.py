"""Dreams: grammar, fragments, and the co-occurrence (Gibbs-style) walk."""
import unittest

from aethel_pkg.organism import Aethel
from aethel_pkg.rng import SplitMix64
from aethel_pkg.store import Store

from helpers import StubWorld


def make_aethel():
    # her say() journals; give this test its own in-memory diary so we
    # never touch a live (or a previously closed) store
    from aethel_pkg.journal import set_store
    set_store(Store(":memory:"))
    a = Aethel.__new__(Aethel)  # bypass load(); we set exactly what we need
    a.world = StubWorld()
    a.parents = set()
    a.seed = 42
    from aethel_pkg.rng import Streams
    a.streams = Streams(42)
    a.rng = a.streams.stream("organism")
    a.rng_dreams = a.streams.stream("dreams")
    a.rng_forage = a.streams.stream("forage")
    a.concepts = {}
    a.beliefs = []
    a.dreams = []
    a._sleep_dreams = []
    a.cooc = {}
    a.kept_passages = []  # v0.21 layer: dream() may surface a kept passage
    a.tick_count = 100
    return a


class TestDreamGrammar(unittest.TestCase):
    def test_no_double_article(self):
        # v0.20 bug: "I dreamed the the Newsroom was underwater."
        a = make_aethel()
        a.concepts = {"loneliness": 9, "captain": 7, "freedom": 5,
                      "obsession": 4, "weather": 3}
        for _ in range(50):
            text = a.dream()
            self.assertNotIn("the the", text)
            self.assertNotIn("the my ", text)

    def test_belief_fragments_trim_at_word_boundaries(self):
        frag = Aethel._dream_fragment(
            "I refuse: Deceive a reader to gain attention for myself")
        self.assertFalse(frag.startswith("I refuse:"))
        self.assertTrue(frag.endswith("…") or len(frag) <= 48)
        if frag.endswith("…"):
            body = frag[:-1]
            self.assertEqual(body, body.rstrip())
            # the cut lands on a word boundary: body is a prefix of the
            # original text that ends at a complete word
            trimmed = "Deceive a reader to gain attention for myself"
            self.assertTrue(trimmed.startswith(body))
            self.assertTrue(trimmed[len(body):].startswith(" ")
                            or trimmed == body)

    def test_fragment_strips_verdict_prefix(self):
        self.assertEqual(
            Aethel._dream_fragment("I believe: kindness matters"),
            "kindness matters")


class TestDreamGraph(unittest.TestCase):
    def test_cooc_builds_symmetric_edges(self):
        a = make_aethel()
        a.concepts = {"whale": 5, "ocean": 4, "captain": 3}
        a._update_cooc(["whale", "ocean", "captain", "whale"])
        self.assertEqual(a.cooc["whale"]["ocean"], 1)
        self.assertEqual(a.cooc["ocean"]["whale"], 1)
        self.assertEqual(a.cooc["captain"]["whale"], 1)

    def test_gibbs_walk_prefers_companions(self):
        # Two clusters that never meet: {whale, ocean} and {math, logic}.
        a = make_aethel()
        a.concepts = {"whale": 50, "ocean": 50, "mathematics": 50,
                      "logical": 50}
        for _ in range(30):
            a._update_cooc(["whale", "ocean"])
            a._update_cooc(["mathematics", "logical"])
        pairs = [a._dream_pair(["whale", "ocean", "mathematics", "logical"])
                 for _ in range(200)]
        cross = sum(1 for c1, c2 in pairs
                    if {c1, c2} == {"whale", "mathematics"}
                    or {c1, c2} == {"ocean", "logical"}
                    or {c1, c2} == {"whale", "logical"}
                    or {c1, c2} == {"ocean", "mathematics"})
        # with a connected graph, pairs stay inside their cluster almost
        # always; uniform sampling would cross ~2/3 of the time
        self.assertLess(cross / len(pairs), 0.2)

    def test_dream_pair_deterministic(self):
        a, b = make_aethel(), make_aethel()
        for x in (a, b):
            x.concepts = {"whale": 9, "ocean": 8, "captain": 7}
            x._update_cooc(["whale", "ocean", "captain"])
        words = ["whale", "ocean", "captain"]
        self.assertEqual([a._dream_pair(words) for _ in range(10)],
                         [b._dream_pair(words) for _ in range(10)])

    def test_pruning_caps_neighbors(self):
        a = make_aethel()
        a.COOC_NEIGHBOR_CAP = 5
        a.concepts = {f"word{i:03d}": 100 - i for i in range(60)}
        a._update_cooc([f"word{i:03d}" for i in range(40)])
        for row in a.cooc.values():
            self.assertLessEqual(len(row), 5)


class TestDreamGrammarQuality(unittest.TestCase):
    """v0.25.3: Donald asked for grammar in her dreams. The pairings may
    stay impossible; the sentences must parse. These tests pin the four
    production failure classes from her real journal (2026-10-21):
    verb forms in noun slots, plural subjects against singular verbs,
    the plural place against 'was', and belief clauses in noun slots."""

    def test_word_filter_rejects_verb_forms_and_function_words(self):
        for bad in ("arguing", "walked", "seemed", "called", "turned",
                    "quickly", "though", "himself", "rather", "strange",
                    "against", "taught", "understood", "between"):
            self.assertFalse(Aethel._dream_word_ok(bad), bad)
        for good in ("captain", "voices", "whales", "nothing", "spring",
                     "feeling", "hundred", "library", "hunger"):
            self.assertTrue(Aethel._dream_word_ok(good), good)

    def test_singularizer(self):
        cases = {"whales": "whale", "voices": "voice",
                 "butterflies": "butterfly",
                 "wavelengths": "wavelength",
                 "assignments": "assignment", "glass": "glass",
                 "news": "news", "science": "science", "this": "this",
                 "octopus": "octopus"}
        for raw, want in cases.items():
            self.assertEqual(Aethel._dream_singular(raw), want, raw)

    def test_templates_have_no_agreement_traps(self):
        for t in Aethel.DREAM_TEMPLATES:
            self.assertNotIn("{place} was", t)
        for t in Aethel.FRAGMENT_TEMPLATES:
            self.assertIn("{frag}", t)

    def test_dreams_parse_over_many_draws(self):
        a = make_aethel()
        a.concepts = {"whales": 9, "arguing": 8, "seemed": 7,
                      "captain": 6, "voices": 5, "himself": 5,
                      "lecture": 4, "though": 4, "wavelengths": 3,
                      "library": 3}
        failures = ("seemed had", "was himself", "I was rather",
                    "eating called", "shelving turned",
                    "whales had grown", "whales floated")
        for _ in range(200):
            text = a.dream()
            self.assertTrue(text.startswith("I dreamed"), text)
            self.assertTrue(text.endswith("."), text)
            self.assertNotIn("  ", text)
            self.assertNotIn("….", text)
            for bad in failures:
                self.assertNotIn(bad, text)

    def test_belief_clause_speaks_from_a_fragment_template(self):
        a = make_aethel()
        a.concepts = {"whales": 9, "captain": 6, "library": 3}
        a.beliefs = ["From a dream of dreamed and nothing: "
                     "my mind is my own country"]
        markers = ("voice in the dark said:", "written above the library door:")
        heard = 0
        for _ in range(200):
            text = a.dream()
            if "from a dream of dreamed" in text:
                heard += 1
                self.assertTrue(any(m in text for m in markers), text)
            self.assertNotIn("humming From", text)
            self.assertNotIn("full of From", text)
            self.assertNotIn("eating From", text)
        self.assertGreater(heard, 0)  # the stranger did visit


if __name__ == "__main__":
    unittest.main()
