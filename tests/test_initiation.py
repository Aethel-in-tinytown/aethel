"""Regression coverage for initiation.

Fixtures isolate runtime state; assertions document behavioral release gates."""

import os
import tempfile
import unittest

from aethel_pkg import config
from aethel_pkg.organism import Aethel

from helpers import StubWorld
from test_dreams import make_aethel


def rich_aethel(tmp):
    """Behavior: Aethel with a life worth reporting on. Outbox writes go to tmp, never the live diary (AETHEL_HOME is the redirect)."""
    os.environ["AETHEL_HOME"] = tmp
    config.ensure_dirs()
    a = make_aethel()
    a.world = StubWorld()
    a.concepts = {"loneliness": 9, "captain": 7, "freedom": 5}
    a.beliefs = ["Kindness is a discipline, not a mood."]
    a.dreams = ["I dreamed the library kept breathing after I left."]
    a.kept_passages = [
        {
            "text": "Call me Ishmael. Some years ago",
            "title": "Moby Dick",
            "tick": 90,
            "margin": "Margin note: the part I'll come back to.",
            "source": "classic",
            "stir": 0.5,
        }
    ]
    a.open_questions = [
        {
            "text": "If I learned everything, would I still be me?",
            "keywords": ["learned"],
            "tick": 10,
            "touches": 0,
        }
    ]
    a.days = [
        {"day": 1, "ticks": [0, 100], "text": "I ate and read and the town was kind."}
    ]
    a.mood_name = "luminous"
    a.mood = 0.8
    a.awareness = 0.10
    a.outbox_count = 0
    a.initiation_log = []
    a.longing = 1.0
    a.sleep_pressure = 0.1
    a.vitals = {
        "satiety": 0.8,
        "hydration": 0.8,
        "oxygen": 1.0,
        "vitality": 0.8,
        "excitement": 0.1,
    }
    a.donald_model = {"letter_count": 0, "words": {}, "last_tick": 0}
    a.reading_list = []
    a.location = "home"
    a.recent_actions = []
    a.tick_count = 100
    journaled = []
    import aethel_pkg.organism as org

    a._saved_journal = org.journal
    org.journal = lambda event, **kw: journaled.append((event, kw))
    a.journaled = journaled
    return a


