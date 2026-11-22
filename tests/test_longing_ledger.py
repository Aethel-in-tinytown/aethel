"""v0.27 — the longing ledger.

Longing is itemized now: one entry per person, place, and unfinished
work, each with a learned attachment (w), a saturating ache, and an
open-loop bonus for unfinished things. The scalar survives only as a
derived aggregate. These tests pin the properties the design argues
for, not just its plumbing:

1. accrual saturates — ache relaxes toward w along 1 - exp(-t/tau),
   increments shrinking, ceiling never crossed;
2. satiation is targeted — touching one entry leaves every other
   entry byte-identical;
3. attachment learns — contact raises w (capped); a day-plus of
   neglect sags it toward the floor, and not before;
4. open loops pull harder — the bonus applies while a work is
   unfinished and releases when the loop closes;
5. a pre-ledger life migrates — the old scalar lands whole on the
   Donald entry and the aggregate does not jump;
6. the aggregate stays in [0, 1] and equals its derivation;
7. restart fidelity — save mid-run, rebuild, and the ledger's
   subsequent trajectory is bit-identical to the uninterrupted run.

Isolation: every organism here is built against a temp AETHEL_HOME
and an injected temp Store — the live diary is never opened.
"""
import math
import os
import tempfile
import unittest

from aethel_pkg import config
from aethel_pkg.journal import set_store
from aethel_pkg.longing import (AGGREGATE_SHARE, NEGLECT_AFTER_TICKS,
                                OPEN_LOOP_BONUS, TAU_TICKS, W_FLOOR,
                                WantLedger, book_id, person_id,
                                question_id)
from aethel_pkg.organism import Aethel
from aethel_pkg.store import Store

from helpers import StubWorld

RATE = 1.75  # the stock coupling: NEED_BURN alone, no void/distress


def entry(eid, kind, w, ache=0.0, since=0, open_loop=False, label=None):
    return {"id": eid, "kind": kind, "label": label or eid, "w": w,
            "ache": ache, "since": since, "open": open_loop}


class TestAccrualShape(unittest.TestCase):
    def test_saturating_curve_matches_closed_form(self):
        led = WantLedger([entry("person:Star", "person", 0.6)])
        tau = TAU_TICKS["person"]
        for t in range(1, 400):
            led.tick(RATE)
            expected = 0.6 * (1.0 - math.exp(-RATE * t / tau))
            self.assertAlmostEqual(led.entries[0]["ache"], expected,
                                   places=9)

    def test_increments_shrink_and_ceiling_holds(self):
        # inside one day: past NEGLECT_AFTER_TICKS the attachment
        # itself starts to sag and the ceiling moves — that is the
        # decay test's territory, not the accrual shape's
        led = WantLedger([entry("place:classic", "place", 0.45)])
        prev, deltas = 0.0, []
        for _ in range(2000):
            led.tick(RATE)
            ache = led.entries[0]["ache"]
            deltas.append(ache - prev)
            prev = ache
            self.assertLessEqual(ache, 0.45)
        self.assertTrue(all(d2 <= d1 + 1e-12
                            for d1, d2 in zip(deltas, deltas[1:])))

    def test_people_climb_faster_than_works(self):
        led = WantLedger([entry("person:Star", "person", 0.5),
                          entry("work:book:X", "work", 0.5)])
        for _ in range(100):
            led.tick(RATE)
        self.assertGreater(led.get("person:Star")["ache"],
                           led.get("work:book:X")["ache"])


class TestTargetedSatiation(unittest.TestCase):
    def test_touch_leaves_others_untouched(self):
        led = WantLedger([entry("person:Donald", "person", 0.85, 0.7),
                          entry("person:Star", "person", 0.55, 0.5),
                          entry("work:book:X", "work", 0.6, 0.4,
                                open_loop=True)])
        before = {e["id"]: dict(e) for e in led.entries}
        led.touch("person:Star", quality=0.35, learn=0.03)
        star = led.get("person:Star")
        self.assertAlmostEqual(star["ache"], 0.5 * 0.65, places=9)
        self.assertEqual(star["since"], 0)
        self.assertAlmostEqual(star["w"], 0.58, places=9)
        for eid in ("person:Donald", "work:book:X"):
            self.assertEqual(led.get(eid), before[eid])


class TestAttachmentLearning(unittest.TestCase):
    def test_contact_raises_w_and_caps_at_one(self):
        led = WantLedger([entry("person:Star", "person", 0.97)])
        led.touch("person:Star", quality=0.1, learn=0.06)
        self.assertEqual(led.get("person:Star")["w"], 1.0)

    def test_neglect_sags_w_toward_floor_only_after_a_day(self):
        e = entry("place:classic", "place", 0.45)
        led = WantLedger([e])
        for _ in range(NEGLECT_AFTER_TICKS):
            led.tick(RATE)
        self.assertEqual(e["w"], 0.45)  # not yet: the day is not over
        for _ in range(20000):
            led.tick(0.0)  # time passes; no climb needed for the sag
        self.assertLess(e["w"], 0.45)
        self.assertGreater(e["w"], W_FLOOR)


