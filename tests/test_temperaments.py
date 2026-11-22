"""v0.28 — temperaments live.

A temperament is a bundle of multipliers on machinery that already
exists: the burns, the council's emphasis, the diet's leanings, and —
the seam v0.27 built — the longing ledger's per-class climb. These
tests pin the properties the design argues for:

1. the spec survives transcription — every strain, every number in
   the lever range, every voice name a real AXIOMS key, Briar's Care
   left at 1.0;
2. Even Keel is the control group — its record is exactly neutral;
3. THE GATE: a full seeded life under Even Keel is bit-identical to
   the same life with the temperament layer neutralized (the
   _temperament_neutral seam) — journals and state blobs alike;
4. the council's weighted mean reduces to the legacy mean at all-1.0
   weights, bit for bit, and emphasis actually moves verdicts;
5. per-pack 500-tick soaks under an identical script show the
   claimed profile directions (Ember's people-ache above Even
   Keel's, Stillwater's below, the Owl's work-ache above, Moonmoth
   sleeping sooner) and oxygen never varies by strain;
6. switching is a sleep-boundary act: queued by control file, never
   mid-wake, journaled by her on waking, cancellable, and refused
   when the id is unknown;
7. nature persists — active strain, pending switch, ledger, and
   Briar's daily weather all survive a rebuild bit-identically.

Isolation: temp AETHEL_HOME and an injected temp Store throughout —
the live diary is never opened (the house pattern, as in
test_longing_ledger.py and test_determinism.py).
"""
import contextlib
import io
import os
import tempfile
import unittest

import aethel_pkg.forage as forage_mod
import aethel_pkg.organism as org
from aethel_pkg import config
from aethel_pkg.config import AXIOMS
from aethel_pkg.journal import get_store, set_store
from aethel_pkg.longing import book_id, person_id
from aethel_pkg.mind import MockLLM
from aethel_pkg.organism import Aethel
from aethel_pkg.store import Store
from aethel_pkg.temperament import TEMPERAMENTS, pack
from town_pkg.town import Town

from helpers import StubWorld, stub_forage, write_lessons

PACKS = ["even-keel", "stillwater", "ember", "owl", "moonmoth", "briar"]


# ------------------------------------------------------------ the spec
class TestSpecIntegrity(unittest.TestCase):
    def test_all_six_strains_present(self):
        self.assertEqual(sorted(TEMPERAMENTS), sorted(PACKS))

    def test_even_keel_is_exactly_neutral(self):
        ek = TEMPERAMENTS["even-keel"]
        self.assertTrue(all(v == 1.0 for v in ek["burn"].values()))
        self.assertTrue(all(v == 1.0 for v in ek["longing"].values()))
        self.assertEqual(ek["voices"], {})
        self.assertIsNone(ek["diet"])
        self.assertEqual(ek["deep_food"], 1.0)
        self.assertIsNone(ek["jitter"])

    def test_voice_names_are_real_axioms_keys(self):
        for tid, rec in TEMPERAMENTS.items():
            for name in rec["voices"]:
                self.assertIn(name, AXIOMS, f"{tid}: {name}")

    def test_multipliers_stay_in_the_spec_lever_range(self):
        for tid, rec in TEMPERAMENTS.items():
            for v in rec["burn"].values():
                self.assertTrue(0.5 <= v <= 1.8, f"{tid} burn {v}")
            for v in rec["longing"].values():
                self.assertTrue(0.5 <= v <= 1.8, f"{tid} longing {v}")
            for v in rec["voices"].values():
                self.assertTrue(0.5 <= v <= 1.5, f"{tid} voice {v}")
            if rec["jitter"] is not None:
                lo, hi = rec["jitter"]
                self.assertTrue(0.5 <= lo < hi <= 1.8)

    def test_briar_care_stays_at_one(self):
        # wild, never cruel: Ethics of Care is not in her table,
        # which is how a voice stays at exactly 1.0
        self.assertNotIn("Ethics of Care (Gilligan)",
                         TEMPERAMENTS["briar"]["voices"])

    def test_unknown_id_degrades_to_even_keel(self):
        self.assertIs(pack("plasma-9000"), TEMPERAMENTS["even-keel"])


