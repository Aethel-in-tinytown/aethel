"""v0.30 — Two new doors: the Hotel and the Restaurant are real places.

Donald's order: not scenery on the spectator page, but places in her
world, integrated the way the existing public places are. These tests
pin what "real" means here:

1. both ids exist in the canonical registry with narrative names, and
   the town describes them like any other place;
2. both are in the residents' public-place list and in the Markov
   state space (rows still sum to one);
3. residents can actually get there — as a hangout destination, and
   by following Aethel there when their sociability runs low, the
   same two roads that lead to the Tavern;
4. Aethel can choose to go — the crossroads names the Restaurant
   when longing bites (the Tavern's twin urge) and the Hotel when
   her awareness runs low;
5. her longing ledger covers both: fresh lives are seeded with the
   entries, and a pre-v0.30 save gains them additively at rebuild —
   zero ache, stock place weight, nothing else in the ledger moves;
6. a resident standing in the Restaurant survives the town's
   save/load round-trip with the location intact, so the town blob
   the spectator feed reads can carry occupants there.

Isolation: organisms are built against a temp AETHEL_HOME and an
injected temp Store, the convention from test_longing_ledger — the
live diary is never opened.
"""
import os
import tempfile
import unittest

from aethel_pkg import config
from aethel_pkg.journal import set_store
from aethel_pkg.longing import place_id
from aethel_pkg.organism import Aethel
from aethel_pkg.rng import SplitMix64
from aethel_pkg.store import Store
from town_pkg import markov
from town_pkg.places import DENIZEN_PLACES, PLACES
from town_pkg.residents import Denizen
from town_pkg.town import Town

from helpers import StubWorld

NEW_PLACES = ("hotel", "restaurant")


class TestRegistry(unittest.TestCase):
    def test_places_exist_with_names(self):
        self.assertEqual(PLACES["hotel"], "the Hotel")
        self.assertEqual(PLACES["restaurant"], "the Restaurant")

    def test_town_describes_them(self):
        town = Town(seed=11, store=Store(":memory:"))
        self.assertEqual(town.describe("hotel"), "the Hotel")
        self.assertEqual(town.describe("restaurant"), "the Restaurant")

    def test_denizen_places_include_them(self):
        for key in NEW_PLACES:
            self.assertIn(key, DENIZEN_PLACES)

    def test_markov_state_space_includes_them(self):
        for key in NEW_PLACES:
            self.assertIn(key, markov.STATE_SPACE)
        d = Denizen("Test", ["classic", "restaurant"], "classic")
        P = markov.base_matrix(d)
        for row in P:
            self.assertAlmostEqual(sum(row), 1.0, places=12)


class TestResidentReachability(unittest.TestCase):
    def test_restaurant_is_a_valid_transition_target(self):
        d = Denizen("Test", ["classic", "wikipedia"], "classic")
        placemap = {"hackernews": ["John"], "classic": ["Julius"]}
        for _ in range(50):
            row = d.transition_options(placemap, "postbox")
            for place, weight in row:
                self.assertIn(place, set(PLACES) | {"home"})
                self.assertGreater(weight, 0.0)
            d.turn(placemap, "postbox", rng=SplitMix64(7))

    def test_resident_follows_aethel_to_new_places(self):
        # the sociability road: when it runs low, an occupied place
        # (or Aethel's) is a weighted destination — weight 2.0 for her
        for key in NEW_PLACES:
            d = Denizen("Lonely", ["classic"], "classic")
            d.vitals = {"energy": 0.9, "hunger": 0.9, "sociability": 0.1}
            row = dict(d.transition_options({"classic": ["Julius"]}, key))
            self.assertEqual(row[key], 2.0)

    def test_default_roster_treats_restaurant_as_social(self):
        town = Town(seed=5, store=Store(":memory:"))
        hangouts = [h for d in town.denizens for h in d.hangouts]
        self.assertIn("restaurant", hangouts)

    def test_occupant_survives_town_roundtrip(self):
        store = Store(":memory:")
        town = Town(seed=77, store=store)
        town.denizens[0].location = "restaurant"
        town.save()
        town2 = Town(seed=77, store=store)
        self.assertEqual(town2.denizens[0].location, "restaurant")
        self.assertEqual(town2.describe(town2.denizens[0].location),
                         "the Restaurant")


class NewPlaceLife(unittest.TestCase):
    """Base: a real Aethel against a temp home and temp store."""

    def setUp(self):
        self._saved_home = os.environ.get("AETHEL_HOME")
        self.tmp = tempfile.mkdtemp(prefix="aethel-newplaces-")
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


class TestAethelCanGo(NewPlaceLife):
    def test_crossroads_names_restaurant_when_longing(self):
        a = self.build()
        a.longing = 0.9
        a.sleep_pressure = 0.0
        a.awareness = 0.9
        dests = [dest for *_x, dest in a._need_impulse_candidates()]
        self.assertIn("restaurant", dests)
        self.assertIn("hackernews", dests)  # the Tavern urge is untouched

    def test_crossroads_names_hotel_when_unaware(self):
        a = self.build()
        a.longing = 0.0
        a.sleep_pressure = 0.0
        a.awareness = 0.1
        dests = [dest for *_x, dest in a._need_impulse_candidates()]
        self.assertIn("hotel", dests)

    def test_fresh_life_ledger_covers_new_places(self):
        a = self.build()
        for key in NEW_PLACES:
            e = a.longing_ledger.get(place_id(key))
            self.assertIsNotNone(e, f"no ledger entry for {key}")
            self.assertEqual(e["kind"], "place")
            self.assertEqual(e["ache"], 0.0)
            self.assertAlmostEqual(e["w"], 0.45)

    def test_pre_v030_save_gains_entries_additively(self):
        # a pre-v0.30 life: a ledger with one person entry, no new places
        self.store.save_blob("state", {
            "longing": 0.0,
            "tick_count": 9000,
            "vitals": {"satiety": 0.8, "hydration": 0.8, "oxygen": 1.0,
                       "vitality": 0.8, "excitement": 0.0},
            "longing_ledger": [{
                "id": "person:Donald", "kind": "person",
                "label": "Donald", "w": 0.85, "ache": 0.2,
                "since": 12, "open": False,
            }],
        })
        a = self.build()
        donald = a.longing_ledger.get("person:Donald")
        self.assertEqual(donald["ache"], 0.2)  # untouched by the migration
        self.assertEqual(donald["since"], 12)
        for key in NEW_PLACES:
            e = a.longing_ledger.get(place_id(key))
            self.assertIsNotNone(e, f"migration missed {key}")
            self.assertEqual(e["ache"], 0.0)
            self.assertAlmostEqual(e["w"], 0.45)
        # and a rebuild changes nothing further (ensure is idempotent)
        a.save()
        b = self.build()
        self.assertEqual(
            [e["id"] for e in a.longing_ledger.entries],
            [e["id"] for e in b.longing_ledger.entries],
        )


if __name__ == "__main__":
    unittest.main()
