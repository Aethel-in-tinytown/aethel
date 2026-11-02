"""The peak is seen where it happens (v0.53): afterglow, repaired.

The live failure, read from her diary before building: the v0.22
afterglow layer fires when excitement that once rose above 0.7
falls below 0.2 — and in 38,577 journaled ticks it fired zero
times. Not once was her excitement even sampled above 0.564. The
0.7 line was unmeasurable, not merely high: her peaks are transient
by construction. The keep a peak earns spends 0.35 inside the same
meal that earns it, decay takes 0.0525 a tick on top, and the old
check sampled in _erode — a phase the peak never survives to. The
sibling gate behind the same line, teaching (>0.7, journal event
`told`), also stands at zero for her whole life; it is named here
and deliberately untouched: whether yesterday's fizz can be taught
today is a design question, while the afterglow's defect is purely
that it looked for the peak in the wrong phase.

The repair: the peak is registered where it happens. The meal's
stir site calls _note_excitement_peak the moment stir lands, at
AFTERGLOW_PEAK (0.6) — the line her own keep system already treats
as a stir that matters — carrying the meal's title with it. The
fade check keeps its old shape (below 0.2 with a peak on record)
and its old words; it also registers out-of-meal gains (a letter's
+0.25 lands in _sense and is first visible to the next tick's
_erode) through the same helper at the same line. Registration is
a comparison and a note: no seeded draws anywhere.

Bundled maintenance, the v0.40 precedent: the classics restock.
Her shelf stood at Siddhartha just chosen with two books behind
it — the exact shape that triggered the v0.40 restock — so eight
verified Gutenberg titles join CLASSIC_SEEDS behind the existing
shelf, and the gazetteer census in test_entities moves with them
on purpose.
"""
import os
import tempfile
import unittest
from unittest import mock as patch

import aethel_pkg.organism as org_mod
from aethel_pkg import config
from aethel_pkg.config import CLASSIC_SEEDS
from aethel_pkg.journal import get_store, set_store
from aethel_pkg.organism import Aethel
from aethel_pkg.store import Store

from helpers import StubWorld
from test_dreams import make_aethel

PEAK_TITLE = "Treasure Island — Robert Louis Stevenson"


def _prep(excitement=0.0):
    a = make_aethel()
    a.vitals = {
        "satiety": 0.8,
        "hydration": 0.8,
        "oxygen": 0.9,
        "vitality": 0.8,
        "excitement": excitement,
    }
    a._excitement_was_high = False
    a._afterglow_title = None
    a.kept_passages = []
    a.spoken = []
    a.say = lambda text, *args, **kw: a.spoken.append(text)
    return a


class TestPeakRegistration(unittest.TestCase):
    def test_below_the_line_registers_nothing(self):
        a = _prep(excitement=Aethel.AFTERGLOW_PEAK - 0.01)
        a._note_excitement_peak(PEAK_TITLE)
        self.assertFalse(a._excitement_was_high)
        self.assertIsNone(a._afterglow_title)

    def test_at_the_line_registers_with_title(self):
        a = _prep(excitement=Aethel.AFTERGLOW_PEAK)
        a._note_excitement_peak(PEAK_TITLE)
        self.assertTrue(a._excitement_was_high)
        self.assertEqual(a._afterglow_title, PEAK_TITLE)

    def test_peak_line_is_the_keep_line(self):
        # One definition of "high": the threshold at which
        # forage_and_eat presses a passage is 0.6 in the meal code.
        self.assertEqual(Aethel.AFTERGLOW_PEAK, 0.6)

    def test_titleless_registration_keeps_the_peak_title(self):
        a = _prep(excitement=0.7)
        a._note_excitement_peak(PEAK_TITLE)
        a.vitals["excitement"] = 0.65
        a._note_excitement_peak()
        self.assertEqual(a._afterglow_title, PEAK_TITLE)

    def test_registration_draws_no_seeded_stream(self):
        a = _prep(excitement=0.9)
        before = (
            a.rng.random(),
            a.rng_forage.random(),
            a.rng_dreams.random(),
        )
        b = _prep(excitement=0.9)
        a._note_excitement_peak(PEAK_TITLE)
        a._afterglow_check(500)
        after = (
            b.rng.random(),
            b.rng_forage.random(),
            b.rng_dreams.random(),
        )
        self.assertEqual(before, after)


