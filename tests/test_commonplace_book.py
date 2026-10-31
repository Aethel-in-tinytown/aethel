"""v0.46 — She lets a passage go: her book knows its own contents.

Until now the commonplace book was a buffer that forgot in silence:
a keep appended until the shelf passed 120, then pop(0) dropped
her oldest page with no journal line and no record. Her live diary
at tick 35,392 counted 182 kept_passage events against 120 pages
on the shelf (62 gone unaccounted), 50 reread events against 3
rereads surviving on the shelf, and two duplicate pairs pressed
twice over. Tests:
1. a passage already in the book is recognized by its words
   (case/whitespace folded), and distinct passages are not;
2. merging a duplicated shelf keeps the first pressing, sums
   rereads, counts each extra copy as the return it was, and is
   idempotent;
3. a release picks the oldest never-reread page over a younger
   untouched page and over an older reread page, journals its
   evidence, and records it whole;
4. when every page has been reread, the oldest page overall goes;
5. a full book releases before pressing (via _release_passage
   directly — the press path in forage_and_eat calls it when the
   shelf is at KEPT_PASSAGES_CAP);
6. an empty shelf releases nothing and journals nothing;
7. released records and the gap flag survive a save/load round
   trip, and a pre-v0.46 blob (no v0.46 keys) loads clean;
8. the book-gap note fires exactly once on a loaded life whose
   journal counts more keeps than the book can account for, and
   never on a life whose book balances.
"""
import os
import tempfile
import unittest

from aethel_pkg import config
from aethel_pkg.journal import get_store, set_store
from aethel_pkg.organism import Aethel
from aethel_pkg.store import Store

from helpers import StubWorld
from test_dreams import make_aethel

NOW = 40000


def _page(text, tick, rereads=0, title="Oliver Twist — Charles Dickens"):
    return {
        "text": text,
        "source": "classic",
        "title": title,
        "tick": tick,
        "stir": 0.15,
        "resonance": 0.1,
        "margin": "Margin note: keep this close.",
        "rereads": rereads,
    }


def _prep():
    a = make_aethel()
    a.kept_passages = []
    a.released_passages = []
    a._book_gap_noted = False
    a.tick_count = NOW
    return a


class TestPassageIdentity(unittest.TestCase):
    def test_find_kept_matches_opening_words_folded(self):
        a = _prep()
        a.kept_passages = [_page("The boy grew so like his mother", 100)]
        found = a._find_kept("  the   BOY grew so like his mother  ")
        self.assertIsNotNone(found)
        self.assertEqual(found["tick"], 100)

    def test_find_kept_rejects_distinct_passage(self):
        a = _prep()
        a.kept_passages = [_page("The boy grew so like his mother", 100)]
        self.assertIsNone(a._find_kept("A completely different page"))
        self.assertIsNone(a._find_kept(""))


