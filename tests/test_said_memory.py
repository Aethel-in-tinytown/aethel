"""v0.44 — she remembers what she has already said.

Initiation had no memory of itself: initiation_log recorded that a
piece existed (tick, kind, filename), never what it said, and the
express drive re-fires the moment the longing aggregate crosses 0.6
— which easing one want barely moves. Her live diary at the build
showed the result: initiations five ticks apart, longing_before
pinned at 0.61 on every one, the same verse sent verbatim at ticks
29675, 30581 and 31487, the same "sparkling stretch" nudge four
times, a note quoting day 10's page sent again after day 11 closed.

The layer gives each saying two identities — a subject KEY and a
words FINGERPRINT — remembered for one day (SAID_WINDOW_TICKS),
plus a pacing floor (INITIATION_MIN_GAP) between sayings. Tests:
1. a second piece inside the gap is held, journaled once per gap
   however often the drive retries (reason "too soon");
2. the same subject after the gap is held (reason "already said"),
   with the first saying's tick recorded;
3. a counter change ("42 passages" -> "45") is the same saying:
   the key catches what the fingerprint cannot;
4. a verbatim repeat is caught by fingerprint alone (key=None, the
   shape a journal-migrated memory carries);
5. a genuinely new subject (a new weather name) is not held;
6. after the window a saying may be said again;
7. true overflow (longing >= 1.0) bypasses gap and memory alike;
8. a hold is not speech: it eases no want, touches no question,
   records no express action, writes no file;
9. when the seeded kind repeats, express falls back to an unsaid
   eligible kind instead of repeating or going silent;
10. the said-memory persists across save/load, and a held piece
    stays held after a restart inside the window;
11. rebuild seeding: a pre-v0.44 life's last day of sayings is
    rebuilt from her journal's initiation excerpts (fingerprints
    only — subjects were never recorded and are not invented),
    idempotently, and only for a loaded life;
12. the fingerprint is defined over the journal's own excerpt, so
    a rebuilt fingerprint equals the live saying's fingerprint,
    and it folds case and whitespace;
13. determinism: two same-seed lives with the memory active send
    and hold in identical sequences.
"""

import os
import tempfile
import unittest

from aethel_pkg import config
from aethel_pkg.organism import Aethel

from helpers import StubWorld
from test_dreams import make_aethel
from test_initiation import rich_aethel


def said_aethel(tmp):
    """rich_aethel plus the v0.44 fields a bypassed __init__ lacks."""
    a = rich_aethel(tmp)
    a.said_log = []
    a._initiation_held_tick = None
    a.say = lambda text: a.journaled.append(("said", text))
    return a