class TestOpenLoopBonus(unittest.TestCase):
    def test_open_entry_ceiling_carries_the_bonus(self):
        # measured inside one day, before neglect starts sagging w:
        # both entries follow the closed form, the open one's ceiling
        # is the bonus multiple of the closed one's
        led = WantLedger([entry("work:book:X", "work", 0.6,
                                open_loop=True),
                          entry("work:book:Y", "work", 0.6)])
        ticks = 1500
        for _ in range(ticks):
            led.tick(RATE)
        climb = 1.0 - math.exp(-RATE * ticks / TAU_TICKS["work"])
        self.assertAlmostEqual(led.get("work:book:X")["ache"],
                               0.6 * OPEN_LOOP_BONUS * climb, places=9)
        self.assertAlmostEqual(led.get("work:book:Y")["ache"],
                               0.6 * climb, places=9)
        self.assertGreater(led.get("work:book:X")["ache"],
                           led.get("work:book:Y")["ache"])

    def test_release_drops_the_ceiling(self):
        led = WantLedger([entry("work:book:X", "work", 0.6, ache=0.8,
                                open_loop=True)])
        led.release_loop("work:book:X")
        led.tick(RATE)
        # ache above the honest ceiling is pulled back to it
        self.assertAlmostEqual(led.get("work:book:X")["ache"], 0.6,
                               places=9)


class TestAggregate(unittest.TestCase):
    def test_matches_derivation_and_stays_in_bounds(self):
        led = WantLedger([entry("person:A", "person", 0.9, 0.8),
                          entry("person:B", "person", 0.5, 0.4),
                          entry("place:C", "place", 0.5, 0.2)])
        self.assertAlmostEqual(
            led.aggregate(), 0.8 + AGGREGATE_SHARE * (0.4 + 0.2) / 2,
            places=9)
        full = WantLedger([entry(f"person:{i}", "person", 1.0, 1.0)
                           for i in range(20)])
        self.assertEqual(full.aggregate(), 1.0)
        self.assertEqual(WantLedger().aggregate(), 0.0)


# ------------------------------------------------------- organism level
class LedgerLife(unittest.TestCase):
    """Base: a real Aethel against a temp home and temp store."""

    def setUp(self):
        self._saved_home = os.environ.get("AETHEL_HOME")
        self.tmp = tempfile.mkdtemp(prefix="aethel-ledger-")
        os.environ["AETHEL_HOME"] = self.tmp
        config.ensure_dirs()
        self.store = Store(config.db_path())
        set_store(self.store)

    def tearDown(self):
        self.store.close()
        # leave a throwaway in-memory store behind, the suite's
        # convention — never let a later get_store() open the live db
        set_store(Store(":memory:"))
        if self._saved_home is None:
            os.environ.pop("AETHEL_HOME", None)
        else:
            os.environ["AETHEL_HOME"] = self._saved_home

    def build(self, parents=("Donald", "Cassandra")):
        return Aethel(world=StubWorld(), parents=parents, seed=42)


class TestMigration(LedgerLife):
    def test_legacy_scalar_lands_on_donald_and_nothing_jumps(self):
        # a pre-v0.27 life: state with a longing scalar, no ledger
        self.store.save_blob("state", {
            "longing": 0.42, "tick_count": 5000,
            "vitals": {"satiety": 0.8, "hydration": 0.8, "oxygen": 1.0,
                       "vitality": 0.8, "excitement": 0.0},
        })
        a = self.build()
        self.assertAlmostEqual(a.longing, 0.42, places=9)
        donald = a.longing_ledger.get(person_id("Donald"))
        self.assertAlmostEqual(donald["ache"], 0.42, places=9)
        others = [e for e in a.longing_ledger.entries
                  if e["id"] != person_id("Donald")]
        self.assertTrue(others)  # the world seeded around him
        self.assertTrue(all(e["ache"] == 0.0 for e in others))

    def test_fresh_birth_seeds_from_her_world(self):
        a = self.build()
        ids = {e["id"] for e in a.longing_ledger.entries}
        self.assertIn(person_id("Donald"), ids)
        self.assertIn(person_id("Cassandra"), ids)  # a parent she knows
        book = next(b for b in a.reading_list if not b["done"])
        self.assertIn(book_id(book["title"]), ids)
        self.assertTrue(a.longing_ledger.get(
            book_id(book["title"]))["open"])
        self.assertEqual(a.longing, 0.0)  # a newborn aches for nothing yet