# ------------------------------------------------------------ the council
class TestCouncilWeights(unittest.TestCase):
    ACTION = "learn share care truth overcome"

    def setUp(self):
        self.llm = MockLLM()
        self.phils = list(AXIOMS.keys())

    def test_weighted_reduces_to_legacy_at_neutral_weights(self):
        # To summation precision, not bit-for-bit: Python's sum()
        # compensates, a hand accumulation does not, and the two can
        # sit 1 ULP apart. Bit-identity for the control strain is an
        # ORGANISM-level property (Even Keel never enters this path —
        # see TestCouncilSeam) and the golden-vector test holds it
        # over a full life; here we pin the arithmetic agreement.
        legacy, notes = self.llm.moral_score(self.ACTION, self.phils)
        for weights in ({}, {n: 1.0 for n in self.phils}):
            w_score, w_notes = self.llm.moral_score(
                self.ACTION, self.phils, weights=weights)
            self.assertAlmostEqual(w_score, legacy, places=12)
            self.assertEqual(w_notes, notes)

    def test_emphasis_moves_the_verdict_toward_the_voice(self):
        solos = {}
        for name in self.phils:
            s, _ = self.llm.moral_score(self.ACTION, [name])
            solos[name] = s
        legacy, _ = self.llm.moral_score(self.ACTION, self.phils)
        loudest = max(solos, key=solos.get)
        quietest = min(solos, key=solos.get)
        self.assertGreater(solos[loudest], solos[quietest],
                           "sanity: the voices actually disagree here")
        up, _ = self.llm.moral_score(self.ACTION, self.phils,
                                     weights={loudest: 3.0})
        down, _ = self.llm.moral_score(self.ACTION, self.phils,
                                       weights={quietest: 3.0})
        self.assertGreater(up, legacy)
        self.assertLess(down, legacy)

    def test_weighting_an_abstaining_voice_changes_nothing(self):
        # 'Machiavellian' has no word in this action; weight on a
        # voice that did not vote must not move the mean (beyond the
        # summation-order ULP documented above)
        legacy, _ = self.llm.moral_score(self.ACTION, self.phils)
        w, _ = self.llm.moral_score(
            self.ACTION, self.phils,
            weights={"Machiavellian (Machiavelli)": 1.5})
        self.assertAlmostEqual(w, legacy, places=12)


# ------------------------------------------------------- organism harness
class TempLife(unittest.TestCase):
    """A real Aethel against a temp home and temp store."""

    def setUp(self):
        self._saved_home = os.environ.get("AETHEL_HOME")
        self.tmp = tempfile.mkdtemp(prefix="aethel-temp-")
        os.environ["AETHEL_HOME"] = self.tmp
        config.ensure_dirs()
        self.store = Store(config.db_path())
        set_store(self.store)

    def tearDown(self):
        self.store.close()
        set_store(Store(":memory:"))
        if self._saved_home is None:
            os.environ.pop("AETHEL_HOME", None)
        else:
            os.environ["AETHEL_HOME"] = self._saved_home

    def build(self, parents=("Donald", "Cassandra")):
        return Aethel(world=StubWorld(), parents=parents, seed=42)


class TestCouncilSeam(TempLife):
    """Where bit-identity actually lives: _council_score under Even
    Keel takes the legacy call (empty table), so its results equal
    the pre-v0.28 two-argument call EXACTLY — tuple for tuple."""

    ACTIONS = ["learn share care truth overcome",
               "Hoard knowledge and refuse to share it with anyone",
               "Write Donald a letter",
               "accept duty and endure, or deceive and hoard"]

    def test_even_keel_council_is_the_legacy_call_exactly(self):
        a = self.build()
        for action in self.ACTIONS:
            self.assertEqual(a._council_score(action),
                             a.llm.moral_score(action, a.philosophers))

    def test_a_pack_with_voices_routes_through_the_weights(self):
        a = self.build()
        a.temperament = "stillwater"   # Stoicism leads at 1.5
        legacy = a.llm.moral_score(self.ACTIONS[0], a.philosophers)
        weighted = a._council_score(self.ACTIONS[0])
        self.assertNotEqual(weighted[0], legacy[0])


