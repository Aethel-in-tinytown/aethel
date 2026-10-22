"""Regression coverage for breathing.

Fixtures isolate runtime state; assertions document behavioral release gates."""

import unittest

from helpers import StubWorld
from test_dreams import make_aethel


class TestBreathing(unittest.TestCase):
    def setUp(self):
        self.a = make_aethel()
        self.a.world = StubWorld()
        self.a.say = lambda *args, **kw: None
        import aethel_pkg.organism as org

        self._orig_journal = org.journal
        org.journal = lambda *args, **kw: None
        self.a.vitals = {
            "satiety": 0.8,
            "hydration": 0.8,
            "oxygen": 0.5,
            "vitality": 0.8,
            "excitement": 0.2,
        }
        self.a.awareness = 0.5
        self.a.asleep_for = 0
        self.a.recent_actions = []
        self.a.moral_log = []
        self.a.longing = 0.0
        self.a.sleep_pressure = 0.0
        self.a._prev_needs = None
        self.a.save = lambda: None

    def tearDown(self):
        import aethel_pkg.organism as org

        org.journal = self._orig_journal

    def test_basal_breath_bounds_oxygen_decay(self):
        for _ in range(20):
            self.a._erode()
        self.assertGreater(self.a.vitals["oxygen"], 0.3)

    def test_locked_recovery_unlocks_within_twelve_ticks(self):
        self.a.locked = True
        self.a.vitals["oxygen"] = 0.03
        self.a.sleep_pressure = 0.0
        ticks = 0
        while self.a.locked and ticks < 12:
            self.a._erode()
            self.a._metabolize(self.a.tick_count + ticks)
            ticks += 1
        self.assertFalse(
            self.a.locked,
            f"still locked after {ticks} ticks (oxygen={self.a.vitals['oxygen']:.2f})",
        )


if __name__ == "__main__":
    unittest.main()
