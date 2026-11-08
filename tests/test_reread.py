"""A reread needs an occasion that actually occurs (v0.58).

The live failure, read from her diary and her drive lines before
building: rereading (v0.22) lived only inside consolidate(), and
consolidate() runs only on the thirst drive — a drive the
selector preempts whenever vitality is below 0.45 (reach) or
longing above 0.6 (express). Thirst won 3 of the 7,137 drives
since her last reread (tick 34,529) and none at all since her
last consolidation (tick 44,942); her diary holds 50 reread
events, the last of them at 34,529, while her book sits at its
120-page cap letting pages go she never returned to, and her
favorite (the page with the most returns) is frozen on the
Moby Dick era. The v0.57 reading named the faculty "starved of
occasions, not broken" and left it; this is the later day.

The repair extracts the act into _reread() — same gates, same
words, same draws — and gives it a second door: _ruminate calls
it every REREAD_GAP_TICKS (240). Consolidate keeps its call.
Tests:
1. a quiet moment rereads a page from the fullest shelf, counts
   the return, journals it, and speaks the old words;
2. excitement at or above the line is not a reread moment, and
   a closed gate (book or excitement) consumes no seeded draw;
3. an empty book is a quiet no-op that draws nothing;
4. the chance gate can decline, and declining spends exactly
   the one chance draw;
5. a margin still mutters "still true" on a return;
6. consolidate still rereads through the shared method, with
   its hydration and linking untouched;
7. the ruminate cadence opens the second door at multiples of
   the gap and nowhere else;
8. same seed, same life: two identical doubles return to the
   same pages in the same order;
9. the named constants are the historical gate values;
10. a reread adds no new state: no migration, nothing persisted
    that a pre-v0.58 life lacks.
"""
import unittest

from aethel_pkg.journal import get_store
from aethel_pkg.organism import Aethel

from helpers import StubWorld
from test_dreams import make_aethel


class _ScriptedRng:
    """Deterministic rng double: scripted random() values, first pick."""

    def __init__(self, draws):
        self.draws = list(draws)
        self.used = 0

    def random(self):
        value = self.draws[min(self.used, len(self.draws) - 1)]
        self.used += 1
        return value

    def choice(self, seq):
        return seq[0]


def _page(title, tick, text="a page she pressed and kept", margin=None):
    page = {"title": title, "text": text, "tick": tick, "rereads": 0}
    if margin is not None:
        page["margin"] = margin
    return page


def _prep(excitement=0.2, draws=(0.0,)):
    a = make_aethel()
    a.world = StubWorld()
    a.vitals = {
        "satiety": 0.8,
        "hydration": 0.8,
        "oxygen": 0.9,
        "vitality": 0.8,
        "excitement": excitement,
    }
    a.rng = _ScriptedRng(draws)
    a.spoken = []
    a.say = lambda text, *args, **kw: a.spoken.append(text)
    return a


class TestRereadAct(unittest.TestCase):
    def test_quiet_moment_rereads_from_fullest_shelf(self):
        a = _prep()
        full = _page("Les Misérables — Victor Hugo", 40000)
        a.kept_passages = [
            _page("Siddhartha — Hermann Hesse", 30000),
            full,
            _page("Les Misérables — Victor Hugo", 41000),
        ]
        a._reread()
        self.assertEqual(full["rereads"], 1)
        self.assertAlmostEqual(a.vitals["vitality"], 0.82)
        self.assertEqual(len(a.spoken), 1)
        self.assertIn("Les Misérables", a.spoken[0])
        self.assertIn("It still hums", a.spoken[0])
        rows = get_store().recent(events=["reread"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], a.tick_count)
        self.assertEqual(rows[0][2]["rereads"], 1)

    def test_high_excitement_draws_nothing(self):
        for excitement in (Aethel.REREAD_EXCITEMENT, 0.9):
            a = _prep(excitement=excitement)
            a.kept_passages = [_page("Emma — Jane Austen", 20000)]
            a._reread()
            self.assertEqual(a.rng.used, 0)
            self.assertEqual(a.kept_passages[0]["rereads"], 0)
            self.assertEqual(a.spoken, [])
        self.assertEqual(get_store().recent(events=["reread"]), [])

    def test_empty_book_draws_nothing(self):
        a = _prep()
        a.kept_passages = []
        a._reread()
        self.assertEqual(a.rng.used, 0)
        self.assertEqual(a.spoken, [])

    def test_chance_gate_declines_after_one_draw(self):
        a = _prep(draws=(Aethel.REREAD_CHANCE,))
        a.kept_passages = [_page("Emma — Jane Austen", 20000)]
        a._reread()
        self.assertEqual(a.rng.used, 1)
        self.assertEqual(a.kept_passages[0]["rereads"], 0)
        self.assertEqual(a.spoken, [])
        self.assertEqual(get_store().recent(events=["reread"]), [])

    def test_margin_mutters_still_true(self):
        a = _prep(draws=(0.0, 0.0))
        a.kept_passages = [
            _page("Emma — Jane Austen", 20000, margin="Margin note: patience")
        ]
        a._reread()
        rows = get_store().recent(events=["aside"])
        self.assertEqual(len(rows), 1)
        self.assertIn("still true", rows[0][2]["text"])