class TestBurnProfiles(TempLife):
    START = {"satiety": 0.8, "hydration": 0.8, "oxygen": 0.9,
             "vitality": 0.8, "excitement": 0.9}

    def _erode_run(self, pack_id, ticks):
        a = self.build()
        a.temperament = pack_id
        a.vitals = dict(self.START)
        oxy = []
        for _ in range(ticks):
            a._erode()
            oxy.append(a.vitals["oxygen"])
        return a, oxy

    def test_oxygen_identical_across_all_packs(self):
        _, reference = self._erode_run("even-keel", 200)
        for pid in PACKS[1:]:
            _, oxy = self._erode_run(pid, 200)
            self.assertEqual(oxy, reference, f"oxygen moved under {pid}")

    def test_hunger_and_vitality_burn_directions(self):
        a_ek, _ = self._erode_run("even-keel", 5)
        a_sw, _ = self._erode_run("stillwater", 5)
        a_em, _ = self._erode_run("ember", 5)
        # hunger: Stillwater (0.7x) keeps her satiety, Ember (1.1x) spends it
        self.assertGreater(a_sw.vitals["satiety"], a_ek.vitals["satiety"])
        self.assertGreater(a_ek.vitals["satiety"], a_em.vitals["satiety"])
        # excitement: the Romantic's fizz fades fastest of all (1.5x)
        a_ek20, _ = self._erode_run("even-keel", 10)
        a_em20, _ = self._erode_run("ember", 10)
        self.assertGreater(a_ek20.vitals["excitement"],
                           a_em20.vitals["excitement"])

    def test_moonmoth_diet_is_the_legacy_diet(self):
        a = self.build()
        a.temperament = "moonmoth"   # spec: no strong leaning
        self.assertEqual(a._diet_weights(),
                         {"classic": 0.35, "news": 0.20, "school": 0.15})

    def test_pack_diets_lean_as_speced(self):
        a = self.build()
        a.temperament = "owl"
        self.assertEqual(a._diet_weights()["school"], 0.35)
        a.temperament = "stillwater"
        self.assertEqual(a._diet_weights()["classic"], 0.50)
        a.temperament = "briar"
        self.assertEqual(a._diet_weights()["news"], 0.40)


class TestPackSoaks(TempLife):
    """500 ticks of _update_needs under an identical script: vitals
    pinned (so the v0.12 rate coupling is the same weather for every
    strain), no contact with people, one touch of her book at t=250.
    The only differences left are the packs' own numbers."""

    TICKS = 500

    def _soak(self, pack_id):
        a = self.build()
        a.temperament = pack_id
        led = a._ledger()
        for e in led.entries:
            e["ache"] = 0.0
            e["since"] = 0
        book = next(b for b in a.reading_list if not b["done"])
        person_at_150 = None
        sleep_hit = None
        max_longing = 0.0
        for i in range(self.TICKS):
            a.tick_count += 1
            a.vitals["vitality"] = 0.8   # pin the weather
            a._update_needs()
            max_longing = max(max_longing, a.longing)
            if i == 149:
                person_at_150 = led.get(person_id("Donald"))["ache"]
            if i == 249:
                a._want_touch(book_id(book["title"]), "work",
                              book["title"], quality=0.3, learn=0.0,
                              w=0.60, open_loop=True)
            if sleep_hit is None and a.sleep_pressure >= 1.0:
                sleep_hit = a.tick_count
        return {"a": a, "person150": person_at_150,
                "person": led.get(person_id("Donald"))["ache"],
                "work": led.get(book_id(book["title"]))["ache"],
                "sleep_hit": sleep_hit, "max_longing": max_longing}

    def test_profiles_point_the_way_the_spec_says(self):
        ek = self._soak("even-keel")
        ember = self._soak("ember")
        still = self._soak("stillwater")
        owl = self._soak("owl")
        moon = self._soak("moonmoth")
        # longing by class: Ember misses people hardest, Stillwater least
        self.assertGreater(ember["person150"], ek["person150"])
        self.assertGreater(ek["person150"], still["person150"])
        self.assertGreater(ember["person"], ek["person"])
        # the Owl's unfinished book pulls harder than the control's
        self.assertGreater(owl["work"], ek["work"])
        # sleep: Moonmoth (1.4x) is driven to bed long before Even Keel;
        # the Owl (0.8x) outlasts the control
        self.assertLess(moon["sleep_hit"], ek["sleep_hit"])
        # nobody's longing escapes its bounds in 500 ticks
        for run in (ek, ember, still, owl, moon):
            self.assertLessEqual(run["max_longing"], 1.0)


