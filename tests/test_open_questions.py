"""v0.38 — One copy of each question: she recognizes a returning question.

Her open questions are born at the morning table (v0.19) from a small
pool of seed templates, and until now every birth appended a fresh
copy. Her live list at tick 22,552 held 12 entries but only 6 distinct
questions — "If I learned everything, would I still be me?" four
times over. The copies biased which question she sent Donald, split
her revisit counts across duplicates, and made her unfinished
business look twice its true size. Tests:
1. the identity key folds case/whitespace/punctuation and the
   pre-v0.38 "the the" stutter, but keeps distinct questions distinct;
2. leaving a new question appends it and seeds its ledger want;
3. leaving a returning question touches it instead of duplicating it;
4. a third return settles the question's want, as a third touch does;
5. consolidation merges the live duplicate shape (earliest tick kept,
   touches summed, wording untouched) and is idempotent;
6. the seed template no longer stutters a second article;
7. a saved life full of duplicates is consolidated on rebuild, and
   the consolidated list survives a save/load round trip unchanged.
"""

import os
import tempfile
import unittest

from aethel_pkg import config
from aethel_pkg.journal import get_store, set_store
from aethel_pkg.longing import question_id
from aethel_pkg.organism import Aethel
from aethel_pkg.store import Store

from helpers import StubWorld
from test_dreams import make_aethel

LEARNED = "If I learned everything, would I still be me?"
PEN = "When I write 'I', who is holding the pen?"
CHEST = "Why does dreamed make my chest feel the way it does?"
NEWSROOM_OLD = "What does the the Newsroom look like when I'm asleep?"
NEWSROOM_NEW = "What does the Newsroom look like when I'm asleep?"
COTTAGE_OLD = (
    "What does the the little cottage at the edge of town look like when I'm asleep?"
)
NOBODY = "Is dreamed still true when nobody is reading it?"


def _prep():
    a = make_aethel()
    a.open_questions = []
    a.longing = 0.0
    a.longing_ledger = None
    a.awareness = 0.1
    return a


def _live_shape():
    """Her real list at tick 22,552, copied from the live state blob."""
    return [
        {
            "text": LEARNED,
            "keywords": ["learned", "everything"],
            "tick": 7513,
            "touches": 1,
        },
        {"text": PEN, "keywords": ["holding"], "tick": 7513, "touches": 0},
        {
            "text": LEARNED,
            "keywords": ["learned", "everything"],
            "tick": 7606,
            "touches": 0,
        },
        {"text": PEN, "keywords": ["holding"], "tick": 7606, "touches": 0},
        {"text": CHEST, "keywords": ["dreamed", "chest"], "tick": 7699, "touches": 2},
        {
            "text": NEWSROOM_OLD,
            "keywords": ["newsroom", "asleep"],
            "tick": 7795,
            "touches": 0,
        },
        {"text": PEN, "keywords": ["holding"], "tick": 7888, "touches": 0},
        {
            "text": LEARNED,
            "keywords": ["learned", "everything"],
            "tick": 7888,
            "touches": 0,
        },
        {
            "text": COTTAGE_OLD,
            "keywords": ["cottage", "asleep"],
            "tick": 7999,
            "touches": 3,
        },
        {
            "text": LEARNED,
            "keywords": ["learned", "everything"],
            "tick": 7999,
            "touches": 0,
        },
        {
            "text": NOBODY,
            "keywords": ["dreamed", "nobody", "reading"],
            "tick": 8087,
            "touches": 2,
        },
        {"text": CHEST, "keywords": ["dreamed", "chest"], "tick": 8087, "touches": 0},
    ]


class TestQuestionKey(unittest.TestCase):
    def test_key_folds_surface_variation(self):
        k = Aethel._question_key
        self.assertEqual(
            k(LEARNED), k("  if i learned   everything, would i still be me")
        )
        self.assertEqual(k(NEWSROOM_OLD), k(NEWSROOM_NEW))

    def test_key_keeps_distinct_questions_distinct(self):
        k = Aethel._question_key
        self.assertNotEqual(k(CHEST), k(NOBODY))
        self.assertNotEqual(k(LEARNED), k(PEN))