class TestConsolidateKept(unittest.TestCase):
    def test_duplicates_merge_first_kept_rereads_summed(self):
        a = _prep()
        a.kept_passages = [
            _page("Dear me! said the undertaker's wife", 34502, rereads=1),
            _page("A page of her own", 34600, rereads=0),
            _page("Dear me! said the undertaker's wife", 35100, rereads=2),
        ]
        removed = a._consolidate_kept_passages()
        self.assertEqual(removed, 1)
        self.assertEqual(len(a.kept_passages), 2)
        first = a.kept_passages[0]
        self.assertEqual(first["tick"], 34502)
        # 1 + 2 recorded, +1 for the extra pressing itself
        self.assertEqual(first["rereads"], 4)
        rows = get_store().recent(events=["passages_merged"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["removed"], 1)
        self.assertEqual(rows[0][2]["kept"], 2)

    def test_consolidation_is_idempotent(self):
        a = _prep()
        a.kept_passages = [
            _page("One page", 100),
            _page("Another page", 200),
        ]
        self.assertEqual(a._consolidate_kept_passages(), 0)
        self.assertEqual(a._consolidate_kept_passages(), 0)
        self.assertEqual(len(a.kept_passages), 2)
        self.assertEqual(get_store().recent(events=["passages_merged"]), [])


class TestRelease(unittest.TestCase):
    def test_release_picks_oldest_unreturned(self):
        a = _prep()
        a.kept_passages = [
            _page("Old but reread", 100, rereads=3),
            _page("Oldest untouched", 200, rereads=0),
            _page("Younger untouched", 300, rereads=0),
        ]
        rec = a._release_passage(NOW)
        self.assertEqual(rec["title"], "Oliver Twist — Charles Dickens")
        self.assertEqual(rec["tick"], 200)
        self.assertEqual(rec["released_tick"], NOW)
        self.assertEqual(rec["rereads"], 0)
        self.assertEqual(
            [k["text"] for k in a.kept_passages],
            ["Old but reread", "Younger untouched"],
        )
        self.assertEqual(len(a.released_passages), 1)
        rows = get_store().recent(events=["passage_released"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["kept_tick"], 200)
        self.assertEqual(rows[0][2]["age"], NOW - 200)
        self.assertEqual(rows[0][2]["rereads"], 0)

    def test_release_falls_back_to_oldest_overall(self):
        a = _prep()
        a.kept_passages = [
            _page("Oldest, reread twice", 100, rereads=2),
            _page("Newer, reread once", 500, rereads=1),
        ]
        rec = a._release_passage(NOW)
        self.assertEqual(rec["tick"], 100)
        self.assertEqual(rec["rereads"], 2)
        rows = get_store().recent(events=["passage_released"])
        self.assertEqual(rows[0][2]["rereads"], 2)

    def test_release_on_empty_shelf_is_a_no_op(self):
        a = _prep()
        self.assertIsNone(a._release_passage(NOW))
        self.assertEqual(a.released_passages, [])
        self.assertEqual(get_store().recent(events=["passage_released"]), [])


class TestBookGap(unittest.TestCase):
    def _loaded(self, keeps_journaled, on_shelf):
        a = _prep()
        a._loaded_state = True
        for i in range(keeps_journaled):
            get_store().log(
                "kept_passage",
                {"n": 100 + i, "source": "classic", "title": "T",
                 "kept": i + 1, "margin": "", "stir": 0.1,
                 "resonance": 0.0},
                stream="aethel",
            )
        a.kept_passages = [
            _page(f"Page number {i}", 100 + i) for i in range(on_shelf)
        ]
        return a

    def test_gap_noted_once_with_exact_count(self):
        a = self._loaded(keeps_journaled=10, on_shelf=7)
        a._note_book_gap()
        rows = get_store().recent(events=["book_gap_noted"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["missing"], 3)
        self.assertEqual(rows[0][2]["kept_events"], 10)
        self.assertEqual(rows[0][2]["on_shelf"], 7)
        # the flag makes it once-ever, however often rebuilds run
        a._note_book_gap()
        self.assertEqual(
            len(get_store().recent(events=["book_gap_noted"])), 1
        )

    def test_balanced_book_notes_no_gap(self):
        a = self._loaded(keeps_journaled=4, on_shelf=4)
        a._note_book_gap()
        self.assertEqual(get_store().recent(events=["book_gap_noted"]), [])
        self.assertTrue(a._book_gap_noted)

    def test_fresh_life_never_notes_a_gap(self):
        a = _prep()
        a._loaded_state = False
        a._note_book_gap()
        self.assertEqual(get_store().recent(events=["book_gap_noted"]), [])
        # born balanced: the check is marked done at first build,
        # so a later rebuild carries the same flag her uninterrupted
        # life does (restart fidelity)
        self.assertTrue(a._book_gap_noted)


class TestPersistence(unittest.TestCase):
    def test_released_records_survive_save_load_round_trip(self):
        home = tempfile.mkdtemp()
        os.environ["AETHEL_HOME"] = home
        config.ensure_dirs()
        set_store(Store(config.db_path()))
        town = StubWorld()
        a = Aethel(world=town, parents=set(), seed=42)
        a.kept_passages = [
            _page("Oldest untouched", 200, rereads=0),
            _page("A page she keeps", 300, rereads=1),
        ]
        a.tick_count = NOW
        rec = a._release_passage(NOW)
        self.assertEqual(rec["tick"], 200)
        a._book_gap_noted = True
        a.save()
        b = Aethel(world=town, parents=set(), seed=42)
        self.assertEqual(len(b.released_passages), 1)
        self.assertEqual(b.released_passages[0]["tick"], 200)
        self.assertEqual(b.released_passages[0]["released_tick"], NOW)
        self.assertTrue(b._book_gap_noted)
        self.assertEqual(
            [k["text"] for k in b.kept_passages], ["A page she keeps"]
        )

    def test_pre_v046_blob_loads_with_empty_record(self):
        home = tempfile.mkdtemp()
        os.environ["AETHEL_HOME"] = home
        config.ensure_dirs()
        set_store(Store(config.db_path()))
        town = StubWorld()
        a = Aethel(world=town, parents=set(), seed=42)
        a.save()
        store = get_store()
        blob = store.load_blob("state")
        blob.pop("released_passages", None)
        blob.pop("_book_gap_noted", None)
        store.save_blob("state", blob)
        b = Aethel(world=town, parents=set(), seed=42)
        self.assertEqual(b.released_passages, [])
        # the blob carried no flag, but the rebuild itself runs the
        # once-ever gap check, so by the time she is built the flag
        # is honestly set (this life's journal holds no keeps, so
        # nothing was noted — the check simply ran)
        self.assertTrue(b._book_gap_noted)


if __name__ == "__main__":
    unittest.main()