class TestSwitching(TempLife):
    def _write_request(self, text):
        with open(config.temperament_path(), "w") as f:
            f.write(text)

    def _capture_journal(self):
        events = []
        saved = org.journal
        org.journal = lambda event, **kw: events.append((event, kw))
        return events, saved

    def test_request_queues_and_applies_only_at_waking(self):
        a = self.build()
        self._write_request("ember")
        a._sense(a.tick_count + 1)
        self.assertEqual(a.temperament, "even-keel")      # not yet
        self.assertEqual(a.temperament_pending, "ember")  # queued
        self.assertFalse(os.path.exists(config.temperament_path()))
        for _ in range(10):                                # a waking stretch
            a._update_needs()
        self.assertEqual(a.temperament, "even-keel")      # still not yet
        events, saved = self._capture_journal()
        try:
            a.asleep_for = 1
            a.sleep_tick(a.tick_count + 1)                 # the boundary
        finally:
            org.journal = saved
        self.assertEqual(a.temperament, "ember")
        self.assertIsNone(a.temperament_pending)
        switched = [kw for ev, kw in events
                    if ev == "temperament_switched"]
        self.assertEqual(len(switched), 1)
        self.assertEqual(switched[0]["from_id"], "even-keel")
        self.assertEqual(switched[0]["to_id"], "ember")

    def test_naming_her_current_strain_cancels_a_queued_switch(self):
        a = self.build()
        self._write_request("ember")
        a._sense(a.tick_count + 1)
        self.assertEqual(a.temperament_pending, "ember")
        self._write_request("even-keel")
        a._sense(a.tick_count + 2)
        self.assertIsNone(a.temperament_pending)
        self.assertEqual(a.temperament, "even-keel")

    def test_unknown_strain_is_refused_not_guessed(self):
        a = self.build()
        events, saved = self._capture_journal()
        try:
            self._write_request("plasma")
            a._sense(a.tick_count + 1)
        finally:
            org.journal = saved
        self.assertEqual(a.temperament, "even-keel")
        self.assertIsNone(a.temperament_pending)
        self.assertIn("temperament_rejected", [ev for ev, _ in events])
        self.assertFalse(os.path.exists(config.temperament_path()))


class TestPersistence(TempLife):
    def test_active_pending_and_ledger_survive_a_rebuild(self):
        a = self.build()
        a.temperament = "ember"
        a.temperament_pending = "owl"
        ledger_before = a.longing_ledger.to_dicts()
        a.save()
        b = self.build()
        self.assertEqual(b.temperament, "ember")
        self.assertEqual(b.temperament_pending, "owl")
        self.assertEqual(b.longing_ledger.to_dicts(), ledger_before)

    def test_pre_temperament_state_wakes_even_keel(self):
        self.store.save_blob("state", {
            "longing": 0.1, "tick_count": 4000,
            "vitals": {"satiety": 0.8, "hydration": 0.8, "oxygen": 1.0,
                       "vitality": 0.8, "excitement": 0.0},
        })
        a = self.build()
        self.assertEqual(a.temperament, "even-keel")
        self.assertIsNone(a.temperament_pending)

    def test_unknown_saved_strain_degrades_to_even_keel(self):
        self.store.save_blob("state", {
            "temperament": "plasma-9000", "tick_count": 4000,
            "vitals": {"satiety": 0.8, "hydration": 0.8, "oxygen": 1.0,
                       "vitality": 0.8, "excitement": 0.0},
        })
        a = self.build()
        self.assertEqual(a.temperament, "even-keel")


