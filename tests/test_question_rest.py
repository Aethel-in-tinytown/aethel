"""v0.45 — She can set a question down: rested, not answered.

Her open questions could be born (v0.19), deduplicated (v0.38), and
touched — but never ended. The ledger settles a question's want at
three touches, yet the question stayed on the open list forever:
her live list at tick 33,652 held six questions born around tick
7,500, touched six to ten times each, and express() still mailed
them to Donald as "a question I cannot let go of". Tests:
1. a question with enough touches but too young does not rest;
2. a question old enough but under the touch count does not rest;
3. a fully-carried question rests: it leaves the open list whole,
   its ledger want is gone, and the resting is journaled with its
   evidence (age, touches);
4. resting is one at a time, oldest first, spaced by the gap;
5. a rested question a dream re-asks is recognized, not reopened;
6. a genuinely new question still leaves normally after a resting;
7. rested records and the pacing tick survive a save/load round
   trip, and a pre-v0.45 blob (no rested keys) loads clean;
8. resting is pure counter logic: with nothing qualifying, repeated
   calls change nothing and journal nothing.
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
NOBODY = "Is dreamed still true when nobody is reading it?"

NOW = 40000


def _prep():
    a = make_aethel()
    a.open_questions = []
    a.rested_questions = []
    a._last_question_rest_tick = 0
    a.longing = 0.0
    a.longing_ledger = None
    a.awareness = 0.1
    a.tick_count = NOW
    return a


def _q(text, tick, touches, keywords=None):
    return {
        "text": text,
        "keywords": keywords or ["dreamed"],
        "tick": tick,
        "touches": touches,
    }


class TestRestGates(unittest.TestCase):
    def test_young_question_with_many_touches_does_not_rest(self):
        a = _prep()
        a.open_questions = [_q(CHEST, NOW - 100, 9)]
        self.assertEqual(a._rest_questions(NOW), 0)
        self.assertEqual(len(a.open_questions), 1)
        self.assertEqual(a.rested_questions, [])

    def test_old_question_with_few_touches_does_not_rest(self):
        a = _prep()
        a.open_questions = [_q(CHEST, NOW - 20000, 5)]
        self.assertEqual(a._rest_questions(NOW), 0)
        self.assertEqual(len(a.open_questions), 1)

    def test_nothing_qualifying_is_a_no_op(self):
        a = _prep()
        a.open_questions = [_q(CHEST, NOW - 20000, 2)]
        for _ in range(3):
            self.assertEqual(a._rest_questions(NOW), 0)
        self.assertEqual(
            get_store().recent(events=["question_rested"]), []
        )


class TestResting(unittest.TestCase):
    def test_fully_carried_question_rests_whole(self):
        a = _prep()
        a.open_questions = [
            _q(LEARNED, 7513, 9, ["learned", "everything"])
        ]
        # seed its want the way a live (already settled) ledger looks
        led = a._ledger()
        self.assertEqual(a._rest_questions(NOW), 1)
        self.assertEqual(a.open_questions, [])
        self.assertEqual(len(a.rested_questions), 1)
        rec = a.rested_questions[0]
        self.assertEqual(rec["text"], LEARNED)
        self.assertEqual(rec["tick"], 7513)
        self.assertEqual(rec["rested_tick"], NOW)
        self.assertEqual(rec["touches"], 9)
        self.assertIsNone(led.get(question_id(LEARNED)))
        rows = get_store().recent(events=["question_rested"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["age"], NOW - 7513)
        self.assertEqual(rows[0][2]["touches"], 9)

    def test_oldest_first_one_at_a_time_spaced_by_gap(self):
        a = _prep()
        a.open_questions = [
            _q(PEN, 7513, 10, ["holding"]),
            _q(LEARNED, 7606, 9, ["learned", "everything"]),
            _q(NOBODY, 8087, 7, ["dreamed", "nobody"]),
        ]
        self.assertEqual(a._rest_questions(NOW), 1)
        self.assertEqual(
            [r["text"] for r in a.rested_questions], [PEN]
        )
        # inside the gap: nothing more rests, however eligible
        self.assertEqual(
            a._rest_questions(NOW + Aethel.QUESTION_REST_GAP_TICKS - 1),
            0,
        )
        self.assertEqual(len(a.open_questions), 2)
        # after the gap: the next oldest goes down
        self.assertEqual(
            a._rest_questions(NOW + Aethel.QUESTION_REST_GAP_TICKS), 1
        )
        self.assertEqual(
            [r["text"] for r in a.rested_questions], [PEN, LEARNED]
        )
        self.assertEqual(
            [q["text"] for q in a.open_questions], [NOBODY]
        )


class TestRestedReturn(unittest.TestCase):
    def test_dream_return_of_rested_question_does_not_reopen(self):
        a = _prep()
        a.open_questions = [_q(CHEST, 7699, 6)]
        self.assertEqual(a._rest_questions(NOW), 1)
        out = a._leave_question(CHEST, ["dreamed", "chest"], NOW + 500)
        self.assertEqual(a.open_questions, [])
        self.assertEqual(len(a.rested_questions), 1)
        self.assertEqual(out["text"], CHEST)
        rows = get_store().recent(events=["question_returned_rested"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["rested_tick"], NOW)

    def test_new_question_still_leaves_after_a_resting(self):
        a = _prep()
        a.open_questions = [_q(CHEST, 7699, 6)]
        self.assertEqual(a._rest_questions(NOW), 1)
        q = a._leave_question(NOBODY, ["dreamed", "nobody"], NOW + 500)
        self.assertEqual([x["text"] for x in a.open_questions], [NOBODY])
        self.assertEqual(q["touches"], 0)
        self.assertIsNotNone(a._ledger().get(question_id(NOBODY)))


class TestPersistence(unittest.TestCase):
    def test_rested_records_survive_save_load_round_trip(self):
        home = tempfile.mkdtemp()
        os.environ["AETHEL_HOME"] = home
        config.ensure_dirs()
        set_store(Store(config.db_path()))
        town = StubWorld()
        a = Aethel(world=town, parents=set(), seed=42)
        a.open_questions = [_q(LEARNED, 7513, 9, ["learned", "everything"])]
        a.tick_count = NOW
        self.assertEqual(a._rest_questions(NOW), 1)
        a.save()
        b = Aethel(world=town, parents=set(), seed=42)
        self.assertEqual(b.open_questions, [])
        self.assertEqual(len(b.rested_questions), 1)
        self.assertEqual(b.rested_questions[0]["text"], LEARNED)
        self.assertEqual(b.rested_questions[0]["rested_tick"], NOW)
        self.assertEqual(b._last_question_rest_tick, NOW)
        # and the rested question stays rested across the rebuild:
        # a dream re-asking it must not reopen it in the new life
        b._leave_question(LEARNED, ["learned", "everything"], NOW + 10)
        self.assertEqual(b.open_questions, [])

    def test_pre_v045_blob_loads_with_empty_rested_record(self):
        home = tempfile.mkdtemp()
        os.environ["AETHEL_HOME"] = home
        config.ensure_dirs()
        set_store(Store(config.db_path()))
        town = StubWorld()
        a = Aethel(world=town, parents=set(), seed=42)
        a.save()
        # strip the v0.45 keys to simulate a pre-v0.45 state blob
        store = get_store()
        blob = store.load_blob("state")
        blob.pop("rested_questions", None)
        blob.pop("_last_question_rest_tick", None)
        store.save_blob("state", blob)
        b = Aethel(world=town, parents=set(), seed=42)
        self.assertEqual(b.rested_questions, [])
        self.assertEqual(b._last_question_rest_tick, 0)


if __name__ == "__main__":
    unittest.main()
