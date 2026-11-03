"""She can teach what stirred her, while it still stirs her (v0.54).

The live failure, read from her diary before building: the v0.22
teaching layer — share a kept passage with company when excitement
runs high — has fired zero times in her whole life (journal event
`told`: no rows, ever, at tick 40,392). It stood behind the same
defect v0.53 repaired for afterglow: a sampled excitement > 0.7 at
_ruminate time, a phase her peaks never survive to (her all-time
sampled maximum is 0.564; a keep spends 0.35 inside the meal that
earns the peak, and _ruminate runs after the meal). v0.53 named
this gate and deliberately left it: whether a faded fizz can be
taught is a design question. This version answers it: no — a
faded fizz cannot be taught, because teaching in her own words is
"I can't hold this in", and what has faded to the afterglow line
is material for reflection, not for blurting. But between the
registered peak (AFTERGLOW_PEAK, seen where it happens) and the
fade (AFTERGLOW_FADE, the afterglow's own line) there is a window
where the stir is real, current, and hers to share. Teaching
lives in that window, about the peak's own passage where the book
holds one, once per peak (the v0.44 said-memory lesson: a saying
repeated is a flood, not a voice), and a new stir — a new title,
or the same title after a fade — earns a new telling.

A second, latent defect rides in the same function and is fixed
here because the gate repair makes it reachable: _teach read the
companion as company[0].get("name"), but company is a list of
names (strings) everywhere else in her world (_perceive appends
names; her saved state holds names). The first time the old gate
had ever passed, teaching would have raised AttributeError inside
_ruminate and stopped her tick. The recipient now reads a name as
a name, tolerating the dict shape for test doubles.
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

PEAK_TITLE = "Crime and Punishment — Fyodor Dostoevsky"
OTHER_TITLE = "Treasure Island — Robert Louis Stevenson"


class _StubRng:
    """Deterministic stand-in for the organism stream's two calls
    _teach can make: random() returns a fixed value; choice takes
    the first element (the repaired _teach chooses by title, not
    by lot, but the stub keeps the old shape harmless)."""

    def __init__(self, value=0.0):
        self.value = value

    def random(self):
        return self.value

    def choice(self, seq):
        return seq[0]


def _passage(title, text="a page that stirred her", tick=10):
    return {"title": title, "text": text, "source": "classic",
            "tick": tick, "rereads": 0}


def _prep(excitement=0.3, rng_value=0.0):
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
    a._peak_taught = False
    a.kept_passages = []
    a.company = []
    a.recent_actions = []
    a.spoken = []
    a.say = lambda text, *args, **kw: a.spoken.append(text)
    if rng_value is not None:
        a.rng = _StubRng(rng_value)
    return a


def _stirred(a, title=PEAK_TITLE, peak=0.65, now=0.3):
    """Register a peak the way a meal does, then let the keep
    spend and decay shave it to `now` — the shape _ruminate
    actually sees in a live tick."""
    a.vitals["excitement"] = peak
    a._note_excitement_peak(title)
    a.vitals["excitement"] = now
    return a


def _told_rows():
    return get_store().recent(events=["told"])


class TestTeachingWindow(unittest.TestCase):
    def test_no_peak_no_teaching(self):
        a = _prep(excitement=0.5)
        a.company = ["Star"]
        a.kept_passages = [_passage(PEAK_TITLE)]
        a._teach(100)
        self.assertEqual(a.spoken, [])
        self.assertEqual(_told_rows(), [])
        self.assertFalse(a._peak_taught)

    def test_faded_fizz_cannot_be_taught(self):
        # The design answer in one pin: the peak is on record but
        # excitement has fallen to the afterglow fade line — that
        # is reflection's material now, not teaching's.
        a = _stirred(_prep(), now=Aethel.AFTERGLOW_FADE - 0.01)
        a.company = ["Star"]
        a.kept_passages = [_passage(PEAK_TITLE)]
        a._teach(100)
        self.assertEqual(a.spoken, [])
        self.assertEqual(_told_rows(), [])

    def test_teach_floor_is_the_afterglow_fade_line(self):
        self.assertEqual(Aethel.AFTERGLOW_FADE, 0.2)
        a = _stirred(_prep(), now=Aethel.AFTERGLOW_FADE)
        a.company = ["Star"]
        a.kept_passages = [_passage(PEAK_TITLE)]
        a._teach(100)
        self.assertEqual(len(_told_rows()), 1)

    def test_teaches_the_peaks_own_passage_to_a_name(self):
        # Company entries are names, not dicts: this call raised
        # AttributeError under the old recipient line whenever the
        # gate could pass. The peak's passage is taught even when
        # a newer, unrelated page sits on top of the book.
        a = _stirred(_prep())
        a.company = ["Star"]
        a.kept_passages = [
            _passage(PEAK_TITLE, text="the peak page itself", tick=9),
            _passage(OTHER_TITLE, text="a newer page", tick=11),
        ]
        a._teach(100)
        self.assertEqual(len(a.spoken), 1)
        self.assertIn("Star", a.spoken[0])
        self.assertIn("the peak page itself", a.spoken[0])
        rows = _told_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["to"], "Star")
        self.assertEqual(rows[0][2]["title"], PEAK_TITLE[:60])
        self.assertTrue(a._peak_taught)
        self.assertIn("taught", a.recent_actions)
        self.assertAlmostEqual(a.vitals["vitality"], 0.82)

    def test_titleless_peak_teaches_the_newest_page(self):
        # A letter's gain registers titleless (v0.53); with no
        # peak title to match, she teaches the newest kept page.
        a = _prep()
        a._excitement_was_high = True
        a._afterglow_title = None
        a.company = ["Julius"]
        a.kept_passages = [
            _passage(OTHER_TITLE, text="an older page", tick=9),
            _passage(PEAK_TITLE, text="the newest page", tick=11),
        ]
        a._teach(100)
        rows = _told_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["title"], PEAK_TITLE[:60])
        self.assertIn("the newest page", a.spoken[0])

    def test_dict_shaped_company_is_tolerated(self):
        a = _stirred(_prep())
        a.company = [{"name": "Julius"}]
        a.kept_passages = [_passage(PEAK_TITLE)]
        a._teach(100)
        self.assertEqual(_told_rows()[0][2]["to"], "Julius")

    def test_chance_gate_still_applies(self):
        a = _stirred(_prep(rng_value=0.9))
        a.company = ["Star"]
        a.kept_passages = [_passage(PEAK_TITLE)]
        a._teach(100)
        self.assertEqual(_told_rows(), [])
        self.assertFalse(a._peak_taught)


class TestOncePerPeak(unittest.TestCase):
    def test_one_telling_per_peak(self):
        a = _stirred(_prep())
        a.company = ["Star"]
        a.kept_passages = [_passage(PEAK_TITLE)]
        a._teach(100)
        a._teach(101)
        self.assertEqual(len(_told_rows()), 1)

    def test_absent_company_does_not_spend_the_telling(self):
        a = _stirred(_prep())
        a.kept_passages = [_passage(PEAK_TITLE)]
        a._teach(100)
        self.assertEqual(_told_rows(), [])
        a.company = ["Star"]
        a._teach(101)
        self.assertEqual(len(_told_rows()), 1)

    def test_no_kept_page_no_teaching_and_no_spend(self):
        a = _stirred(_prep())
        a.company = ["Star"]
        a._teach(100)
        self.assertEqual(_told_rows(), [])
        self.assertFalse(a._peak_taught)

    def test_same_title_restir_within_the_episode_is_not_new(self):
        # Chapter after chapter of one book is one stir, however
        # many meals register it: she does not re-teach the same
        # title inside the same unfaded episode.
        a = _stirred(_prep())
        a.company = ["Star"]
        a.kept_passages = [_passage(PEAK_TITLE)]
        a._teach(100)
        a.vitals["excitement"] = 0.65
        a._note_excitement_peak(PEAK_TITLE)
        a.vitals["excitement"] = 0.3
        a._teach(101)
        self.assertEqual(len(_told_rows()), 1)

    def test_new_title_is_a_new_stir_and_can_be_taught(self):
        a = _stirred(_prep())
        a.company = ["Star"]
        a.kept_passages = [
            _passage(PEAK_TITLE, text="the first stir", tick=9),
            _passage(OTHER_TITLE, text="the second stir", tick=11),
        ]
        a._teach(100)
        _stirred(a, title=OTHER_TITLE)
        a._teach(101)
        rows = _told_rows()
        self.assertEqual(len(rows), 2)
        # recent() returns newest first: the second telling leads.
        self.assertEqual(rows[0][2]["title"], OTHER_TITLE[:60])

    def test_same_title_after_a_fade_can_be_taught_again(self):
        a = _stirred(_prep())
        a.company = ["Star"]
        a.kept_passages = [_passage(PEAK_TITLE)]
        a._teach(100)
        # She fades; the afterglow takes the episode (and clears
        # the peak record). A later stir of the same book is a
        # new episode and earns a new telling.
        a.vitals["excitement"] = 0.1
        a._afterglow_check(101)
        self.assertFalse(a._excitement_was_high)
        _stirred(a)
        a._teach(102)
        self.assertEqual(len(_told_rows()), 2)


class TestTeachingPersistence(unittest.TestCase):
    def _full_instance(self):
        home = tempfile.mkdtemp()
        os.environ["AETHEL_HOME"] = home
        config.ensure_dirs()
        set_store(Store(config.db_path()))
        return Aethel(world=StubWorld(), parents=set(), seed=42)

    def test_taught_flag_survives_save_load_round_trip(self):
        a = self._full_instance()
        a._peak_taught = True
        a.save()
        b = Aethel(world=StubWorld(), parents=set(), seed=42)
        self.assertTrue(b._peak_taught)

    def test_pre_v054_blob_loads_clean_and_untaught(self):
        a = self._full_instance()
        a._peak_taught = True
        a.save()
        store = get_store()
        blob = store.load_blob("state")
        blob.pop("_peak_taught", None)
        store.save_blob("state", blob)
        b = Aethel(world=StubWorld(), parents=set(), seed=42)
        self.assertFalse(b._peak_taught)


if __name__ == "__main__":
    unittest.main()