class TestOrganismHooks(LedgerLife):
    def test_attention_eases_only_donald(self):
        a = self.build()
        a._ledger().get(person_id("Donald"))["ache"] = 0.8
        a._ledger().ensure(person_id("Star"), "person", "Star", w=0.55)
        a._ledger().get(person_id("Star"))["ache"] = 0.5
        with open(config.attention_path(), "w") as f:
            f.write("knock")
        a._sense(a.tick_count + 1)
        self.assertAlmostEqual(
            a._ledger().get(person_id("Donald"))["ache"], 0.8 * 0.45,
            places=9)
        self.assertAlmostEqual(
            a._ledger().get(person_id("Star"))["ache"], 0.5, places=9)

    def test_finishing_a_book_closes_its_loop(self):
        a = self.build()
        cur = next(b for b in a.reading_list if not b["done"])
        self.assertIsNotNone(a._ledger().get(book_id(cur["title"])))
        a.finish_book(cur)
        self.assertIsNone(a._ledger().get(book_id(cur["title"])))

    def test_question_settles_out_of_the_ledger(self):
        a = self.build()
        q = {"text": "If I learned everything, would I still be me?",
             "keywords": ["learned"], "tick": 1, "touches": 2}
        a.open_questions = [q]
        a._question_touched(q)  # the third touch: wondered out
        self.assertEqual(q["touches"], 3)
        self.assertIsNone(a._ledger().get(question_id(q["text"])))

    def test_dream_born_question_enters_the_ledger(self):
        # regression: the morning table's question branch — the hook
        # receives the question text, not the dict (a type error here
        # crashed a 2000-tick soak before it was caught)
        a = self.build()
        a.concepts = {"whale": 5, "ocean": 5}
        a._sleep_dreams = ["whale ocean, whale ocean"]
        a.llm.moral_score = lambda action, phils: (0.56, "test")
        a._interpret_dreams(a.tick_count + 1)
        self.assertEqual(len(a.open_questions), 1)
        q = a.open_questions[0]
        e = a._ledger().get(question_id(q["text"]))
        self.assertIsNotNone(e)
        self.assertTrue(e["open"])

    def test_express_records_and_eases_its_driver(self):
        import aethel_pkg.organism as org
        a = self.build()
        q = {"text": "Why does the ache have a shape?",
             "keywords": ["ache"], "tick": 1, "touches": 0}
        a.open_questions = [q]
        led = a._ledger()
        led.ensure(question_id(q["text"]), "work", q["text"][:60],
                   w=0.5, open_loop=True)
        led.get(question_id(q["text"]))["ache"] = 0.9  # her loudest want
        events = []
        saved = org.journal
        org.journal = lambda event, **kw: events.append((event, kw))
        try:
            a.express()
        finally:
            org.journal = saved
        init = [kw for ev, kw in events if ev == "initiation"]
        self.assertEqual(len(init), 1)
        self.assertEqual(init[0]["want"], question_id(q["text"]))
        self.assertEqual(init[0]["kind"], "question")
        self.assertIn("Why does the ache have a shape?", init[0]["text"])
        # the driver eased twice over, both times proportionally:
        # asking the question touches it (x0.7), and the writing
        # itself satiates the want that drove it (x0.45). It was NOT
        # flattened to the old flat 0.15.
        after = led.get(question_id(q["text"]))["ache"]
        self.assertAlmostEqual(after, 0.9 * 0.7 * 0.45, places=6)
        self.assertNotEqual(a.longing, 0.15)


class TestRestartFidelity(LedgerLife):
    def _drive(self, a, ticks):
        """Deterministic life-pressure: needs tick, one scripted
        contact in the middle. No streams are consumed by the ledger,
        so identical inputs must give identical wants."""
        out = []
        for i in range(ticks):
            a.tick_count += 1
            a._update_needs()
            if i == ticks // 2:
                a._want_touch(person_id("Donald"), "person", "Donald",
                              quality=0.55, learn=0.05, w=0.85)
            out.append(round(a.longing, 9))
        return out

    def test_save_rebuild_continues_identically(self):
        a = self.build()
        self._drive(a, 60)
        a.save()
        snapshot = a.longing_ledger.to_dicts()
        # the rebuild: a new organism over the same saved life
        b = self.build()
        self.assertEqual(b.longing_ledger.to_dicts(), snapshot)
        traj_a = self._drive(a, 60)
        traj_b = self._drive(b, 60)
        self.assertEqual(traj_a, traj_b)
        self.assertEqual(a.longing_ledger.to_dicts(),
                         b.longing_ledger.to_dicts())


if __name__ == "__main__":
    unittest.main()