class TestBriarJitter(TempLife):
    def test_draw_is_in_band_and_scales_the_multipliers(self):
        a = self.build()
        a.temperament = "briar"
        j = a._day_jitter()
        self.assertTrue(0.8 <= j <= 1.6)
        self.assertEqual(a._burn_mult("hunger"), j)        # base 1.0 x j
        self.assertEqual(a._burn_mult("excitement"), 1.6)  # pinned, exempt
        self.assertEqual(a._longing_mods()["person"], j)

    def test_same_seed_same_day_same_weather(self):
        a = self.build()
        a.temperament = "briar"
        j_a = a._day_jitter()
        b = self.build()
        b.temperament = "briar"
        self.assertEqual(b._day_jitter(), j_a)

    def test_weather_survives_a_rebuild_and_the_week_turns(self):
        a = self.build()
        a.temperament = "briar"
        j0 = a._day_jitter()
        a.save()
        b = self.build()
        b.temperament = "briar"
        self.assertEqual(b._day_jitter(), j0)      # cached, not redrawn
        a.tick_count += a.DAY_LENGTH
        b.tick_count += b.DAY_LENGTH
        j_a = a._day_jitter()
        j_b = b._day_jitter()
        self.assertEqual(j_a, j_b)                 # same next day, both lives
        self.assertTrue(0.8 <= j_a <= 1.6)
        self.assertNotEqual(j_a, j0)               # a new day, new weather


# ------------------------------------------------------------ THE GATE
FAKE_CHAPTER = ("The chapter speaks of duty, storms at sea, a captain's "
                "obsession, and the whiteness of the whale. " * 20)


def _patch_network():
    stub_forage(forage_mod)
    stub_forage(org)
    org.forage = lambda rng=None: {
        "source": "wikipedia", "title": "Honeybee communication",
        "text": "Honeybees perform a waggle dance describing direction "
                "and distance of flowers — patience, movement, angle, "
                "and sweetness."}
    org.wikisource_chapter = lambda title, numeral: FAKE_CHAPTER


def _scrub(obj):
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items()
                if k not in ("t", "ts")}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


class TestGoldenVector(unittest.TestCase):
    """A full life under Even Keel, against the same life with the
    temperament layer neutralized at the seam. Same harness shape as
    test_determinism.py: stubbed network, real town, real ticks."""

    SEED = 20261019
    TICKS = 160

    def _run(self, home, neutral):
        saved_home = os.environ.get("AETHEL_HOME")
        os.environ["AETHEL_HOME"] = home
        try:
            config.ensure_dirs()
            write_lessons(config)
            _patch_network()
            set_store(Store(config.db_path()))
            store = get_store()
            town = Town(seed=self.SEED, store=store)
            aethel = Aethel(world=town, parents=town.parent_names(),
                            seed=self.SEED)
            aethel._temperament_neutral = neutral
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                for _ in range(self.TICKS):
                    aethel.tick()
            snap = {}
            for stream in ("aethel", "town"):
                snap[stream] = [(t, e, _scrub(d)) for t, e, d
                                in store.recent(stream, limit=10 ** 9)]
                snap[f"{stream}/state"] = _scrub(
                    store.load_blob("state", stream=stream))
            store.close()
            return snap
        finally:
            set_store(Store(":memory:"))
            if saved_home is None:
                os.environ.pop("AETHEL_HOME", None)
            else:
                os.environ["AETHEL_HOME"] = saved_home

    def test_even_keel_equals_neutralized_bit_for_bit(self):
        with tempfile.TemporaryDirectory() as h1, \
                tempfile.TemporaryDirectory() as h2:
            keel = self._run(h1, neutral=False)
            neutral = self._run(h2, neutral=True)
        self.assertGreater(len(keel["aethel"]), 100,
                           "sanity: she actually lived")
        self.assertEqual(keel, neutral)


if __name__ == "__main__":
    unittest.main()