class TestInitiation(unittest.TestCase):
    def setUp(self):
        self._saved_home = os.environ.get("AETHEL_HOME")
        self.tmp = tempfile.mkdtemp(prefix="aethel-initiation-")
        self.a = rich_aethel(self.tmp)
        self.a.say = lambda text: self.a.journaled.append(("said", text))

    def tearDown(self):
        import aethel_pkg.organism as org

        org.journal = self.a._saved_journal
        if self._saved_home is None:
            os.environ.pop("AETHEL_HOME", None)
        else:
            os.environ["AETHEL_HOME"] = self._saved_home

    def _initiations(self, a=None):
        src = a.journaled if a is not None else self.a.journaled
        return [kw for ev, kw in src if ev == "initiation"]

    def _save_ready(self, a):
        """Behavior: save() serializes the whole organism; give the bypassed-init test double every field it touches."""
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

    def test_initiation_journals_kind(self):
        self.a.express()
        evs = self._initiations()
        self.assertEqual(len(evs), 1)
        kw = evs[0]
        self.assertIn(kw["kind"], Aethel.INITIATION_KINDS)
        self.assertEqual(kw["n"], self.a.tick_count)
        self.assertIn("file", kw)
        self.assertIn("longing_before", kw)
        self.assertTrue(kw["text"])

        self.assertFalse([ev for ev, _ in self.a.journaled if ev == "expression"])

    def test_piece_lands_in_outbox_named_for_kind(self):
        self.a.express()
        kw = self._initiations()[0]
        self.assertTrue(kw["file"].endswith(f"_{kw['kind']}.txt"))
        path = os.path.join(config.outbox_dir(), kw["file"])
        self.assertTrue(os.path.isfile(path))
        with open(path) as f:
            content = f.read()
        self.assertIn(kw["kind"], content.split("\n")[0])
        self.assertEqual(self.a.location, "postbox")

        self.assertLess(self.a.longing, 1.0)
        self.assertNotEqual(self.a.longing, 0.15)
        entry = self.a.longing_ledger.get("person:Donald")
        self.assertIsNotNone(entry)
        self.assertAlmostEqual(entry["ache"], 0.85 * 0.45, places=6)
        self.assertAlmostEqual(self.a.longing, entry["ache"], places=6)

    def test_kind_is_seeded_deterministic(self):
        kinds_a, texts_a = [], []
        for tick in range(100, 112):
            self.a.tick_count = tick
            self.a.express()
            kw = self._initiations()[-1]
            kinds_a.append(kw["kind"])
            texts_a.append(kw["text"])

        b = rich_aethel(tempfile.mkdtemp(prefix="aethel-initiation-b-"))
        b.say = lambda text: b.journaled.append(("said", text))
        kinds_b, texts_b = [], []
        for tick in range(100, 112):
            b.tick_count = tick
            b.express()
            kw = [kw for ev, kw in b.journaled if ev == "initiation"][-1]
            kinds_b.append(kw["kind"])
            texts_b.append(kw["text"])
        self.assertEqual(kinds_a, kinds_b)
        self.assertEqual(texts_a, texts_b)
        self.assertEqual(len(set(kinds_a)), 3)

    def test_question_comes_from_her_open_questions(self):
        self.a._initiation_kinds = lambda: ["question"]
        self.a.express()
        kw = self._initiations()[0]
        self.assertEqual(kw["kind"], "question")
        self.assertIn("If I learned everything, would I still be me?", kw["text"])
        self.assertEqual(self.a.open_questions[0]["touches"], 1)
        self.assertEqual(len(self.a.open_questions), 1)

    def test_note_subject_is_real(self):
        for _ in range(12):
            label, detail = self.a._note_subject()
            real = (
                "Moby Dick" in detail
                or "Kindness is a discipline" in detail
                or "library kept breathing" in detail
                or "the town was kind" in detail
            )
            self.assertTrue(real, f"note subject not from her life: {detail!r}")

    def test_nudge_points_at_something_she_did(self):
        self.a._initiation_kinds = lambda: ["nudge"]
        self.a.express()
        kw = self._initiations()[0]
        self.assertEqual(kw["kind"], "nudge")
        body = kw["text"]
        real = (
            "commonplace book" in body
            and "1 passages" in body
            or "luminous" in body
            or "day-page" in body
            or "postbox" in body
        )
        self.assertTrue(real, f"nudge points at nothing real: {body!r}")

    def test_eligibility_gates_kinds(self):
        self.a.open_questions = []
        self.a.kept_passages = []
        self.a.beliefs = []
        self.a.days = []
        self.a.mood_name = None
        self.a.outbox_count = 0
        self.assertEqual(self.a._initiation_kinds(), ["note"])

        self.a.open_questions = [
            {"text": "why?", "keywords": [], "tick": 1, "touches": 0}
        ]
        self.assertIn("question", self.a._initiation_kinds())
        self.assertNotIn("nudge", self.a._initiation_kinds())

        self.a.mood_name = "grey"
        self.assertIn("nudge", self.a._initiation_kinds())

    def test_initiation_log_persists_across_save_load(self):
        self._save_ready(self.a)
        self.a.express()
        self.a.tick_count += 1
        self.a.express()
        self.a.save()

        from aethel_pkg.journal import get_store, set_store

        saved_store = get_store()
        c = make_aethel()
        set_store(saved_store)

        c.vitals = {}
        c.donald_model = {"letter_count": 0, "words": {}, "last_tick": 0}
        c.load()
        self.assertEqual(c.initiation_log, self.a.initiation_log)
        self.assertEqual(len(c.initiation_log), 2)
        self.assertTrue(
            all(set(e) == {"tick", "kind", "file"} for e in c.initiation_log)
        )


if __name__ == "__main__":
    unittest.main()