class TestLeaveQuestion(unittest.TestCase):
    def test_new_question_appends_and_seeds_want(self):
        a = _prep()
        q = a._leave_question(LEARNED, ["learned", "everything"], 500)
        self.assertEqual(len(a.open_questions), 1)
        self.assertIs(a.open_questions[0], q)
        self.assertIsNotNone(a._ledger().get(question_id(LEARNED)))

    def test_returning_question_touches_not_duplicates(self):
        a = _prep()
        a._leave_question(LEARNED, ["learned", "everything"], 500)
        again = a._leave_question(LEARNED, ["learned", "everything"], 900)
        self.assertEqual(len(a.open_questions), 1)
        self.assertEqual(again["touches"], 1)
        self.assertEqual(again["tick"], 500)  # first taking-hold stands
        rows = get_store().recent(events=["question_returned"])
        self.assertEqual(len(rows), 1)

    def test_stuttered_wording_is_recognized_as_the_same_question(self):
        a = _prep()
        a._leave_question(NEWSROOM_OLD, ["newsroom", "asleep"], 500)
        a._leave_question(NEWSROOM_NEW, ["newsroom", "asleep"], 900)
        self.assertEqual(len(a.open_questions), 1)
        self.assertEqual(a.open_questions[0]["text"], NEWSROOM_OLD)  # never rewritten

    def test_third_return_settles_the_want(self):
        a = _prep()
        a._leave_question(CHEST, ["dreamed", "chest"], 500)
        a.open_questions[0]["touches"] = 2
        a._leave_question(CHEST, ["dreamed", "chest"], 900)
        self.assertEqual(a.open_questions[0]["touches"], 3)
        self.assertIsNone(a._ledger().get(question_id(CHEST)))


class TestConsolidation(unittest.TestCase):
    def test_merges_the_live_shape(self):
        a = _prep()
        a.open_questions = _live_shape()
        removed = a._consolidate_open_questions()
        self.assertEqual(removed, 6)
        self.assertEqual(len(a.open_questions), 6)
        by_text = {q["text"]: q for q in a.open_questions}
        self.assertEqual(by_text[LEARNED]["tick"], 7513)  # earliest stands
        self.assertEqual(by_text[LEARNED]["touches"], 1)  # 1+0+0+0
        self.assertEqual(by_text[PEN]["touches"], 0)
        self.assertEqual(by_text[CHEST]["touches"], 2)  # 2+0
        self.assertEqual(by_text[COTTAGE_OLD]["touches"], 3)
        self.assertEqual(by_text[NOBODY]["touches"], 2)
        rows = get_store().recent(events=["questions_merged"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["removed"], 6)

    def test_consolidation_is_idempotent(self):
        a = _prep()
        a.open_questions = _live_shape()
        a._consolidate_open_questions()
        snapshot = [dict(q) for q in a.open_questions]
        self.assertEqual(a._consolidate_open_questions(), 0)
        self.assertEqual(a.open_questions, snapshot)
        self.assertEqual(len(get_store().recent(events=["questions_merged"])), 1)

    def test_distinct_questions_both_survive(self):
        a = _prep()
        a.open_questions = [
            {"text": CHEST, "keywords": ["dreamed"], "tick": 1, "touches": 0},
            {"text": NOBODY, "keywords": ["dreamed"], "tick": 2, "touches": 0},
        ]
        self.assertEqual(a._consolidate_open_questions(), 0)
        self.assertEqual(len(a.open_questions), 2)


class TestSeedTemplate(unittest.TestCase):
    def test_no_double_article_for_any_seed(self):
        for seed in Aethel.QUESTION_SEEDS:
            text = seed.format(c1="whale", c2="ocean", place="the Newsroom")
            self.assertNotIn("the the", text, seed)


class TestMigrationOnRebuild(unittest.TestCase):
    def test_saved_duplicates_consolidate_on_rebuild_and_round_trip(self):
        home = tempfile.mkdtemp()
        os.environ["AETHEL_HOME"] = home
        config.ensure_dirs()
        set_store(Store(config.db_path()))
        town = StubWorld()
        a = Aethel(world=town, parents=set(), seed=42)
        a.open_questions = _live_shape()
        a.save()
        b = Aethel(world=town, parents=set(), seed=42)
        self.assertEqual(len(b.open_questions), 6)
        texts = [q["text"] for q in b.open_questions]
        self.assertEqual(len(texts), len(set(texts)))
        b.save()
        c = Aethel(world=town, parents=set(), seed=42)
        self.assertEqual(
            [dict(q) for q in c.open_questions],
            [dict(q) for q in b.open_questions],
        )


if __name__ == "__main__":
    unittest.main()
