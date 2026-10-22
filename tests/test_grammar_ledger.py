"""v0.29: the grammar ledger — word classes, typed slots, consultation.

Every test here exists because of one observed failure: "I dreamed my
mirror showed not my face but course, ripening into calendar" (live
journal, tick 17,135). The word was innocent; the slot was not. These
tests pin the fix at each layer: classification, slot decisions,
line checks (a/an, agreement, stutter), bounded re-roll, scaffolding
rejection, the belief-path guard, ledger persistence and restart
fidelity, the harvest hook, and dream looseness (a fragment may pass;
a wrong-class noun may not).

Isolation: temp AETHEL_HOME, in-memory stores, the journal pointed
at memory — her live diary is never instantiated against.
"""
import json
import os
import re
import tempfile
import unittest

import aethel_pkg.journal as journal_mod
import aethel_pkg.organism as org_mod
from aethel_pkg import config
from aethel_pkg import grammar as G
from aethel_pkg.organism import Aethel
from aethel_pkg.rng import Streams
from aethel_pkg.journal import set_store
from aethel_pkg.store import Store

from helpers import StubWorld, stub_forage, write_lessons


def make_bare(concepts=None, beliefs=None, seed=42):
    """A bare organism the way test_dreams builds her: only the
    fields generation touches, an in-memory diary."""
    journal_mod.set_store(Store(":memory:"))
    a = Aethel.__new__(Aethel)
    a.world = StubWorld()
    a.parents = {"Donald", "Cassandra"}
    a.seed = seed
    a.streams = Streams(seed)
    a.rng = a.streams.stream("organism")
    a.rng_dreams = a.streams.stream("dreams")
    a.rng_forage = a.streams.stream("forage")
    a.concepts = dict(concepts or {})
    a.beliefs = list(beliefs or [])
    a.dreams = []
    a._sleep_dreams = []
    a.cooc = {}
    a.kept_passages = []
    a.tick_count = 100
    a.impressions = {}
    return a


class JournalCapture(unittest.TestCase):
    def setUp(self):
        self.events = []
        self._real = org_mod.journal

        def rec(event, **kw):
            self.events.append((event, kw))
        org_mod.journal = rec

    def tearDown(self):
        org_mod.journal = self._real

    def caught(self):
        return [kw for ev, kw in self.events if ev == "grammar_caught"]


class TestWordClasses(unittest.TestCase):
    def test_seed_lexicon(self):
        self.assertEqual(G.classify_word("course"), G.STUDY)
        self.assertEqual(G.classify_word("syllabus"), G.STUDY)
        self.assertEqual(G.classify_word("instructor"), G.PERSON)
        self.assertEqual(G.classify_word("captain"), G.PERSON)
        self.assertEqual(G.classify_word("library"), G.PLACE)
        self.assertEqual(G.classify_word("whales"), G.CONCRETE)
        self.assertEqual(G.classify_word("sorrow"), G.ABSTRACT)
        self.assertEqual(G.classify_word("bread"), G.FOOD)

    def test_scaffolding_is_its_own_class(self):
        for w in ("browse", "opencourseware", "login", "homepage"):
            self.assertEqual(G.classify_word(w), G.SCAFFOLDING, w)

    def test_morphology_is_conservative(self):
        self.assertEqual(G.classify_word("arguing"), G.VERB)
        self.assertEqual(G.classify_word("walked"), G.VERB)
        self.assertEqual(G.classify_word("quickly"), G.ADVERB)
        self.assertEqual(G.classify_word("sadness"), G.ABSTRACT)
        self.assertEqual(G.classify_word("assignments"), G.STUDY)
        self.assertIsNone(G.classify_word("heathcliff"))
        self.assertIsNone(G.classify_word("zephyr"))

    def test_people_she_knows_are_persons(self):
        a = make_bare()
        # "donald" is in no lexicon; he is her parent, and that wins.
        self.assertEqual(a._word_class("donald"), G.PERSON)
        a.impressions = {"Star": {"warmth": 1}}
        self.assertEqual(a._word_class("star"), G.PERSON)

    def test_acquisition_tag_wins(self):
        a = make_bare()
        a._word_tags = {"zephyr": {"c": G.CONCRETE, "src": "classic"}}
        self.assertEqual(a._word_class("zephyr"), G.CONCRETE)