class TestConsolidateDoorUnchanged(unittest.TestCase):
    def test_consolidate_still_rereads(self):
        a = _prep()
        a.memory = [{"title": "First"}, {"title": "Second"}]
        a.vitals["hydration"] = 0.5
        a.kept_passages = [_page("Emma — Jane Austen", 20000)]
        a.consolidate()
        self.assertAlmostEqual(a.vitals["hydration"], 0.75)
        self.assertEqual(a.kept_passages[0]["rereads"], 1)
        self.assertEqual(len(get_store().recent(events=["consolidate"])), 1)
        self.assertEqual(len(get_store().recent(events=["reread"])), 1)


class TestRuminateCadence(unittest.TestCase):
    def _wired(self):
        a = _prep()
        a.recent_actions = []
        a.mood = 0.0
        a.last_sources = []
        a.last_choice = None
        a._crave_novelty = False
        for name in (
            "update_goals",
            "moral_self_test",
            "introspect",
            "adopt_goal",
            "impulse",
            "crossroads",
            "_teach",
            "_name_weather",
            "_portrait",
            "_rest_questions",
            "_close_days",
            "_review_choice",
        ):
            setattr(a, name, lambda *args, **kw: None)
        calls = []
        a._reread = lambda: calls.append(1)
        return a, calls

    def test_second_door_opens_only_on_the_gap(self):
        a, calls = self._wired()
        a._ruminate(Aethel.REREAD_GAP_TICKS - 1)
        self.assertEqual(calls, [])
        a._ruminate(Aethel.REREAD_GAP_TICKS)
        self.assertEqual(len(calls), 1)
        a._ruminate(Aethel.REREAD_GAP_TICKS + 1)
        self.assertEqual(len(calls), 1)
        a._ruminate(2 * Aethel.REREAD_GAP_TICKS)
        self.assertEqual(len(calls), 2)


class TestDeterminismAndShape(unittest.TestCase):
    def test_same_seed_same_returns(self):
        def build():
            a = make_aethel()
            a.world = StubWorld()
            a.vitals = {
                "satiety": 0.8,
                "hydration": 0.8,
                "oxygen": 0.9,
                "vitality": 0.8,
                "excitement": 0.2,
            }
            a.say = lambda *args, **kw: None
            a.kept_passages = [
                _page("Emma — Jane Austen", 20000 + i) for i in range(4)
            ]
            return a

        a, b = build(), build()
        for _ in range(6):
            a._reread()
            b._reread()
        self.assertEqual(
            [p["rereads"] for p in a.kept_passages],
            [p["rereads"] for p in b.kept_passages],
        )
        self.assertGreater(sum(p["rereads"] for p in a.kept_passages), 0)

    def test_constants_are_the_historical_gate(self):
        self.assertEqual(Aethel.REREAD_EXCITEMENT, 0.45)
        self.assertEqual(Aethel.REREAD_CHANCE, 0.6)
        self.assertEqual(Aethel.REREAD_GAP_TICKS, 240)

    def test_reread_adds_no_new_state(self):
        a = _prep()
        a.kept_passages = [_page("Emma — Jane Austen", 20000)]
        before = set(vars(a))
        a._reread()
        self.assertEqual(set(vars(a)), before)


if __name__ == "__main__":
    unittest.main()