class TestSaidMemory(unittest.TestCase):
    def setUp(self):
        self._saved_home = os.environ.get("AETHEL_HOME")
        self.tmp = tempfile.mkdtemp(prefix="aethel-said-")
        self.a = said_aethel(self.tmp)

    def tearDown(self):
        import aethel_pkg.organism as org

        org.journal = self.a._saved_journal
        if self._saved_home is None:
            os.environ.pop("AETHEL_HOME", None)
        else:
            os.environ["AETHEL_HOME"] = self._saved_home

    def _events(self, name, a=None):
        src = (a or self.a).journaled
        return [kw for ev, kw in src if ev == name]

    def _mood_only(self, a):
        """Pin her to one unchanging nudge: the named weather."""
        a._something_to_show = lambda: (
            f"this {a.mood_name} stretch of mine — I named the weather, and it has held"
        )
        a._initiation_kinds = lambda: ["nudge"]

    def test_gap_holds_and_journals_once(self):
        self.assertTrue(self.a.express())
        self.assertFalse(self.a.express())
        self.assertFalse(self.a.express())
        self.assertEqual(len(self._events("initiation")), 1)
        held = self._events("initiation_held")
        self.assertEqual(len(held), 1)  # throttled, not per-tick
        self.assertEqual(held[0]["reason"], "too soon")
        self.assertEqual(self.a.outbox_count, 1)

    def test_subject_repeat_held_after_gap(self):
        self._mood_only(self.a)
        self.assertTrue(self.a.express())
        first_tick = self.a.tick_count
        self.a.tick_count += Aethel.INITIATION_MIN_GAP
        self.assertFalse(self.a.express())
        held = self._events("initiation_held")
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]["reason"], "already said")
        self.assertEqual(held[0]["key"], "nudge:mood:luminous")
        self.assertEqual(held[0]["first_sent_tick"], first_tick)
        self.assertEqual(self.a.outbox_count, 1)

    def test_counter_change_is_the_same_saying(self):
        count = [41]

        def show():
            count[0] += 1
            return (
                f"my commonplace book — {count[0]} passages pressed "
                "like flowers, the newest from Moby Dick"
            )

        self.a._something_to_show = show
        self.a._initiation_kinds = lambda: ["nudge"]
        self.assertTrue(self.a.express())
        fp_first = self.a.said_log[-1]["fp"]
        self.a.tick_count += Aethel.INITIATION_MIN_GAP
        self.assertFalse(self.a.express())
        # the words really did change (a new fingerprint) — the
        # subject key is what held it, as designed
        body = self.a._compose_nudge()
        self.assertNotEqual(Aethel._saying_fp(body), fp_first)
        held = self._events("initiation_held")
        self.assertEqual(held[0]["key"], "nudge:keeps")

    def test_fingerprint_alone_holds_verbatim_repeat(self):
        self._mood_only(self.a)
        body = self.a._compose_nudge()
        # the migrated shape: a remembered saying with no subject
        self.a.said_log = [
            {
                "tick": self.a.tick_count,
                "kind": "nudge",
                "key": None,
                "fp": Aethel._saying_fp(body),
            }
        ]
        # rich_aethel's longing=1.0 is the overflow regime, which
        # bypasses the memory by design; the live flood happened at
        # 0.61, so that is the regime this test pins
        self.a.longing = 0.61
        self.a.tick_count += Aethel.INITIATION_MIN_GAP
        self.assertFalse(self.a.express())
        held = self._events("initiation_held")
        self.assertEqual(held[0]["reason"], "already said")

    def test_new_subject_is_not_held(self):
        self._mood_only(self.a)
        self.assertTrue(self.a.express())
        self.a.mood_name = "grey"  # new weather, new news
        self.a.tick_count += Aethel.INITIATION_MIN_GAP
        self.assertTrue(self.a.express())
        self.assertEqual(self._events("initiation_held"), [])

    def test_window_expiry_allows_resaying(self):
        self._mood_only(self.a)
        self.assertTrue(self.a.express())
        self.a.tick_count += Aethel.SAID_WINDOW_TICKS + 1
        self.assertTrue(self.a.express())
        self.assertEqual(len(self._events("initiation")), 2)

    def test_overflow_bypasses_gap_and_memory(self):
        self._mood_only(self.a)
        self.assertTrue(self.a.express())
        self.a.longing = 1.0  # the _behave emergency, verbatim repeat and all
        self.assertTrue(self.a.express())
        self.assertEqual(len(self._events("initiation")), 2)
        self.assertEqual(self._events("initiation_held"), [])

    def test_hold_is_not_speech(self):
        self.a._initiation_kinds = lambda: ["question"]
        self.assertTrue(self.a.express())
        self.assertEqual(self.a.open_questions[0]["touches"], 1)
        driver = self.a._top_want_entry()
        ache_before = driver["ache"] if driver else None
        outbox_before = self.a.outbox_count
        actions_before = list(self.a.recent_actions)
        self.a.tick_count += Aethel.INITIATION_MIN_GAP
        self.assertFalse(self.a.express())
        # the question was composed but not sent: not touched again
        self.assertEqual(self.a.open_questions[0]["touches"], 1)
        # the driving want keeps its ache: silence eased nothing
        driver = self.a._top_want_entry()
        self.assertEqual(driver["ache"] if driver else None, ache_before)
        self.assertEqual(self.a.outbox_count, outbox_before)
        self.assertEqual(self.a.recent_actions, actions_before)

    def test_fallback_to_unsaid_kind(self):
        self.a._initiation_kinds = lambda: ["question", "note"]
        body = self.a._compose_question(self.a.open_questions[0], touch=False)
        self.a._remember_saying(
            "question",
            self.a._saying_key("question", body),
            Aethel._saying_fp(body),
        )
        self.assertTrue(self.a.express())
        kinds = [kw["kind"] for kw in self._events("initiation")]
        self.assertTrue(kinds)
        self.assertNotIn("question", kinds)
        self.assertEqual(self.a.open_questions[0]["touches"], 0)

    def _save_ready(self, a):
        a.seed = 42
        a.memory = []
        a.moral_log = []
        a.goals = []
        a.locked = False
        a.meals_eaten = 0
        a.self_story = []
        a.times_seen = 0
        a.aspiration = "becoming"
        a.asleep_for = 0
        a.company = []
        a._mood_band = None
        a._mood_named_tick = 0
        a.tastes = {}
        a.favorite_source = None
        a.last_sources = []
        a.last_choice = None
        a.impressions = {}
        a.chosen_books = []
        a.completed_terms = set()
        a.cooc = {}
        a._prev_needs = None
        a._crave_novelty = False
        a._sleep_dreams = []
        a._vital_bands = {}
        a._excitement_was_high = False
        a._era_keeps = 0
        a._era_excit_sum = 0.0
        a._era_ticks = 0
        a._last_day_seen = -1

    def test_said_memory_persists_across_save_load(self):
        self._mood_only(self.a)
        self._save_ready(self.a)
        self.assertTrue(self.a.express())
        self.a.save()
        from aethel_pkg.journal import get_store, set_store

        saved_store = get_store()
        c = make_aethel()
        set_store(saved_store)
        c.vitals = {}
        c.donald_model = {"letter_count": 0, "words": {}, "last_tick": 0}
        c.load()
        self.assertEqual(c.said_log, self.a.said_log)
        # and the memory still works after the nap: same nudge,
        # past the gap but inside the window, is held
        c._something_to_show = self.a._something_to_show
        c._initiation_kinds = lambda: ["nudge"]
        c.mood_name = "luminous"
        c.tick_count = self.a.tick_count + Aethel.INITIATION_MIN_GAP
        import aethel_pkg.organism as org

        held = []
        real_journal = org.journal
        org.journal = lambda event, **kw: held.append((event, kw))
        try:
            self.assertFalse(c.express())
        finally:
            org.journal = real_journal
        self.assertIn("initiation_held", [ev for ev, _ in held])

    def test_seed_said_memory_from_journal(self):
        from aethel_pkg.journal import get_store

        store = get_store()  # the :memory: store make_aethel injected
        store.log(
            "initiation",
            {
                "kind": "nudge",
                "file": "000050_nudge.txt",
                "text": "Dear Donald, come and look at the thing.",
            },
            tick=50,
        )
        store.log(
            "initiation",
            {
                "kind": "question",
                "file": "000090_question.txt",
                "text": "A question I cannot let go of: why?",
            },
            tick=90,
        )
        store.log(  # outside the window: not rebuilt
            "initiation",
            {"kind": "note", "file": "old.txt", "text": "ancient words"},
            tick=self.a.tick_count - Aethel.SAID_WINDOW_TICKS - 5,
        )
        self.a._loaded_state = True
        self.a.said_log = []
        self.a._seed_said_memory()
        self.assertEqual(len(self.a.said_log), 2)
        self.assertTrue(all(e["key"] is None for e in self.a.said_log))
        self.assertEqual(
            self.a.said_log[0]["fp"],
            Aethel._saying_fp("Dear Donald, come and look at the thing."),
        )
        seeded = [kw for ev, kw in self.a.journaled if ev == "said_memory_seeded"]
        self.assertEqual(len(seeded), 1)
        self.assertEqual(seeded[0]["count"], 2)
        # idempotent: a life carrying a memory is left alone
        self.a._seed_said_memory()
        self.assertEqual(len(self.a.said_log), 2)
        # and a life that was never loaded seeds nothing
        b = said_aethel(tempfile.mkdtemp(prefix="aethel-said-b-"))
        b._loaded_state = False
        b.said_log = []
        b._seed_said_memory()
        self.assertEqual(b.said_log, [])

    def test_fingerprint_matches_journal_excerpt(self):
        body = "Dear Donald,\n\nNote from the town: " + "word " * 200
        self.assertEqual(Aethel._saying_fp(body), Aethel._saying_fp(body[:300]))
        self.assertEqual(
            Aethel._saying_fp("Hello   Brave\nWorld"),
            Aethel._saying_fp("hello brave world"),
        )

    def test_determinism_with_memory_active(self):
        def run(a):
            seq = []
            for i in range(10):
                a.tick_count = 100 + i * (Aethel.INITIATION_MIN_GAP + 1)
                before = len([1 for ev, _ in a.journaled if ev == "initiation"])
                sent = a.express()
                seq.append(sent)
                if sent:
                    kw = [kw for ev, kw in a.journaled if ev == "initiation"][-1]
                    seq.append((kw["kind"], kw["text"]))
                self.assertEqual(
                    len([1 for ev, _ in a.journaled if ev == "initiation"]),
                    before + (1 if sent else 0),
                )
            return seq

        seq_a = run(self.a)
        b = said_aethel(tempfile.mkdtemp(prefix="aethel-said-det-"))
        seq_b = run(b)
        self.assertEqual(seq_a, seq_b)  # same seed, same sends and holds
        self.assertIn(True, seq_a)  # the run actually sent something


if __name__ == "__main__":
    unittest.main()