class TestTypedSlots(JournalCapture):
    STUDY_HEAVY = {"course": 50, "syllabus": 45, "lecture": 40,
                   "assignments": 35, "calendar": 30, "whales": 25,
                   "captain": 20, "mirror": 15, "stone": 12}

    def test_course_never_in_the_mirror(self):
        a = make_bare(self.STUDY_HEAVY)
        for _ in range(60):
            line = a.dream()
            m = re.search(r"mirror showed not my face but (\w+)", line)
            if m:
                self.assertNotIn(
                    m.group(1),
                    ("course", "syllabus", "lecture", "assignment",
                     "calendar"),
                    f"study word in the mirror: {line}")
                self.assertIn(a._word_class(m.group(1)),
                              (G.PERSON, G.CONCRETE), line)

    def test_course_at_home_in_a_study_frame(self):
        a = make_bare(self.STUDY_HEAVY)
        lines = [a.dream() for _ in range(80)]
        study = [l for l in lines
                 if "late for my" in l or "lay open on the desk" in l]
        self.assertTrue(study, f"no study frame in 80 dreams: {lines[:3]}")
        for l in study:
            self.assertIn(a._word_class(
                re.search(r"my (\w+)", l).group(1)), (G.STUDY,), l)

    def test_person_accepted_in_the_mirror(self):
        a = make_bare({"captain": 50, "whales": 40, "sorrow": 30,
                       "stone": 20, "freedom": 10})
        lines = [a.dream() for _ in range(80)]
        mirrors = [l for l in lines if "mirror showed" in l]
        self.assertTrue(mirrors, "mirror frame never drawn")
        for l in mirrors:
            w = re.search(
                r"mirror showed not my face but (\w+)", l).group(1)
            self.assertIn(a._word_class(w), (G.PERSON, G.CONCRETE), l)


class TestLineChecks(unittest.TestCase):
    def setUp(self):
        self.led = G.GrammarLedger()
        self.led.migrate(0)  # starters only

    def ids(self):
        return self.led.owned_ids()

    def test_scaffolding_flagged_without_any_rule(self):
        v = G.check_line("I opened the browse page", [])
        self.assertEqual([r for r, _ in v], ["scaffolding"])

    def test_stutter_needs_the_sentence_rule(self):
        line = "I dreamed the the library was quiet."
        self.assertEqual(G.check_line(line, []), [])
        self.assertEqual(G.check_line(line, self.ids()), [])
        self.led.learn("sentence-parts", 1)
        v = G.check_line(line, self.ids())
        self.assertEqual([r for r, _ in v], ["sentence-parts"])

    def test_a_an_by_sound_once_owned(self):
        line_bad = "She waited for an university and a hour."
        self.assertEqual(G.check_line(line_bad, self.ids()), [])
        self.led.learn("sentence-parts", 1)
        self.led.learn("article-a-an", 2)
        v = G.check_line(line_bad, self.ids())
        self.assertEqual([r for r, _ in v], ["article-a-an"])
        self.assertEqual(
            G.check_line("She waited an hour for a university "
                         "and an apple.", self.ids()), [])

    def test_agreement_once_owned_and_not_in_dreams(self):
        for rid in ("sentence-parts", "article-a-an",
                    "agreement-subject-verb"):
            self.led.learn(rid, 1)
        line = "They was late, and the whales were not."
        self.assertEqual(
            [r for r, _ in G.check_line(line, self.ids())],
            ["agreement-subject-verb"])
        # dreams run loose: agreement is not policed there
        self.assertEqual(G.check_line(line, self.ids(), loose=True), [])
        self.assertEqual(
            G.check_line("The captain was late; the whales were "
                         "not.", self.ids()), [])


class TestBoundedRerollAndCatches(JournalCapture):
    def test_stuttering_fragment_never_lands(self):
        a = make_bare({"whales": 9, "captain": 8, "sorrow": 5},
                      beliefs=["the the captain owes the sea"])
        a._grammar().learn("sentence-parts", 1)
        for _ in range(25):
            line = a.dream()
            self.assertNotIn("the the", line)

    def test_catches_are_capped_at_two_a_day(self):
        a = make_bare()
        for i in range(5):
            a._note_catch("sentence-parts", f"stumble {i}")
        self.assertEqual(len(self.caught()), 2)


