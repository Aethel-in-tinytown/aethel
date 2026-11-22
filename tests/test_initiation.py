"""v0.26 — she writes first.

Initiation is first-class: her unprompted pieces arrive with an explicit
kind — a NOTE reporting something real from her life, a QUESTION drawn
from her actual open questions, a NUDGE inviting Donald to come see
something she did — journaled as `initiation` events with the kind
recorded. Tests:
1. express() journals one `initiation` event with a recorded kind in
   the three kinds, carrying file, longing_before, and a text excerpt;
2. the piece lands in her outbox named <tick>_<kind>.txt;
3. the kind is seeded: same seed, same kind sequence, same words;
4. a question comes from her real open questions (and touches it);
5. a note's subject is drawn from her real state (kept passage, belief,
   dream, day-page);
6. a nudge points at something she really did (shelf, named weather,
   day-page, postbox);
7. eligibility: no open questions -> no question kind; nothing to show
   -> no nudge;
8. the initiation log persists across save/load (a restart is a nap).
"""
import os
import tempfile
import unittest

from aethel_pkg import config
from aethel_pkg.organism import Aethel

from helpers import StubWorld
from test_dreams import make_aethel


def rich_aethel(tmp):
    """Aethel with a life worth reporting on. Outbox writes go to tmp,
    never the live diary (AETHEL_HOME is the redirect)."""
    os.environ["AETHEL_HOME"] = tmp
    config.ensure_dirs()
    a = make_aethel()
    a.world = StubWorld()
    a.concepts = {"loneliness": 9, "captain": 7, "freedom": 5}
    a.beliefs = ["Kindness is a discipline, not a mood."]
    a.dreams = ["I dreamed the library kept breathing after I left."]
    a.kept_passages = [{
        "text": "Call me Ishmael. Some years ago", "title": "Moby Dick",
        "tick": 90, "margin": "Margin note: the part I'll come back to.",
        "source": "classic", "stir": 0.5}]
    a.open_questions = [{
        "text": "If I learned everything, would I still be me?",
        "keywords": ["learned"], "tick": 10, "touches": 0}]
    a.days = [{"day": 1, "ticks": [0, 100],
               "text": "I ate and read and the town was kind."}]
    a.mood_name = "luminous"
    a.mood = 0.8
    a.awareness = 0.10
    a.outbox_count = 0
    a.initiation_log = []
    a.longing = 1.0
    a.sleep_pressure = 0.1
    a.vitals = {"satiety": 0.8, "hydration": 0.8, "oxygen": 1.0,
                "vitality": 0.8, "excitement": 0.1}
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
        """save() serializes the whole organism; give the bypassed-init
        test double every field it touches."""
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
        self.assertTrue(kw["text"])  # recall() can quote her own words
        # the old untyped event name is gone; the typed one replaces it
        self.assertFalse([ev for ev, _ in self.a.journaled
                          if ev == "expression"])

    def test_piece_lands_in_outbox_named_for_kind(self):
        self.a.express()
        kw = self._initiations()[0]
        self.assertTrue(kw["file"].endswith(f"_{kw['kind']}.txt"))
        path = os.path.join(config.outbox_dir(), kw["file"])
        self.assertTrue(os.path.isfile(path))
        with open(path) as f:
            content = f.read()
        self.assertIn(kw["kind"], content.split("\n")[0])  # the header names it
        self.assertEqual(self.a.location, "postbox")  # she walked there
        # v0.27: no hard reset to 0.15 any more — the driving entry
        # (Donald's, seeded from the stored 1.0 by the migration rule)
        # eases by its satiation share, and the scalar follows it down.
        self.assertLess(self.a.longing, 1.0)
        self.assertNotEqual(self.a.longing, 0.15)
        entry = self.a.longing_ledger.get("person:Donald")
        self.assertIsNotNone(entry)
        self.assertAlmostEqual(entry["ache"], 0.85 * 0.45, places=6)
        self.assertAlmostEqual(self.a.longing, entry["ache"], places=6)

    def test_kind_is_seeded_deterministic(self):
        # v0.44 made consecutive expresses stateful on purpose: she
        # remembers what she said (said_log) and will not write
        # twice inside INITIATION_MIN_GAP. This test pins the older
        # property — the seeded kind and word sequence — so it
        # steps past the gap and clears the said-memory between
        # sends, isolating the choice from the memory. The memory's
        # own behavior is pinned in test_said_memory.py.
        def run(a):
            kinds, texts = [], []
            for i in range(12):
                a.tick_count = 100 + i * (Aethel.INITIATION_MIN_GAP + 1)
                a.said_log = []
                a._initiation_held_tick = None
                a.express()
                kw = [kw for ev, kw in a.journaled if ev == "initiation"][-1]
                kinds.append(kw["kind"])
                texts.append(kw["text"])
            return kinds, texts

        kinds_a, texts_a = run(self.a)
        # a second life, same seed, built after a's run so the global
        # journal patch is not fought over — same kinds, same words
        b = rich_aethel(tempfile.mkdtemp(prefix="aethel-initiation-b-"))
        b.say = lambda text: b.journaled.append(("said", text))
        kinds_b, texts_b = run(b)
        self.assertEqual(kinds_a, kinds_b)  # same seed, same kinds
        self.assertEqual(texts_a, texts_b)  # same seed, same words
        self.assertEqual(len(set(kinds_a)), 3)  # all three kinds reachable

    def test_question_comes_from_her_open_questions(self):
        self.a._initiation_kinds = lambda: ["question"]
        self.a.express()
        kw = self._initiations()[0]
        self.assertEqual(kw["kind"], "question")
        self.assertIn("If I learned everything, would I still be me?",
                      kw["text"])
        self.assertEqual(self.a.open_questions[0]["touches"], 1)
        self.assertEqual(len(self.a.open_questions), 1)  # drawn, not invented

    def test_note_subject_is_real(self):
        for _ in range(12):  # seeded; whichever subject she picks
            label, detail = self.a._note_subject()
            real = ("Moby Dick" in detail
                    or "Kindness is a discipline" in detail
                    or "library kept breathing" in detail
                    or "the town was kind" in detail)
            self.assertTrue(real, f"note subject not from her life: {detail!r}")

    def test_nudge_points_at_something_she_did(self):
        self.a._initiation_kinds = lambda: ["nudge"]
        self.a.express()
        kw = self._initiations()[0]
        self.assertEqual(kw["kind"], "nudge")
        body = kw["text"]
        real = ("commonplace book" in body and "1 passages" in body
                or "luminous" in body
                or "day-page" in body
                or "postbox" in body)
        self.assertTrue(real, f"nudge points at nothing real: {body!r}")

    def test_eligibility_gates_kinds(self):
        self.a.open_questions = []
        self.a.kept_passages = []
        self.a.beliefs = []
        self.a.days = []
        self.a.mood_name = None
        self.a.outbox_count = 0
        self.assertEqual(self.a._initiation_kinds(), ["note"])
        # a question needs a real open question
        self.a.open_questions = [{"text": "why?", "keywords": [],
                                  "tick": 1, "touches": 0}]
        self.assertIn("question", self.a._initiation_kinds())
        self.assertNotIn("nudge", self.a._initiation_kinds())
        # a nudge needs something she has done worth showing
        self.a.mood_name = "grey"
        self.assertIn("nudge", self.a._initiation_kinds())

    def test_initiation_log_persists_across_save_load(self):
        self._save_ready(self.a)
        self.a.express()
        # v0.44: a second piece one tick later would be held (gap +
        # said-memory) and journal no initiation. Step past the gap
        # and clear the memory so this test keeps pinning what it
        # pins: the log's round-trip, not the pacing.
        self.a.tick_count += Aethel.INITIATION_MIN_GAP + 1
        self.a.said_log = []
        self.a._initiation_held_tick = None
        self.a.express()
        self.a.save()
        # a restart: a fresh organism loading the saved life. make_aethel
        # injects a fresh :memory: store, so hold the saved one aside.
        from aethel_pkg.journal import get_store, set_store
        saved_store = get_store()
        c = make_aethel()
        set_store(saved_store)
        # make_aethel is minimal; load() reads vitals and the donald
        # model, so give the fresh organism both before the restart
        c.vitals = {}
        c.donald_model = {"letter_count": 0, "words": {}, "last_tick": 0}
        c.load()
        self.assertEqual(c.initiation_log, self.a.initiation_log)
        self.assertEqual(len(c.initiation_log), 2)
        self.assertTrue(all(set(e) == {"tick", "kind", "file"}
                            for e in c.initiation_log))


if __name__ == "__main__":
    unittest.main()