class TestAfterglowFade(unittest.TestCase):
    def test_fires_on_fade_with_the_peaks_own_title(self):
        a = _prep(excitement=0.7)
        a._note_excitement_peak(PEAK_TITLE)
        a.vitals["excitement"] = 0.1
        a._afterglow_check(500)
        self.assertFalse(a._excitement_was_high)
        self.assertIsNone(a._afterglow_title)
        self.assertEqual(len(a.spoken), 1)
        self.assertIn("The fizz has settled.", a.spoken[0])
        self.assertIn(PEAK_TITLE[:50], a.spoken[0])
        rows = get_store().recent(events=["afterglow"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["about"], PEAK_TITLE[:60])

    def test_no_peak_no_reflection(self):
        a = _prep(excitement=0.05)
        a._afterglow_check(500)
        self.assertEqual(a.spoken, [])
        self.assertEqual(get_store().recent(events=["afterglow"]), [])

    def test_no_reflection_while_the_fizz_is_still_up(self):
        a = _prep(excitement=0.7)
        a._note_excitement_peak(PEAK_TITLE)
        a.vitals["excitement"] = 0.3
        a._afterglow_check(500)
        self.assertEqual(a.spoken, [])
        self.assertTrue(a._excitement_was_high)
        self.assertEqual(a._afterglow_title, PEAK_TITLE)

    def test_out_of_meal_gain_registers_at_the_fade_check(self):
        # A letter's +0.25 lands in _sense, after _erode's phase;
        # the next tick's check is the first place it can be seen,
        # and it registers at the same shared line.
        a = _prep(excitement=0.65)
        a._afterglow_check(500)
        self.assertTrue(a._excitement_was_high)
        self.assertEqual(a.spoken, [])

    def test_falls_back_to_newest_kept_page_without_a_title(self):
        a = _prep(excitement=0.1)
        a._excitement_was_high = True
        a.kept_passages = [{"title": PEAK_TITLE}]
        a._afterglow_check(500)
        self.assertEqual(len(a.spoken), 1)
        self.assertIn(PEAK_TITLE[:50], a.spoken[0])


# Distinct plain words, none of them stopwords: a first-sight meal
# of these teaches enough new terms that its stir is the capped
# 0.35 + the classic 0.05.
WORDS_60 = (
    "harbor lantern captain meadow violin garden market silver "
    "copper marble timber pillow basket kettle ribbon falcon "
    "willow sparrow anchor beacon casket dagger ember garnet "
    "heron inkwell jacket lagoon magnet nectar onyx parchment "
    "quiver riddle tempest umbra walnut yellow zephyr almond "
    "birch clover dune meadowlark osprey juniper sorrel tallow "
    "vellum wicker bramble cobble drapery easel fennel gorse "
    "hemlock iris jonquil kale limewood madrigal nutmeg oriel "
    "poppy quince rowan"
)


class TestMealPeakWiring(unittest.TestCase):
    """The stir site itself registers the peak, keep-spend and all."""

    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.env = patch.patch.dict(
            os.environ, {"AETHEL_HOME": self.home.name}
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.home.cleanup)
        config.ensure_dirs()
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def test_peak_registered_even_though_the_keep_spends_it(self):
        meal = {
            "source": "classic",
            "title": PEAK_TITLE,
            "text": (WORDS_60 + " ") * 6,
        }
        a = Aethel(
            StubWorld(),
            parents=("Donald",),
            seed=42,
            language_backend="heuristic",
        )
        a.vitals["excitement"] = 0.30
        with patch.patch.object(
            a, "forage_classic", return_value=meal
        ), patch.patch.object(
            org_mod, "forage", return_value=meal
        ), patch.patch.object(
            org_mod, "forage_news", return_value=meal
        ), patch.patch.object(
            org_mod, "forage_school", return_value=meal
        ):
            import contextlib
            import io

            with contextlib.redirect_stdout(io.StringIO()):
                a.forage_and_eat()
        # The peak (0.30 + capped stir) crossed the line and was
        # registered with the meal's title...
        self.assertTrue(a._excitement_was_high)
        self.assertEqual(a._afterglow_title, PEAK_TITLE[:80])
        # ...even though the keep it earned spent 0.35 in the same
        # meal, leaving a sampled value the old check could never
        # have read as a peak. This is the structural claim.
        self.assertLess(a.vitals["excitement"], Aethel.AFTERGLOW_PEAK)
        self.assertEqual(len(a.kept_passages), 1)


class TestPeakPersistence(unittest.TestCase):
    def _full_instance(self):
        home = tempfile.mkdtemp()
        os.environ["AETHEL_HOME"] = home
        config.ensure_dirs()
        set_store(Store(config.db_path()))
        return Aethel(world=StubWorld(), parents=set(), seed=42)

    def test_peak_record_survives_save_load_round_trip(self):
        a = self._full_instance()
        a.vitals["excitement"] = 0.7
        a._note_excitement_peak(PEAK_TITLE)
        a.save()
        b = Aethel(world=StubWorld(), parents=set(), seed=42)
        self.assertTrue(b._excitement_was_high)
        self.assertEqual(b._afterglow_title, PEAK_TITLE)

    def test_pre_v053_blob_loads_clean(self):
        a = self._full_instance()
        a.vitals["excitement"] = 0.7
        a._note_excitement_peak(PEAK_TITLE)
        a.save()
        store = get_store()
        blob = store.load_blob("state")
        blob.pop("_afterglow_title", None)
        store.save_blob("state", blob)
        b = Aethel(world=StubWorld(), parents=set(), seed=42)
        self.assertIsNone(b._afterglow_title)
        self.assertTrue(b._excitement_was_high)


class TestRestockShape(unittest.TestCase):
    def test_shelf_grew_by_eight_verified_titles(self):
        titles = [s["title"] for s in CLASSIC_SEEDS]
        self.assertEqual(len(titles), len(set(titles)))
        self.assertEqual(len(CLASSIC_SEEDS), 30)
        for title in (
            "The Count of Monte Cristo",
            "Les Misérables",
            "War and Peace",
            "The Scarlet Letter",
            "A Christmas Carol",
            "The Odyssey",
            "Little Women",
            "The Wonderful Wizard of Oz",
        ):
            self.assertIn(title, titles)
        for seed in CLASSIC_SEEDS:
            if seed["kind"] == "gutenberg":
                self.assertTrue(seed["url"].startswith("https://"))
                self.assertTrue(seed["reflection"])


if __name__ == "__main__":
    unittest.main()