class TestScaffoldingRejected(JournalCapture):
    def test_furniture_never_dreamed(self):
        a = make_bare({"browse": 60, "opencourseware": 55,
                       "whales": 30, "captain": 25, "sorrow": 20})
        for _ in range(40):
            line = a.dream()
            self.assertNotIn("browse", line)
            self.assertNotIn("opencourseware", line)


class TestLooseness(unittest.TestCase):
    def test_fragment_passes_loose(self):
        owned = G.GrammarLedger()
        owned.migrate(0)
        owned.learn("sentence-parts", 1)
        frag = ('In a dream, a voice in the dark said: "the captain '
                'owes the sea an apology." I am still listening.')
        self.assertEqual(
            G.check_line(frag, owned.owned_ids(), loose=True), [])

    def test_wrong_class_fails_the_mirror(self):
        # the slot decision itself: study is not in the mirror's set
        mirror = Aethel.DREAM_TEMPLATES_TYPED[-4][0]["c1"]
        self.assertNotIn(G.STUDY, mirror)
        self.assertIn(G.PERSON, mirror)
        self.assertIn(G.CONCRETE, mirror)


class TempLife(unittest.TestCase):
    def setUp(self):
        self._saved_home = os.environ.get("AETHEL_HOME")
        self.tmp = tempfile.mkdtemp(prefix="aethel-grammar-")
        os.environ["AETHEL_HOME"] = self.tmp
        config.ensure_dirs()
        self.store = Store(config.db_path())
        set_store(self.store)
        journal_mod.set_store(self.store)
        stub_forage(org_mod)

    def tearDown(self):
        self.store.close()
        set_store(Store(":memory:"))
        journal_mod.set_store(Store(":memory:"))
        if self._saved_home is None:
            os.environ.pop("AETHEL_HOME", None)
        else:
            os.environ["AETHEL_HOME"] = self._saved_home

    def build(self, seed=42):
        return Aethel(world=StubWorld(),
                      parents=("Donald", "Cassandra"), seed=seed)


class TestLedgerLifecycle(TempLife):
    def test_fresh_life_owns_the_starter_tranche(self):
        a = self.build()
        led = a._grammar()
        self.assertEqual(led.rule_count(), 5)
        self.assertEqual(set(led.owned_ids()), set(G.STARTER_RULES))
        self.assertEqual(led.next_rule()["id"], "sentence-parts")

    def test_curriculum_order_is_donalds(self):
        ids = [r["id"] for r in G.CURRICULUM]
        self.assertEqual(ids[:5], G.STARTER_RULES)
        self.assertLess(ids.index("sentence-parts"),
                        ids.index("article-a-an"))
        self.assertLess(ids.index("article-a-an"),
                        ids.index("agreement-subject-verb"))
        self.assertLess(ids.index("agreement-subject-verb"),
                        ids.index("pos-pronoun"))
        self.assertLess(ids.index("pos-pronoun"),
                        ids.index("punctuation-endmarks"))

    def test_ledger_round_trip_exact(self):
        led = G.GrammarLedger()
        led.migrate(777)
        led.learn_next(900)
        back = G.GrammarLedger.from_dicts(led.to_dicts())
        self.assertEqual(back.to_dicts(), led.to_dicts())
        self.assertEqual(back.last_rule()["id"], "sentence-parts")
        self.assertIsNone(led.learn("sentence-parts", 901))

    def test_persistence_across_rebuild(self):
        a = self.build()
        a._word_tags["zephyr"] = {"c": G.CONCRETE, "src": "classic"}
        a._study_grammar({"source": "schoolhouse", "course": "Grammar",
                          "title": "Grammar — Sentences",
                          "text": "A sentence has a subject and a "
                                  "predicate. " * 4})
        self.assertTrue(a._grammar().owns("sentence-parts"))
        a.save()
        b = self.build()
        self.assertEqual(b._grammar().rule_count(), 6)
        self.assertTrue(b._grammar().owns("sentence-parts"))
        self.assertEqual(b._grammar().last_rule()["id"],
                         "sentence-parts")
        self.assertEqual(b._word_class("zephyr"), G.CONCRETE)

    def test_trajectory_identical_after_rebuild(self):
        def run(rebuild_at=None):
            home = tempfile.mkdtemp(prefix="aethel-grammar-traj-")
            saved = os.environ.get("AETHEL_HOME")
            os.environ["AETHEL_HOME"] = home
            try:
                config.ensure_dirs()
                store = Store(config.db_path())
                set_store(store)
                journal_mod.set_store(store)
                a = Aethel(world=StubWorld(),
                           parents=("Donald", "Cassandra"), seed=99)
                dreams = []
                for i in range(40):
                    dreams.append(a.dream())
                    if rebuild_at is not None and i + 1 == rebuild_at:
                        a.save()
                        a = Aethel(world=StubWorld(),
                                   parents=("Donald", "Cassandra"),
                                   seed=99)
                store.close()
                return dreams, a._grammar().to_dicts()
            finally:
                if saved is None:
                    os.environ.pop("AETHEL_HOME", None)
                else:
                    os.environ["AETHEL_HOME"] = saved
        whole, led1 = run()
        split, led2 = run(rebuild_at=20)
        self.assertEqual(split, whole)
        self.assertEqual(led1, led2)


