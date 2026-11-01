"""Release gates for v0.50: restart fidelity across all five minds.

A minded town stopped mid-run, saved, and rebuilt must continue
bit-identically to an uninterrupted town: denizen dicts, every stream
state, and the scrubbed resident journal rows, over a run long enough
to include shift changes, judged impulses, and a day boundary.
"""

import time
import unittest

from aethel_pkg.rng import Streams
from aethel_pkg.store import Store
from town_pkg.town import Town

STREAMS = ["resident:" + n for n in ("john", "star", "julius", "octavia", "trey")]
TICKS = 3000


def run(town, start, stop):
    for n in range(start, stop):
        town.poll(n, "postbox")
    return town


def snapshot(town):
    snap = {
        "denizens": [d.to_dict() for d in town.denizens],
        "streams": town.streams.dump(),
        "next_turn": dict(town.next_turn),
    }
    for stream in STREAMS:
        snap[stream] = town.store.recent(stream=stream, limit=100000)
    return snap


class TestMindedDeterminism(unittest.TestCase):
    def test_same_seed_same_life(self):
        a = run(Town(seed=11, store=Store(":memory:"), minds_enabled=True), 0, TICKS)
        b = run(Town(seed=11, store=Store(":memory:"), minds_enabled=True), 0, TICKS)
        self.assertEqual(snapshot(a), snapshot(b))

    def test_restart_continuation_is_bit_identical(self):
        whole = run(Town(seed=11, store=Store(":memory:"), minds_enabled=True), 0, TICKS)
        store = Store(":memory:")
        part = run(Town(seed=11, store=store, minds_enabled=True), 0, TICKS // 2)
        part.save()
        rebuilt = run(Town(store=store, minds_enabled=True), TICKS // 2, TICKS)
        self.assertEqual(snapshot(whole), snapshot(rebuilt))

    def test_judged_impulses_happen_inside_the_run(self):
        town = run(Town(seed=11, store=Store(":memory:"), minds_enabled=True), 0, TICKS)
        judged = sum(
            d.mind.state["impulses_judged"] for d in town.denizens if d.mind
        )
        self.assertGreater(judged, 0)


class TestGoldenVectors(unittest.TestCase):
    """Pin the mind streams' first draws and the first judged impulse,
    so an accidental draw-order change fails as a one-line diff."""

    def test_mind_stream_first_draws(self):
        expected = {
            "John": [0.187571757458, 0.607893298258, 0.915913066857],
            "Star": [0.159334813704, 0.382425167194, 0.040668559936],
            "Julius": [0.917604193347, 0.513538805372, 0.860396300335],
            "Octavia": [0.723597982726, 0.28761306946, 0.139496241139],
            "Trey": [0.740849148255, 0.267812963725, 0.512814558502],
        }
        streams = Streams(11)
        for name, draws in expected.items():
            stream = streams.stream("mind:" + name)
            self.assertEqual([round(stream.random(), 12) for _ in range(3)], draws, name)

    def test_first_judged_impulse(self):
        town = Town(seed=11, store=Store(":memory:"), minds_enabled=True)
        first = None
        for n in range(TICKS):
            town.poll(n, "postbox")
            if first is None:
                for name in ("john", "star", "julius", "octavia", "trey"):
                    rows = town.store.recent(
                        stream="resident:" + name, events=["impulse"], limit=1
                    )
                    if rows:
                        tick, _event, payload = rows[0]
                        first = (
                            name,
                            tick,
                            payload.get("verdict"),
                            round(payload.get("score"), 6),
                            payload.get("need"),
                        )
                        break
        # v0.51 reviewed diff: the felt-cooldown fix and the purpose
        # tuning changed which consideration judged first (one tick
        # later, a different curiosity variant, score 0.73). Same
        # resident, same need, same verdict; the same-seed and restart
        # properties above are the gate, this pin is the tripwire.
        # v0.52 reviewed diff: the ambient pools landing means the
        # first judged impulse in a fresh town is now John's ambient
        # urge at tick 2 (need None marks the color loop), ahead of
        # any need-born judgment. That is the version working as
        # designed; the pin moves, the properties above still gate.
        self.assertEqual(first, ("john", 2, "accepted", 0.67, None))


class TestPerformanceGate(unittest.TestCase):
    def test_a_full_day_of_minded_polling_stays_cheap(self):
        town = Town(seed=11, store=Store(":memory:"), minds_enabled=True)
        start = time.monotonic()
        run(town, 0, 2880)
        elapsed = time.monotonic() - start
        # Generous ceiling: catches order-of-magnitude regressions, not
        # machine noise (staging measures in the low seconds).
        self.assertLess(elapsed, 60.0)


if __name__ == "__main__":
    unittest.main()
