"""Release gates for v0.50: state migration and rollback shape.

A v0.49 town blob (no "mind" keys anywhere, Trey still anchored to the
postbox under the provisional labels) must load with minds defaulted,
nobody's location or legacy vitals reset, and Trey migrated to the Post
Office (D6). A Phase 2 blob must still load through the plain
resident_from_dict path, which is the rollback property: v0.49 code
reads the keys it knows and the rest is inert.
"""

import unittest

from aethel_pkg.store import Store
from town_pkg.residents import resident_from_dict
from town_pkg.town import Town


def by_name(town, name):
    return next(d for d in town.denizens if d.name == name)


def v49_blob(seed=11):
    """A town blob as v0.49 would have saved it."""
    town = Town(seed=seed, store=Store(":memory:"), minds_enabled=False)
    for n in range(120):
        town.poll(n, "postbox")
    blob = town.store.load_blob("state", stream="town")
    for d in blob["denizens"]:
        d.pop("mind", None)
        if d["name"] == "Trey":
            d["home"] = "postbox"
            d["workplace"] = "postbox"
            d["residence"] = "the room behind the postbox"
    return blob


class TestV49BlobLoads(unittest.TestCase):
    def setUp(self):
        self.blob = v49_blob()
        self.store = Store(":memory:")
        self.store.save_blob("state", self.blob, stream="town")
        self.town = Town(store=self.store, minds_enabled=True)

    def test_legacy_state_is_preserved(self):
        saved = {d["name"]: d for d in self.blob["denizens"]}
        for d in self.town.denizens:
            self.assertEqual(d.location, saved[d.name]["location"], d.name)
            self.assertEqual(d.vitals, saved[d.name]["vitals"], d.name)

    def test_minds_default_in(self):
        for name in ("John", "Star", "Julius", "Octavia", "Trey"):
            mind = by_name(self.town, name).mind
            self.assertIsNotNone(mind, name)
            self.assertEqual(mind.state["vitals"], {"purpose": 0.6, "curiosity": 0.5})
            self.assertEqual(mind.state["impulses_judged"], 0)
        for name in ("Donald", "Cassandra"):
            self.assertIsNone(by_name(self.town, name).mind, name)

    def test_trey_migrates_through_to_the_hotel(self):
        # Reviewed diff (v0.52): this test pinned the v0.50 end state
        # (the Post Office). Donald's 2026-11-01 hotel ruling chains
        # the migration onward in the same load: home and residence
        # land at the Hotel, the workplace stays the Post Office,
        # which remains his route base.
        trey = by_name(self.town, "Trey")
        self.assertEqual(trey.home, "hotel")
        self.assertEqual(trey.workplace, "postoffice")
        self.assertEqual(trey.residence, "the keeper's rooms at the Hotel")


class TestRollbackShape(unittest.TestCase):
    def test_minded_dict_loads_without_a_mind_attached(self):
        town = Town(seed=11, store=Store(":memory:"), minds_enabled=True)
        trey = by_name(town, "Trey")
        d = trey.to_dict()
        self.assertIn("mind", d)
        plain = resident_from_dict(d)
        self.assertIsNone(plain.mind)
        self.assertEqual(plain.location, trey.location)
        self.assertEqual(plain.vitals, trey.vitals)
        self.assertEqual(plain.workplace, "postoffice")


if __name__ == "__main__":
    unittest.main()