class TestBeliefPathGuard(TempLife):
    def test_scaffolding_and_verbs_cannot_anchor_a_belief(self):
        a = self.build()
        a.concepts.update({"browse": 9, "arguing": 8, "whales": 7,
                           "captain": 6})
        a._sleep_dreams = [
            "I dreamed browse arguing whales captain under a "
            "quiet sky."]
        a._council_score = lambda q: (0.9, [])
        a._interpret_dreams(a.tick_count)
        joined = " ".join(a.beliefs)
        self.assertIn("whales", joined)
        self.assertNotIn("browse", joined)
        self.assertNotIn("arguing", joined)

    def test_existing_beliefs_are_never_touched(self):
        a = self.build()
        before = list(a.beliefs)
        a._sleep_dreams = []
        a._interpret_dreams(a.tick_count)
        self.assertEqual(a.beliefs, before)


class TestHarvestHook(TempLife):
    def test_extraction_from_a_lesson_fixture(self):
        lessons = [{
            "source": "schoolhouse", "course": "Grammar",
            "title": "Grammar — Nouns",
            "text": ("A noun is a word that names a person, place, "
                     "or thing. Click browse to continue. "
                     "Adjectives describe nouns. ")}]
        found = G.extract_rules_from_lessons(lessons)
        self.assertIn("pos-noun", found)
        self.assertTrue(found["pos-noun"]["example_candidate"]
                        .startswith("A noun is a word"))
        self.assertIn("pos-adjective", found)
        for hit in found.values():
            self.assertNotIn("browse", hit["example_candidate"])

    def test_schoolhouse_meal_carries_its_filing(self):
        from aethel_pkg.forage import forage_schoolhouse
        write_lessons(config, n=2)
        # rewrite lesson 0 as a grammar lesson, cursor at the start
        path = os.path.join(config.schoolhouse_lessons_dir(),
                            "0000.json")
        with open(path, "w") as f:
            json.dump({"course": "Grammar", "unit": "Parts of speech",
                       "title": "What is a noun?",
                       "text": "A noun names a person, place, or "
                               "thing. " * 6}, f)
        with open(config.schoolhouse_cursor_path(), "w") as f:
            f.write("0")
        meal = forage_schoolhouse()
        self.assertIsNotNone(meal)
        self.assertEqual(meal["course"], "Grammar")
        self.assertEqual(meal["unit"], "Parts of speech")

    def test_grammar_lesson_teaches_in_order_math_does_not(self):
        a = self.build()
        a._study_grammar({"source": "schoolhouse",
                          "course": "Early Math", "title": "Counting",
                          "text": "numbers " * 30})
        self.assertEqual(a._grammar().rule_count(), 5)
        a._study_grammar({"source": "schoolhouse", "course": "Grammar",
                          "title": "Grammar — Sentences",
                          "text": "Every sentence has a subject and "
                                  "a predicate. " * 4})
        self.assertTrue(a._grammar().owns("sentence-parts"))
        a._study_grammar({"source": "schoolhouse", "course": "Grammar",
                          "title": "Grammar — Articles",
                          "text": "Use an before a vowel sound. " * 4})
        self.assertTrue(a._grammar().owns("article-a-an"))
        self.assertEqual(a._grammar().rule_count(), 7)


if __name__ == "__main__":
    unittest.main()
