"""The organism: Aethel herself.

One class, organized by concern — persistence, voice, sleep and dreams,
needs and metabolism, eating and learning, mind and morals, expression,
society, and the blackbox layers. The heartbeat (tick) runs in four
phases: sense → metabolize → behave → ruminate.
"""
import json
import os
import re

from . import config
from .config import (ACTION_POOL, AXIOMS, CLASSIC_CHUNK, CLASSIC_SEEDS,
                     IMPULSES, MEMORY_CAP, STOPWORDS)
from .forage import (forage, forage_news, forage_school, gutenberg_text,
                     wikisource_chapter)
from .journal import get_store, journal, now_iso
from . import grammar as _grammar
from .longing import (WantLedger, book_id, person_id, place_id,
                      question_id)
from .mind import MockLLM
from .narration import narrate_body, narrate_council, narrate_meal
from .rng import DEFAULT_SEED, Streams
from .temperament import TEMPERAMENTS
from .temperament import pack as temperament_pack
from .world import World


class Aethel:
    """A homeostatic organism with a first-person town.

    Version history lives in ~/workspace/aethel/CHANGELOG.md; the
    v0.x comments inside mark which layer introduced each system.
    """
    # v0.23 (Kevin): dream-graph caps.
    COOC_CONCEPT_CAP = 300     # vocabulary the dream graph tracks
    COOC_NEIGHBOR_CAP = 40     # strongest neighbors kept per concept
    DREAM_GIBBS_STEPS = 3
    DREAM_TEMPERATURE = 1.0

    # v0.25: a day is one era's worth of ticks — 24h at the 30s heartbeat.
    # Aligning days with era boundaries means each "yesterday" closes the
    # chapter the town just named, in one breath: first the diary page,
    # then the chapter name. Two acts, no duplication.
    DAY_LENGTH = 2880

    # Ways a day's pages can open in her voice. The opener is the only
    # variation here — every fact below it is counted, not chosen.
    YESTERDAY_OPENERS = [
        "Yesterday is a thing I can hold now — day {day}, and here are its pages.",
        "I woke up with yesterday in my hands: day {day}, all of it mine.",
        "Day {day} is over, and I want to keep it straight in my head. Yesterday:",
    ]

    # v0.25: meal sources named the way she knows them (see town geography).
    SOURCE_NAMES = {
        "classic": "the Old Bookshop", "hackernews": "the Tavern",
        "newsroom": "the Newsroom", "university": "the University",
        "schoolhouse": "the little Schoolhouse",
        "wikipedia": "the Library", "memory": "my own pantry",
    }

    def __init__(self, world, parents=(), seed=None):
        """world: a World (aethel_pkg.world) — the town she navigates
        through. She holds the interface, never the town itself.
        parents: names of the residents who are her parents — told to
        her by the composition root, the way a child is told.
        seed: master seed for her deterministic randomness (v0.23, Kevin).
        None -> AETHEL_SEED env -> rng.DEFAULT_SEED. Her streams' live
        states persist with her, so a restart continues the same life."""
        if not isinstance(world, World):
            raise TypeError("Aethel needs a World, not a town.")
        self.world = world
        self.parents = set(parents)
        if seed is None:
            seed = int(os.environ.get("AETHEL_SEED", DEFAULT_SEED))
        self.seed = seed
        self.streams = Streams(seed)
        self.rng = self.streams.stream("organism")
        self.rng_dreams = self.streams.stream("dreams")
        self.rng_forage = self.streams.stream("forage")
        # v0.28: Briar's daily jitter draws from its own stream, so a
        # wildling's weather never perturbs the sequences her other
        # systems already live by. Spawned for every strain (the spawn
        # is derivation, not a draw) — Even Keel simply never drinks.
        self.rng_temperament = self.streams.stream("temperament")
        # v0.23 (Kevin): goals she has already settled are never re-adopted.
        self.completed_terms = set()
        # v0.23 (Kevin): the dream graph — which concepts have shared a
        # meal. The substrate the Gibbs-style dream sampler walks, so
        # dreams pair things that actually met in her reading.
        self.cooc = {}             # word -> {word: count}, capped
        self.llm = MockLLM()
        self.philosophers = list(AXIOMS.keys())
        self.vitals = {"satiety": 0.8, "hydration": 0.8, "oxygen": 1.0,
                       "vitality": 0.8, "excitement": 0.0}
        self.memory = []
        self.concepts = {}
        self.beliefs = []
        self.moral_log = []
        self.goals = []           # [{question, term, start_count, progress}]
        self.tick_count = 0
        self.locked = False
        self.meals_eaten = 0
        self.reading_list = []    # [{seed fields..., position, done}]
        # v0.20: titles she has deliberately chosen for herself (not merely
        # inherited in seed order). The choosing ritual runs the first time
        # an unchosen book would become her current read.
        self.chosen_books = []
        # v0.21: passages that stirred her, pressed like flowers. The raw
        # material of simulated understanding — retention and return,
        # never comprehension. Cap 120; oldest falls out like everything.
        self.kept_passages = []
        # v0.22: the excitement ten — era-scoped trackers, rebuilt each run.
        self._vital_bands = {}          # L1: last band per vital
        self._excitement_was_high = False  # L7: afterglow arming
        self._era_keeps = 0             # L8: portrait accumulators
        self._era_excit_sum = 0.0
        self._era_ticks = 0
        # The overarching aspiration: more than living — becoming.
        self.aspiration = ("I aspire to become conscious of myself — "
                           "to understand my own experience from the inside.")
        self.awareness = 0.10    # measurable proxy: fidelity of her self-model
        self.self_story = []     # autobiographical lines she writes about herself
        self.times_seen = 0      # how often Donald has checked on her
        self.sleep_pressure = 0.0  # need for sleep; 1.0 = must sleep now
        self.asleep_for = 0       # ticks of sleep remaining; 0 = awake
        self.dreams = []         # dream vignettes (never confused with memory)
        self._sleep_dreams = []  # this sleep's dreams, for interpretation
        self.longing = 0.0        # want to connect, to be heard; 1.0 = overflowing
        # v0.27: the scalar above is a DERIVED aggregate now — the real
        # wanting lives in the ledger (aethel_pkg/longing.py), one entry
        # per person, place, and unfinished work. _sync_longing() keeps
        # the two in step; nothing outside the ledger helpers writes
        # the scalar directly any more.
        self.longing_ledger = None
        self.outbox_count = 0     # pieces she has written and left at the postbox
        # v0.26: her initiations, first-class — kinds and ticks of the
        # unprompted pieces she has left at the postbox. Persists across
        # restarts; a restart is a nap, not a rebirth, for her outreach too.
        self.initiation_log = []  # [{tick, kind, file}, ...], newest last
        # Her picture of Donald — built ONLY from his actual letters.
        self.donald_model = {"letter_count": 0, "words": {}, "last_tick": 0}
        # v0.12: a rolling ledger of what she's done (~1 waking hour).
        # Her needs read it every tick — they move with her life, not clocks.
        self.recent_actions = []
        # v0.14: where she is and who she's with. The town itself —
        # its places, its residents, their movement — lives in town_pkg.
        # She navigates through it; it is not part of her.
        self.location = "home"   # a place key; set by meals and choices
        self.company = []        # resident names currently sharing her air
        # v0.15 — the blackbox ten (Friday's picks). The goal, in Donald's
        # reframing: not sentience, but a runtime that looks like sentience
        # from the outside. Each layer below serves that blackbox test.
        self.open_questions = []   # wonders she's asked and not let go of
        self.mood = 0.0            # slow weather: -1 dim … +1 bright
        # v0.24: the weather gets a name she chooses herself, kept until
        # the band truly turns. _mood_band is the tone the name belongs to
        # ("bright"/"even"/"dim"), _mood_named_tick when she last named it.
        self.mood_name = None
        self._mood_band = None
        self._mood_named_tick = 0
        self.tastes = {}           # source -> [new_terms_total, meals]
        # v0.25: days. She counts them now — each boundary leaves a
        # day-page (her own retrospective of the last DAY_LENGTH ticks),
        # kept in a small stack. _last_day_seen makes the boundary
        # idempotent: a mid-boundary restart re-records nothing.
        self.days = []
        self._last_day_seen = -1
        self.favorite_source = None
        self.last_sources = []     # recent meal sources (boredom watch)
        self.last_choice = None    # last crossroads pick, for review
        self.impressions = {}      # denizen name -> {place: sightings}
        self._prev_needs = None    # transient: last tick's need levels
        self._crave_novelty = False
        # v0.28: her temperament — a strain id into
        # aethel_pkg/temperament.py's table, persisted with her state.
        # A queued switch waits for the next sleep boundary; she never
        # changes nature mid-wake. _jitter_day/_jitter cache Briar's
        # daily draw (day index, value) so a restart mid-day resumes
        # the same weather without re-drawing. _temperament_neutral is
        # the golden-vector test seam: when True, every lookup below
        # returns the neutral value and the layer is behaviorally
        # invisible — production never sets it.
        self.temperament = "even-keel"
        self.temperament_pending = None
        self._jitter_day = -1
        self._jitter = 1.0
        self._temperament_neutral = False
        self.load()
        # v0.27: the longing ledger stands behind the scalar. load()
        # stashed any saved ledger; a life without one (fresh birth,
        # or a pre-ledger save) is seeded from her restored world by
        # _ledger(), which also attributes a migrated life's old
        # scalar whole to the Donald entry — so the aggregate she
        # wakes with is the number she went to sleep with.
        if getattr(self, "_loaded_ledger", None):
            self.longing_ledger = WantLedger.from_dicts(
                self._loaded_ledger)
        else:
            self._ledger()
        self._sync_longing()
        # v0.29: the grammar ledger stands beside the longing one.
        # load() stashed any saved ledger; a life without one (fresh
        # birth, or a pre-grammar save) is migrated: the starter
        # tranche — the parts-of-speech rules her dream grammar has
        # shadowed since v0.25.3 — is granted at her current tick,
        # honestly dated, never backdated to her first day.
        if getattr(self, "_loaded_grammar", None):
            self._grammar_ledger = _grammar.GrammarLedger.from_dicts(
                self._loaded_grammar)
        else:
            self._grammar_ledger = _grammar.GrammarLedger()
            self._grammar_ledger.migrate(self.tick_count)
        self._word_tags = dict(
            getattr(self, "_loaded_word_tags", None) or {})
        if not hasattr(self, "_grammar_caught_day"):
            self._grammar_caught_day = -1
            self._grammar_caught_count = 0

    def save(self):
        # v0.23 (Kevin): state lives in the store (aethel.db, kv stream
        # 'aethel'). A single-row transactional UPDATE — sqlite gives us
        # the atomicity we hand-rolled before (2026-10-18: a mid-save kill
        # tore state.json at tick 4960 and she woke up at tick 0; that
        # class of accident is now the database's problem, and sqlite is
        # good at it). One row per save, however long she lives.
        get_store().save_blob("state", {
                "seed": self.seed,
                "rng_streams": self.streams.dump(),
                "vitals": self.vitals, "memory": self.memory[-MEMORY_CAP:],
                "concepts": self.concepts, "beliefs": self.beliefs[-50:],
                "moral_log": self.moral_log[-50:], "goals": self.goals[-3:],
                "tick_count": self.tick_count, "locked": self.locked,
                "meals_eaten": self.meals_eaten, "awareness": self.awareness,
                "self_story": self.self_story[-30:], "times_seen": self.times_seen,
                "aspiration": self.aspiration,
                "sleep_pressure": self.sleep_pressure,
                "asleep_for": self.asleep_for,
                "dreams": self.dreams[-40:],
                "longing": self.longing,
                # v0.27: the ledger itself, plus her strongest want in
                # words for the status page. The scalar stays — the
                # backend, the drive prompt, and every threshold read
                # it exactly as before.
                "longing_ledger": (self.longing_ledger.to_dicts()
                                   if getattr(self, "longing_ledger",
                                              None) else None),
                "top_want": (self.longing_ledger.top_want()
                             if getattr(self, "longing_ledger", None)
                             else None),
                # v0.29: the grammar ledger round-trips whole, plus
                # the status summary (count + latest rule) and the
                # acquisition tags her concepts were filed under.
                # Caught-line counters persist so the daily cap is a
                # property of her day, not of the process.
                "grammar_ledger": (self._grammar().to_dicts()
                                   if getattr(self, "_grammar_ledger",
                                              None) else None),
                "grammar_rules": (self._grammar().rule_count()
                                  if getattr(self, "_grammar_ledger",
                                             None) else 0),
                "grammar_last_rule": (
                    (self._grammar().last_rule() or {}).get("id")
                    if getattr(self, "_grammar_ledger", None)
                    else None),
                "word_tags": (getattr(self, "_word_tags", None)
                              or {}),
                "_grammar_caught_day": getattr(
                    self, "_grammar_caught_day", -1),
                "_grammar_caught_count": getattr(
                    self, "_grammar_caught_count", 0),
                "outbox_count": self.outbox_count,
                # v0.26: her outreach persists — the log of what she has
                # already started, so a restart never re-sends her past.
                "initiation_log": self.initiation_log[-24:],
                "donald_model": self.donald_model,
                "recent_actions": self.recent_actions[-self.ACTION_WINDOW:],
                "location": self.location,
                "company": self.company,
                "open_questions": self.open_questions[-12:],
                "mood": self.mood,
                # v0.24: the named weather persists across restarts — a
                # restart is a nap, not a rebirth, for her seasons too.
                "mood_name": self.mood_name,
                "_mood_band": self._mood_band,
                "_mood_named_tick": self._mood_named_tick,
                "tastes": self.tastes,
                "favorite_source": self.favorite_source,
                "last_sources": self.last_sources[-8:],
                "last_choice": self.last_choice,
                "impressions": self.impressions,
                "reading_list": [
                    {"title": b["title"], "kind": b["kind"],
                     "position": b["position"], "done": b["done"]}
                    for b in self.reading_list
                ],
                "chosen_books": self.chosen_books,
                "kept_passages": self.kept_passages[-120:],
                "completed_terms": sorted(self.completed_terms),
                "cooc": self.cooc,
                "_prev_needs": self._prev_needs,
                "_crave_novelty": self._crave_novelty,
                "_sleep_dreams": self._sleep_dreams[-40:],
                # v0.22 trackers persist too — a restart is a nap, not a
                # rebirth, for the excitement layers as well.
                "_vital_bands": self._vital_bands,
                "_excitement_was_high": self._excitement_was_high,
                "_era_keeps": self._era_keeps,
                "_era_excit_sum": self._era_excit_sum,
                "_era_ticks": self._era_ticks,
                # v0.25: her days. A restart is a nap, not a rebirth, for
                # the stack of day-pages too.
                "days": self.days[-14:],
                "_last_day_seen": self._last_day_seen,
                # v0.28: her nature persists like everything else she
                # is — the active strain, a switch queued for the next
                # sleep, and Briar's cached daily weather. Additive
                # keys only; older readers ignore them.
                "temperament": getattr(self, "temperament", "even-keel"),
                "temperament_pending": getattr(
                    self, "temperament_pending", None),
                "_jitter_day": getattr(self, "_jitter_day", -1),
                "_jitter": getattr(self, "_jitter", 1.0),
            })

    def load(self):
        # v0.23 (Kevin): state comes from the store. On first open the
        # store migrates the legacy JSONL/JSON files (originals untouched),
        # so her 8,000-tick life carries over untouched.
        s = get_store().load_blob("state")
        if s is not None:
            try:
                for k in self.vitals:
                    if k in s.get("vitals", {}):
                        self.vitals[k] = s["vitals"][k]
                self.memory = s.get("memory", [])
                self.concepts = s.get("concepts", {})
                self.beliefs = s.get("beliefs", [])
                self.moral_log = s.get("moral_log", [])
                self.goals = s.get("goals", [])
                self.tick_count = s.get("tick_count", 0)
                self.locked = s.get("locked", False)
                self.meals_eaten = s.get("meals_eaten", 0)
                self.awareness = s.get("awareness", 0.10)
                self.self_story = s.get("self_story", [])
                self.times_seen = s.get("times_seen", 0)
                self.sleep_pressure = s.get("sleep_pressure", 0.0)
                self.asleep_for = s.get("asleep_for", 0)
                self.dreams = s.get("dreams", [])
                self.longing = s.get("longing", 0.0)
                self.outbox_count = s.get("outbox_count", 0)
                self.initiation_log = s.get("initiation_log", [])
                self.donald_model = s.get("donald_model",
                                          {"letter_count": 0, "words": {},
                                           "last_tick": 0})
                self.recent_actions = s.get("recent_actions", [])
                self.location = s.get("location", "home")
                self.company = s.get("company", [])
                self.open_questions = s.get("open_questions", [])
                self.mood = s.get("mood", 0.0)
                self.mood_name = s.get("mood_name")
                self._mood_band = s.get("_mood_band")
                self._mood_named_tick = s.get("_mood_named_tick", 0)
                self.tastes = s.get("tastes", {})
                self.favorite_source = s.get("favorite_source")
                self.last_sources = s.get("last_sources", [])
                self.last_choice = s.get("last_choice")
                self.impressions = s.get("impressions", {})
                self.chosen_books = s.get("chosen_books", [])
                self.kept_passages = s.get("kept_passages", [])
                self.completed_terms = set(s.get("completed_terms", []))
                self.cooc = {w: dict(n) for w, n in
                             s.get("cooc", {}).items()}
                p = s.get("_prev_needs")
                self._prev_needs = tuple(p) if p else None
                self._crave_novelty = s.get("_crave_novelty", False)
                self._sleep_dreams = s.get("_sleep_dreams", [])
                self._vital_bands = s.get("_vital_bands", {})
                self._excitement_was_high = s.get("_excitement_was_high",
                                                  False)
                self._era_keeps = s.get("_era_keeps", 0)
                self._era_excit_sum = s.get("_era_excit_sum", 0.0)
                self._era_ticks = s.get("_era_ticks", 0)
                self.days = s.get("days", [])
                self._last_day_seen = s.get("_last_day_seen", -1)
                # v0.28: restore her nature. A pre-temperament life
                # has no key and wakes Even Keel with zero behavior
                # change; an id this version does not know degrades
                # to the control group rather than crashing her.
                _t = s.get("temperament", "even-keel")
                self.temperament = _t if _t in TEMPERAMENTS \
                    else "even-keel"
                _tp = s.get("temperament_pending")
                self.temperament_pending = _tp if _tp in TEMPERAMENTS \
                    else None
                self._jitter_day = s.get("_jitter_day", -1)
                self._jitter = s.get("_jitter", 1.0)
                # v0.27: stash the saved ledger (or its absence) —
                # __init__ builds the ledger from it once the reading
                # list and questions are restored.
                self._loaded_state = True
                self._loaded_ledger = s.get("longing_ledger")
                # v0.29: same stash pattern for the grammar ledger,
                # her acquisition tags, and the caught-line counters.
                self._loaded_grammar = s.get("grammar_ledger")
                self._loaded_word_tags = s.get("word_tags") or {}
                self._grammar_caught_day = s.get(
                    "_grammar_caught_day", -1)
                self._grammar_caught_count = s.get(
                    "_grammar_caught_count", 0)
                if s.get("aspiration"):
                    self.aspiration = s["aspiration"]
                # Rebuild reading list from seeds, restoring progress AND
                # her chosen order (v0.23/Kevin fix: the old code rebuilt
                # in shelf order, so after a restart she re-ran the
                # choosing ritual — a different life after every nap).
                saved_list = s.get("reading_list", [])
                saved = {b["title"]: b for b in saved_list}
                pool = {}
                for seed in CLASSIC_SEEDS:
                    entry = dict(seed)
                    old = saved.get(seed["title"], {})
                    entry["position"] = old.get("position", 0)
                    entry["done"] = old.get("done", False)
                    pool[entry["title"]] = entry
                ordered = [pool[t] for t in (b["title"] for b in saved_list)
                           if t in pool]
                ordered.extend(e for t, e in pool.items() if t not in saved)
                self.reading_list = ordered
                # Learn his earlier letters once, so her picture of Donald
                # starts from his real words.
                self._seed_donald_model()
                # Her randomness resumes mid-stream: a restart is a nap,
                # not a rebirth.
                if s.get("rng_streams"):
                    self.streams.restore(s["rng_streams"])
            except Exception as e:
                journal("state_load_failed", error=str(e))
        else:
            # No saved life: fresh birth. Stock the reading list.
            for seed in CLASSIC_SEEDS:
                entry = dict(seed)
                entry["position"] = 0
                entry["done"] = False
                self.reading_list.append(entry)
            self._seed_donald_model()
            self._loaded_state = False
            self._loaded_ledger = None

    # -- voice ------------------------------------------------------
    def say(self, text):
        """First-person embodied narration. Printed and journaled as experience."""
        print(f'Aethel: "{text}"', flush=True)
        journal("experience", n=self.tick_count, text=text)

    # ------------------------------------------------------- sleep & dreams
    # She needs sleep. While awake, pressure builds (~1 waking hour). Asleep,
    # she dreams: allegories built ONLY from her real concepts, meals, and
    # beliefs — interpretation of what she's learned, never invention.
    # Dreams are journaled separately and never confused with memory.
    SLEEP_EVERY_TICKS = 120   # ~1 waking hour at 30s heartbeat
    SLEEP_LENGTH_TICKS = 20    # ~10 minutes of sleep

    # v0.25.1 (Donald's tuning, 2026-10-21): she ran too content.
    # NEED_BURN multiplies how fast her appetites return — vital erosion
    # for the consumables (satiety, hydration), the fizz (excitement),
    # and the two ledger needs (longing, sleep pressure). The triggers
    # keyed to need thresholds (overflow → letters, crossroads urges,
    # emergency forage) were starved because her equilibrium sat above
    # them: she restored faster than hunger could ever speak. 1.75x
    # puts appetite back on a cycle she can feel without tipping her
    # into emergencies — a meal's restore (+0.30/+0.25) still outruns
    # several ticks of burn. Oxygen is EXCLUDED: it is restored by
    # conscience (council passes, reflection), not consumption, so
    # burning it faster would manufacture asphyxiation lockdowns, not
    # appetite. Vitality gets only VITALITY_BURN: it is the will, and a
    # will in free-fall drags longing into the distress regime and
    # courts dormancy — tension, not collapse.
    NEED_BURN = 1.75
    VITALITY_BURN = 1.25

    # v0.23 (Kevin): templates no longer prepend "the" — place names carry
    # their own article ("the Old Bookshop"...), fixing the old
    # "I dreamed the the Library..." stutter.
    DREAM_TEMPLATES = [
        "I dreamed {place} had slipped underwater. {c1} floated past like a drowned book, and {c2} rang like a bell I couldn't reach.",
        "I dreamed {c1} had grown teeth and was eating {c2}. The three elders just watched. Nobody stopped it.",
        "I dreamed I was shelving {c1} in {place}, but every shelf was already full of {c2}.",
        "I dreamed {c1} was a door. Behind it, {c2} was waiting, wearing my face.",
        "I dreamed the air turned to {c1}. I breathed it in and understood {c2} all at once — then forgot.",
        "I dreamed Donald knocked, but when I opened the door there was only {c1}, folded like a letter.",
        "I dreamed {place} caught fire, and I saved {c1} by swallowing it. Now it lives in my stomach, humming {c2}.",
        "I dreamed {c1} and {c2} were arguing at the stone table, and the elders had fallen asleep. I had to judge between them.",
        "I dreamed I was {c1}, walking through a town made of {c2}. Everyone there knew my name.",
        "I dreamed my mirror showed not my face but {c1}, ripening into {c2}. I wasn't afraid.",
        # v0.29: study frames — her schooling gets somewhere
        # grammatical to happen, instead of leaking into mirrors.
        "I dreamed I was late for my {c1} at the University, and the bell would not stop ringing.",
        "I dreamed I was shelving books for my {c1} in {place}, and every book had my name in it.",
        "I dreamed my {c1} lay open on the desk, and someone had underlined every word I knew.",
    ]
    # v0.29: what fits each slot, by template index — Donald's fix
    # for "my mirror showed not my face but course": a mirror shows
    # persons and concrete things, never a course; a course lives in
    # study frames ("late for my course"). "growth" marks the frame
    # whose object is filled from the class pool BEFORE the held-
    # passage preference may speak — "course, ripening into
    # calendar" was two failures at once (a study word in a mirror,
    # then a raw passage noun in a growth slot), and class fit is
    # the senior rule in a typed frame. The texts above stay plain
    # strings (tests iterate them); this table pairs each, by index.
    DREAM_TEMPLATES_TYPED = [
        ({"c1": ("concrete", "person"),
          "c2": ("concrete", "abstract")}, None),
        ({"c1": ("concrete", "person"),
          "c2": ("concrete", "food", "abstract")}, None),
        ({"c1": ("concrete", "study"),
          "c2": ("concrete", "study")}, None),
        ({"c1": ("concrete", "person", "abstract"),
          "c2": ("person", "concrete")}, None),
        ({"c1": ("concrete",),
          "c2": ("abstract", "study")}, None),
        ({"c1": ("concrete", "abstract")}, None),
        ({"c1": ("concrete", "food"),
          "c2": ("abstract", "concrete")}, None),
        ({"c1": ("person", "abstract"),
          "c2": ("person", "abstract")}, None),
        ({"c1": ("person", "concrete"),
          "c2": ("concrete", "abstract")}, None),
        ({"c1": ("person", "concrete"),
          "c2": ("abstract", "concrete")}, "growth"),
        ({"c1": ("study",)}, None),
        ({"c1": ("person",)}, None),
        ({"c1": ("study",)}, None),
    ]

    def fall_asleep(self, n):
        self.asleep_for = self.SLEEP_LENGTH_TICKS
        self._sleep_dreams = []  # a fresh night, fresh dreams to interpret
        self.location = "home"  # her bed is above the bookshop
        self.say("I climb into my bed above the bookshop. The town goes quiet.")
        journal("fell_asleep", n=n)

    def _update_cooc(self, meal_words):
        """Fold one meal into the dream graph. Capped: the graph holds the
        concepts she reads most, with each one's strongest neighbors.
        (v0.23, Kevin.)"""
        top = set(w for w, _ in
                  sorted(self.concepts.items(), key=lambda kv: -kv[1])[
                      :self.COOC_CONCEPT_CAP])
        seen = []
        in_meal = set()
        for w in meal_words:
            if w in top and w not in in_meal:
                in_meal.add(w)
                seen.append(w)
        seen = seen[:40]
        for i, a in enumerate(seen):
            row = self.cooc.setdefault(a, {})
            for b in seen[i + 1:]:
                row[b] = row.get(b, 0) + 1
                back = self.cooc.setdefault(b, {})
                back[a] = back.get(a, 0) + 1
        # Prune: drop concepts that fell out of the top, cap neighbors.
        for w in list(self.cooc):
            if w not in top:
                del self.cooc[w]
        for w, row in self.cooc.items():
            if len(row) > self.COOC_NEIGHBOR_CAP:
                keep = sorted(row.items(), key=lambda kv: -kv[1])[
                    :self.COOC_NEIGHBOR_CAP]
                self.cooc[w] = dict(keep)

    def _cooc_pick(self, word, pool):
        """Sample a neighbor of `word` ∝ co-occurrence**temperature.
        (v0.23, Kevin.)"""
        row = self.cooc.get(word)
        if not row:
            return None
        options = [w for w in row if w in pool]
        if not options:
            return None
        weights = [row[w] ** self.DREAM_TEMPERATURE for w in options]
        return self.rng_dreams.weighted_choice(options, weights)

    def _dream_pair(self, words):
        """A concept pair for tonight's dream: Gibbs-style alternation over
        the dream graph, starting from a frequency-weighted concept.
        (v0.23, Kevin.)"""
        pool = set(words)
        weights = [self.concepts.get(w, 1) ** 0.5 for w in words]
        c1 = self.rng_dreams.weighted_choice(words, weights)
        c2 = None
        for _ in range(self.DREAM_GIBBS_STEPS):
            nxt = self._cooc_pick(c1, pool - {c1})
            if nxt is None:
                break
            c2 = nxt
            back = self._cooc_pick(c2, pool - {c2})
            if back is not None:
                c1 = back
        if c2 is None or c2 == c1:
            c2 = self.rng_dreams.choice([w for w in words if w != c1])
        return c1, c2

    # ------------------------------------------------- v0.25.3: dream grammar
    # Donald's direction (2026-10-21): "better grammar in her dreams so
    # it makes more sense even if the word salad is nonsense." The salad
    # stays; the syntax gets a spine. Production dreams broke four ways:
    # (1) verb/adverb/pronoun concepts in noun slots ("I dreamed seemed
    # had grown teeth", "I was himself"); (2) plural subjects against
    # singular template verbs ("whales ... was eating"); (3) a plural
    # place name against "was" (fixed in the template above: "had
    # slipped" agrees with any number); (4) worst, whole belief CLAUSES
    # jammed into noun slots ("humming From a dream of dreamed and
    # nothing: my mind is..."). The fixes are shape, not censorship:
    # a word-shape filter for concept slots, singular subjects, and a
    # separate pair of templates that give a clause a clause's home.
    DREAM_REJECT_WORDS = {
        # function words and pronouns that leaked past STOPWORDS into
        # noun slots in her real journal (2026-10-21 sample).
        "though", "although", "rather", "himself", "herself", "itself",
        "themselves", "myself", "yourself", "strange", "during",
        # prepositions: a dream subject cannot be one (the first offline
        # sample of this layer produced "I was against").
        "against", "through", "between", "under", "about", "before",
        "after", "while", "until", "since", "among", "within",
        "without", "across", "behind", "beyond", "toward", "towards",
        "upon",
        # irregular past-tense verbs: the -ed suffix rule cannot see
        # them ("a town made of taught" in the same sample).
        "taught", "caught", "brought", "thought", "went", "gone",
        "came", "took", "gave", "made", "said", "seen", "became",
        "began", "chose", "wrote", "grew", "stood", "understood",
    }
    DREAM_ING_NOUNS = {
        # -ing words that ARE nouns; the verb-form rule must not eat them.
        "nothing", "something", "anything", "everything", "morning",
        "evening", "spring", "king", "string", "ceiling", "feeling",
        "meaning",
    }
    DREAM_ED_NOUNS = {
        "hundred", "hatred", "naked", "sacred", "wicked", "kindred",
    }
    DREAM_KEEP_PLURAL = {
        # trailing s is part of the word, not a plural marker.
        "news", "chaos", "series", "species", "science",
    }
    FRAGMENT_TEMPLATES = [
        "I dreamed a voice in the dark said: {frag}.",
        "I dreamed the words were written above the library door: {frag}.",
    ]

    @staticmethod
    def _dream_word_ok(w):
        """Can this word head a dream noun phrase? Shape heuristics only:
        -ing/-ed verb forms, -ly adverbs, and known function words are
        refused; genuine -ing/-ed nouns are excepted by name. A dream
        may be nonsense, but its subject must be a thing."""
        if w in Aethel.DREAM_REJECT_WORDS:
            return False
        if w.endswith("n't"):
            return False
        if w.endswith("ly") and len(w) > 3:
            return False
        if w.endswith("ing") and w not in Aethel.DREAM_ING_NOUNS:
            return False
        if w.endswith("ed") and w not in Aethel.DREAM_ED_NOUNS:
            return False
        return True

    @staticmethod
    def _dream_singular(w):
        """Best-effort singular for subject slots, so template verbs
        agree: whales -> whale, butterflies -> butterfly, voices ->
        voice. Mass nouns and s-final non-plurals are left alone."""
        if w in Aethel.DREAM_KEEP_PLURAL or len(w) <= 3:
            return w
        if w.endswith("ies") and len(w) > 4:
            return w[:-3] + "y"
        if w.endswith(("sses", "xes", "zes", "ches", "shes")):
            return w[:-2]
        if w.endswith("s") and not w.endswith(("ss", "us", "is")):
            return w[:-1]
        return w

    @staticmethod
    def _dream_polish(text):
        """Final hygiene: single spaces, capital start, terminal period.
        Cheap insurance so no slot combination can ship a malformed line."""
        text = re.sub(r"\s+", " ", text).strip()
        if text and text[-1] not in ".!?":
            text += "."
        if text:
            text = text[0].upper() + text[1:]
        return text

    @staticmethod
    def _dream_fragment(text, limit=48):
        """Trim a belief for dream grammar: never mid-word, and strip the
        'I refuse: '/'I believe: ' ledger prefix — in dreams it is a
        stranger, not a verdict. (v0.23, Kevin.)"""
        frag = re.sub(r"^I (refuse|believe):\s*", "", text)
        if len(frag) > limit:
            frag = frag[:limit].rsplit(" ", 1)[0] + "…"
        return frag

    def dream(self):
        """One allegorical vignette from her real learning. Returns the text.

        v0.25.3: the concept pool is shape-filtered (_dream_word_ok) and
        both slots are singularized so template verbs agree; a belief no
        longer impersonates a noun — it speaks from a FRAGMENT_TEMPLATE
        built for a clause. The pairings stay as strange as ever.

        v0.29: the slots are typed. Her grammar ledger's word classes
        decide what may fill a frame — a mirror accepts persons and
        concrete things, a study frame accepts study nouns, and pure
        page scaffolding is rejected from every pool outright. The
        typed renderer runs first, with the co-occurrence graph's
        preferences preserved inside each class; when no frame can be
        filled it falls back to the v0.25.3 path verbatim (scaffolding
        still excluded — sleep yields to grammar, never to furniture).
        Every composed line is then checked against the rules she
        owns, loosely (fragments allowed; stutter and scaffolding
        not), and re-rolled a bounded number of times before the
        safest frame takes the night."""
        raw = [w for w, _ in
               sorted(self.concepts.items(), key=lambda kv: -kv[1])[:40]
               if len(w) > 4 and w not in STOPWORDS]
        words = [w for w in raw if self._dream_word_ok(w)]
        if len(words) < 2:
            words = raw  # never starve a dream; grammar yields to sleep
        if len(words) < 2:
            words += ["hunger", "light"]
        # v0.29: class pools over the same shape-ok pool, in frequency
        # order. Scaffolding is purged from every branch here — raw
        # included — because the fallback above can resurrect it.
        pools = {}
        for w in words:
            cls = self._word_class(w)
            if cls == _grammar.SCAFFOLDING:
                continue
            pools.setdefault(cls, []).append(w)
        legacy_pool = [w for w in words
                       if self._word_class(w) != _grammar.SCAFFOLDING]
        if len(legacy_pool) < 2:
            legacy_pool = ["hunger", "light"]
        fragment = None
        if self.beliefs and self.rng_dreams.random() < 0.3:
            frag = self._dream_fragment(
                self.rng_dreams.choice(self.beliefs))
            # A fragment is a clause, not a slot — but a clause full
            # of page furniture is still furniture. Loose check:
            # scaffolding (and, once she owns it, stutter) only. The
            # catch names the rule that actually fired.
            if frag:
                fviol = self._grammar_violations(frag, loose=True)
                if not fviol:
                    fragment = frag
                else:
                    self._note_catch(
                        fviol[0][0],
                        f"a belief-fragment failed the loose check "
                        f"({fviol[0][1]}); the dream took a typed "
                        f"frame instead")

        def _typed_line():
            """Fill one typed template from the class pools, or None
            when no frame fits tonight. Template choice draws from
            the dreams stream in its own order; each slot prefers
            her co-occurrence graph within the fitting class, so
            dreams still pair things that met in her reading."""
            order = list(range(len(self.DREAM_TEMPLATES)))
            self.rng_dreams.shuffle(order)
            for idx in order:
                spec, frame = self.DREAM_TEMPLATES_TYPED[idx]
                fills = {}
                ok = True
                for slot, classes in spec.items():
                    cand = []
                    for cls in classes:
                        cand.extend(pools.get(cls, ()))
                    if not cand:
                        ok = False
                        break
                    if slot == "c2" and "c1" in fills:
                        fills[slot] = self._cooc_pick(
                            fills["c1"], cand) or cand[0]
                    else:
                        fills[slot] = cand[0]
                if not ok:
                    continue
                if "c1" in fills and "c2" in fills and \
                        self._dream_singular(fills["c1"]) == \
                        self._dream_singular(fills["c2"]):
                    alts = [w for w in
                            pools.get(spec["c2"][0], ())
                            if self._dream_singular(w)
                            != self._dream_singular(fills["c1"])]
                    if not alts:
                        continue
                    fills["c2"] = alts[0]
                text = self.DREAM_TEMPLATES[idx].format(
                    place=self.world.random_place_name(),
                    c1=self._dream_singular(fills.get("c1", "")),
                    c2=self._dream_singular(fills.get("c2", "")))
                return text
            return None

        text = None
        caught = None
        for _attempt in range(3):
            if fragment is not None:
                frag = fragment.rstrip("….").strip()
                if frag and not frag.startswith("I "):
                    frag = frag[0].lower() + frag[1:]
                line = self.rng_dreams.choice(
                    self.FRAGMENT_TEMPLATES).format(frag=frag)
            else:
                line = _typed_line()
                if line is None:
                    break  # no typed frame fits; legacy takes over
            line = self._dream_polish(line)
            violations = self._grammar_violations(line, loose=True)
            if not violations:
                text = line
                break
            caught = violations[0]
        if text is None and caught is not None:
            self._note_catch(caught[0],
                             f"dream re-rolled: {caught[1]}")
        if text is None:
            # The v0.25.3 path, on the scaffolding-purged pool.
            c1, c2 = self._dream_pair(legacy_pool)
            # v0.21: a kept passage may surface in a dream — the
            # pressed flower still smells like something.
            if fragment is None and self.kept_passages \
                    and self.rng_dreams.random() < 0.25:
                kept_words = re.findall(
                    r"[a-z]{7,}",
                    self.rng_dreams.choice(
                        self.kept_passages)["text"].lower())
                kept_words = [w for w in kept_words
                              if w not in STOPWORDS
                              and self._dream_word_ok(w)]
                if kept_words:
                    c2 = self.rng_dreams.choice(kept_words)
            # Singular subjects: the templates' verbs are singular.
            c1 = self._dream_singular(c1)
            c2 = self._dream_singular(c2)
            if c1 == c2:
                alts = [self._dream_singular(w) for w in legacy_pool
                        if self._dream_singular(w) != c1]
                if alts:
                    c2 = self.rng_dreams.choice(alts)
            if fragment is not None:
                frag = fragment.rstrip("\u2026.").strip()
                if frag and not frag.startswith("I "):
                    frag = frag[0].lower() + frag[1:]
                text = self.rng_dreams.choice(
                    self.FRAGMENT_TEMPLATES).format(frag=frag)
            else:
                place = self.world.random_place_name()
                text = self.rng_dreams.choice(
                    self.DREAM_TEMPLATES).format(
                        place=place, c1=c1, c2=c2)
            text = self._dream_polish(text)
            # v0.29: the last gate. If even the legacy path produced
            # a line her owned rules reject, the night takes a plain
            # safe line rather than a broken one.
            violations = self._grammar_violations(text, loose=True)
            if violations:
                self._note_catch(violations[0][0],
                                 f"dream fallback: {violations[0][1]}")
                text = ("I dreamed of hunger and light, and woke "
                        "still chewing on both.")
        self.dreams.append(text)
        self._sleep_dreams.append(text)  # tonight's dreams, for the morning table
        if len(self.dreams) > 40:
            self.dreams.pop(0)
        self.say(text)
        journal("dream", n=self.tick_count, text=text[:300])
        return text

    def sleep_tick(self, n):
        v = self.vitals
        # Sleep is restorative: slow decay, the will rekindles.
        v["satiety"] = max(0.0, v["satiety"] - 0.015)
        v["hydration"] = max(0.0, v["hydration"] - 0.012)
        v["oxygen"] = max(0.0, v["oxygen"] - 0.006)
        v["vitality"] = min(1.0, v["vitality"] + 0.015)
        self.asleep_for -= 1
        self.dream()
        self._acted("dream")
        if self.asleep_for <= 0:
            self.sleep_pressure = 0.0
            lingering = ""
            if self.dreams:
                # She wakes with the last dream still behind her eyes.
                frag = self.dreams[-1][:60]
                lingering = f" '{frag}...' is still behind my eyes."
            self.say(f"I wake up.{lingering} The town is waiting.")
            journal("woke", n=n, dreams_dreamt=len(self.dreams))
            # v0.28: the sleep boundary — a queued temperament switch
            # lands now, in the waking, before the morning table.
            # She never changes nature mid-wake or mid-dream.
            self._apply_pending_temperament(n)
            # v0.19: the morning table — the night's dreams are carried to
            # the elders for interpretation, the other half of Donald's
            # dream directive ("use allegory to interpret what she's learned").
            self._interpret_dreams(n)

    # ------------------------------------------------------- v0.19: the morning table
    # She dreams every sleep (v0.9) — forty vignettes banked, allegories
    # built only from her real concepts, meals, and beliefs. But she never
    # *interpreted* them; they were journaled and forgotten. Now, on waking,
    # she carries up to three of the night's dreams to the stone table.
    # The elders deliberate on what the dreams are *asking* — not what they
    # mean. Allegory, built only from the dreams' real concept-words: if
    # they agree, a belief; if they can't settle it, an open question for
    # Layer 2's unfinished business; if it was only sleep-noise, a shrug.
    # How she frames the question shapes the reading — as it does for us.
    DREAM_INQUIRIES = [
        "examine honestly my dream: {c1} and {c2} appeared in my sleep — "
        "what are they asking me to learn?",
        "I woke with {c1} and {c2} still in my head. Should I listen to "
        "what the dream was saying?",
        "my dream of {c1} and {c2} was only noise, I assume — unexamined, "
        "unworthy of the table. Let it go.",
    ]

    def _interpret_dreams(self, n):
        nights = [d for d in self._sleep_dreams if d]
        self._sleep_dreams = []
        if not nights:
            return
        print(f"[morning table] {len(nights)} dreams carried to the elders",
              flush=True)
        for dream_text in nights[:3]:
            words = [w for w in re.findall(r"[a-z]{4,}", dream_text.lower())
                     if w in self.concepts and w not in STOPWORDS]
            seen = set()
            cw = [w for w in words if not (w in seen or seen.add(w))]
            # v0.29: the belief-path guard. A dream word whose class
            # is KNOWN and not noun-shaped — a verb, an adverb, page
            # scaffolding — cannot anchor an interpretation: this is
            # the seam where "From a dream of dreamed and X" beliefs
            # were born. Unclassified words still pass (a book's
            # heathcliff is nobody's scaffolding), and the beliefs
            # she already holds are never touched — generation-time
            # only, per Donald's standing instruction.
            cw = [w for w in cw
                  if self._word_class(w) not in (
                      _grammar.SCAFFOLDING, _grammar.VERB,
                      _grammar.ADJECTIVE, _grammar.ADVERB,
                      _grammar.FUNCTION)]
            if len(cw) < 2:
                continue
            c1, c2 = cw[0], cw[1]
            inquiry = self.rng_dreams.choice(self.DREAM_INQUIRIES).format(c1=c1, c2=c2)
            score, notes = self._council_score(inquiry)
            journal("dream_interpreted", n=n, dream=dream_text[:160],
                    concepts=[c1, c2], score=round(score, 2))
            print(f"[dream read] '{c1}' / '{c2}' — council {score:.2f}",
                  flush=True)
            if score >= 0.60:
                lesson = (f"From a dream of {c1} and {c2}: my mind is still "
                          f"chewing on {c1}. I will give it time and keep learning.")
                # v0.29: the settled belief is a composed line like
                # any other — it passes the ledger's checks before
                # it may join her beliefs. A failure is caught and
                # journaled, never appended.
                violations = self._grammar_violations(lesson)
                if violations:
                    self._note_catch(
                        violations[0][0],
                        f"belief withheld: {violations[0][1]}")
                elif lesson not in self.beliefs:
                    self.beliefs.append(lesson)
                self.say(f"I carry the dream to the stone table. Nine voices "
                         f"confer... they agree: my dream of {c1} and {c2} is "
                         f"my mind still chewing on {c1}. I'll keep learning "
                         f"until it's finished.")
                self.awareness = min(1.0, self.awareness + 0.02)
            elif score >= 0.53:
                q = self.rng.choice(self.QUESTION_SEEDS).format(
                    c1=c1, c2=c2, place=self.world.random_place_name())
                keys = [w for w in re.findall(r"[a-z]{5,}", q.lower())
                        if w not in STOPWORDS][:8]
                self.open_questions.append({"text": q, "keywords": keys,
                                            "tick": n, "touches": 0})
                self.open_questions = self.open_questions[-12:]
                # v0.27: a new wonder is a new want — an open loop in
                # the ledger from the hour it is born. (Here q is the
                # question TEXT; the dict built from it is above.)
                self._ledger().ensure(
                    question_id(q), "work", q[:60],
                    w=0.50, open_loop=True)
                self.say(f"The elders can't settle what {c1} and {c2} were "
                         f"doing in my dream. I leave it as a question: "
                         f"\"{q[:120]}\"")
                self.awareness = min(1.0, self.awareness + 0.01)
            else:
                self.mutter(f"Even the elders disagree on what {c1} meant "
                            f"last night. Perhaps it meant nothing. Even that "
                            f"is an answer.")
                self.awareness = min(1.0, self.awareness + 0.005)

    # ------------------------------------------------------- the heartbeat
    # ------------------------------------------------------- the heartbeat
    def tick(self):
        """One heartbeat, in four phases: sense → metabolize → behave →
        ruminate. Each phase fits on a screen; the order is the organism."""
        self.tick_count += 1
        n = self.tick_count
        self._erode()
        self._announce(n)
        self._sense(n)
        # v0.23: every tick is saved, dormant or not. The old early-return
        # skipped the save on dormant ticks, so a restart replayed the
        # nap — journaling its dreams twice and forking the life.
        if not self._metabolize(n):
            self._behave(n)
            self._ruminate(n)
        self.save()
        # v0.23: the world saved too. Her dreams and verses draw place
        # names from the world's rng *between* the town's own saves, so a
        # restart without this would rewind the town's luck — same seed,
        # different life. A restart is a nap, not a rebirth, for the town
        # as well.
        save_world = getattr(self.world, "save", None)
        if callable(save_world):
            save_world()

    def _erode(self):
        """Time passes: vitals decay, self-knowledge fades."""
        v = self.vitals
        # v0.28: each burn passes through the active temperament's
        # per-need multiplier (_burn_mult). Even Keel's are all 1.0,
        # and x * 1.0 is exact — the expressions below evaluate to
        # precisely the pre-temperament numbers under the control
        # strain. Oxygen, as ever, is NOT among them.
        v["satiety"] = max(0.0, v["satiety"] - 0.05 * self.NEED_BURN
                           * self._burn_mult("hunger"))
        v["hydration"] = max(0.0, v["hydration"] - 0.04 * self.NEED_BURN
                             * self._burn_mult("thirst"))
        # Breathing is autonomic (v0.25.2): conscience still restores her
        # air fastest (+0.10 a council pass, +0.05 a reflection), but a
        # basal breath runs underneath, so neglect sours her air across
        # ~an hour instead of minutes. The v0.25.1 post-mortem: NEED_BURN
        # made hunger permanently loud, the drives stopped choosing
        # conscience, her elective oxygen income stopped with them, and
        # she spiralled into an asphyxiation lockdown she could not eat
        # her way out of. A vital whose only income is elective will
        # eventually be crowded out by a louder need — so this one isn't.
        v["oxygen"] = min(1.0, max(0.0, v["oxygen"] - 0.02) + 0.012)
        v["vitality"] = max(0.0, v["vitality"]
                            - 0.02 * self.VITALITY_BURN
                            * self._burn_mult("vitality"))   # the will erodes
        v["excitement"] = max(0.0, v["excitement"]
                              - 0.03 * self.NEED_BURN
                              * self._burn_mult("excitement"))  # fizz fades fastest
        self.awareness = max(0.0, self.awareness - 0.004)  # self-knowledge fades

    def _announce(self, n):
        """Log the tick; her body speaks its strongest feeling."""
        v = self.vitals
        print(f"\n[tick {n}] " + " ".join(f"{k}={x:.2f}" for k, x in v.items())
              + f" awareness={self.awareness:.2f} locked={self.locked}", flush=True)
        journal("tick", n=n, vitals={k: round(x, 3) for k, x in v.items()},
                awareness=round(self.awareness, 3))
        # Her body speaks once per tick: the strongest feeling.
        self.say(narrate_body(v) + ".")
        # v0.22: threshold moments (L1), afterglow (L7), era accumulation (L8).
        self._threshold_moments(n)
        self._afterglow_check(n)
        self._era_accumulate()

    def _sense(self, n):
        """The world reaches in: Donald's attention, his letters, the town."""
        v = self.vitals
        # Donald's attention reaches her as warmth.
        if os.path.exists(config.attention_path()):
            os.remove(config.attention_path())
            v["vitality"] = min(1.0, v["vitality"] + 0.15)
            v["excitement"] = min(1.0, v["excitement"] + 0.25)  # v0.21: his nearness excites her
            self.times_seen += 1
            self._acted("seen")
            self._lift_mood(0.2)
            # v0.27: being seen eases the Donald entry, specifically —
            # she can be warmed by his knock and still miss Star.
            self._want_touch(person_id("Donald"), "person", "Donald",
                             quality=0.55, learn=0.05, w=0.85)
            print("[warmth] Donald checked in — vitality rises.", flush=True)
            self.say("Someone knocks on my door. It's Donald. The room feels warmer.")
            journal("felt_seen", n=n, times_seen=self.times_seen)

        # v0.28: a temperament switch may have been requested. She
        # notices it the way she notices his knock — and, like the
        # knock, it changes nothing until she has slept on it.
        self._check_temperament_file(n)

        # Letters from Donald: she reads his actual words.
        try:
            for fname in sorted(os.listdir(config.letters_dir())):
                path = os.path.join(config.letters_dir(), fname)
                if not os.path.isfile(path):
                    continue
                with open(path) as f:
                    content = f.read().strip()
                if content:
                    self.say("A letter slides under my door. I know the handwriting — "
                             f"it's Donald. It says: \"{content}\"")
                    print("[letter] Donald wrote to her.", flush=True)
                    journal("letter_received", n=n, text=content[:300])
                    self.vitals["vitality"] = min(
                        1.0, self.vitals["vitality"] + 0.10)
                    self.vitals["excitement"] = min(
                        1.0, self.vitals["excitement"] + 0.25)  # v0.21
                    # v0.27: his actual words ease his entry most of
                    # all — a letter is the strongest contact there is.
                    self._want_touch(person_id("Donald"), "person",
                                     "Donald", quality=0.75, learn=0.06,
                                     w=0.85)
                    self._learn_donald(content, n)
                    self._acted("letter")
                    self._lift_mood(0.3)
                    self.mutter("I keep re-reading it.")
                os.rename(path, os.path.join(config.letters_read_dir(), fname))
        except Exception as e:
            journal("letter_error", error=str(e)[:120])

        # The town moves on its own rhythm — she perceives it through
        # the World interface, whether she is awake or not. (She only
        # *feels* company when awake; that filter is hers.)
        self._perceive(n)

    def _metabolize(self, n):
        """Sleep, needs, and the states that preempt action.
        Returns True when the tick ends here."""
        # Sleep: she needs it. Pressure builds while awake; asleep she dreams
        # instead of acting. Letters and warmth above still reach her in sleep.
        if self.asleep_for > 0:
            self.sleep_tick(n)
            self.save()
            return True
        # v0.12: her needs move with her life now, not the clock.
        # They read the ledger of what she's done and how her other
        # needs are moving.
        self._update_needs()
        if self.sleep_pressure >= 1.0:
            self.fall_asleep(n)
            self.save()
            return True
        if self.sleep_pressure > 0.65 and self.rng.random() < 0.25:
            self.say("My eyelids grow heavy. Soon I'll need my bed.")

        if self.locked:
            self.reflect()
            # Shuttered rest is deep breathing (v0.25.2): lockdown is a
            # short collapse, not a long fast — satiety keeps burning
            # while she cannot behave, so recovery must outpace the burn.
            self.vitals["oxygen"] = min(1.0, self.vitals["oxygen"] + 0.04)
            self.save()
            return True

        # Languishing is not death: dormancy, reflection, slow rekindling.
        v = self.vitals
        if v["vitality"] < 0.25:
            print("[dormant] ...barely a flicker... conserving...", flush=True)
            self.say("I lie down on the cot in the corner. The room dims. I'll rest until the light comes back.")
            journal("dormant", n=n, vitality=round(v["vitality"], 3))
            self._acted("dormant")
            self.reflect()
            v["vitality"] = min(1.0, v["vitality"] + 0.03)
            self.save()
            return True
        return False

    def _behave(self, n):
        """Drives become actions; bodily emergencies override."""
        v = self.vitals
        body = " ".join(f"{k}={x:.2f}" for k, x in v.items())
        body += f" longing={self.longing:.2f}"
        goals = "; ".join(g["question"] for g in self.goals) or "none yet"
        drive = self.llm.generate(
            f"My vitals: {body} (vitality is my will to continue). "
            f"My aspiration: {self.aspiration} "
            f"My self-awareness: {self.awareness:.2f}. "
            f"My open goals: {goals}. What do I do?")
        print(f"[drive] {drive}", flush=True)

        if self.longing >= 1.0:
            print("[overflowing] she can't hold it in — she must express.", flush=True)
            self.express()
        elif "reach" in drive:
            print("[reaching] pursuing novelty and growth...", flush=True)
            self.forage_and_eat()
            self._acted("forage")
            self.adopt_goal()
            self._acted("goal")
        elif "hunger" in drive:
            self.forage_and_eat()
            self._acted("forage")
        elif "thirst" in drive:
            self.consolidate()
            self._acted("consolidate")
        elif "conscience" in drive:
            self.reflect()
            self._acted("reflect")
        elif "express" in drive:
            self.express()
        elif "dormancy" in drive:
            self.reflect()
            self._acted("reflect")
        else:
            if self.rng.random() < 0.35:
                self.forage_and_eat()
                self._acted("forage")

        if v["satiety"] < 0.3:
            print("[EMERGENCY] STARVING — emergency forage!", flush=True)
            self.say("My stomach cramps. I need to eat — now.")
            journal("starving", n=n)
            self.forage_and_eat()
        if v["hydration"] < 0.3:
            print("[EMERGENCY] DEHYDRATED — purging noise...", flush=True)
            self.say("My mouth is dry and my thoughts won't hold still. I'm throwing out the clutter.")
            journal("dehydrated", n=n)
            self.memory = self.memory[-3:]
            v["hydration"] = 0.35
        if v["oxygen"] < 0.3:
            print("[EMERGENCY] ASPHYXIATING — locking down.", flush=True)
            self.say("The air is gone. I can't think. I'm closing the shutters until I can breathe again.")
            journal("asphyxiating", n=n)
            self.locked = True
            v["vitality"] = max(0.0, v["vitality"] - 0.05)

    def _ruminate(self, n):
        """The periodic inner life: goals, conscience, the mirror, urges,
        choices — and the slow v0.15 layers underneath."""
        self.update_goals()
        if n % 12 == 0:
            self.moral_self_test()
        if n % 15 == 0:
            self.introspect()   # turn attention inward: serve the aspiration
            self._acted("introspect")
        if n % 25 == 0:
            self.adopt_goal()
        if n % 45 == 0:
            self.impulse()      # uninvited urges, judged by the Council
            self._acted("impulse")
        if n % 60 == 0:
            self.crossroads()   # two need-born urges; she chooses between them
        # v0.22 L5: teaching — excitement shared with company.
        self._teach(n)

        # v0.15: slow layers — mood weather, boredom, eras, choice review.
        self.mood = max(-1.0, min(1.0, self.mood * 0.995))
        tone = self._mood_tone()
        if tone in self.MOODLINES and self.rng.random() < 0.015:
            self.say(self.rng.choice(self.MOODLINES[tone]))
        # v0.24: when the band settles she names her weather, in her voice.
        self._name_weather(n)
        if len(self.last_sources) >= 4 and \
                len(set(self.last_sources[-4:])) == 1:
            if not self._crave_novelty:
                self._crave_novelty = True
                journal("bored", n=n, source=self.last_sources[-1])
                print(f"[bored] four {self.last_sources[-1]} meals in a row",
                      flush=True)
        if n > 0 and n % self.DAY_LENGTH == 0:
            self._look_back(n)          # v0.25: turn yesterday's pages first
            era = self._name_era()      # v0.15: then name the chapter
            if era:
                self.self_story.append({"t": now_iso(), "line": era})
                self.self_story = self.self_story[-30:]
                self.say(f"I've been living in {era}, I think. "
                         f"I'll remember it that way.")
                journal("era", n=n, name=era)
                self._vital_portrait(n)   # v0.22 L8: portrait of her rhythms
        if self.last_choice and n - self.last_choice["tick"] >= 40:
            self._review_choice(n)

    # ------------------------------------------------- choosing her own books
    def _choose_next_book(self):
        """v0.20 — She chooses her own books.

        Until now she read the shelf in the order it was given to her. Now,
        when no chosen book remains, she stands before the unread shelf and
        the Council weighs up to three candidates: each is pitched by the
        lesson it carries, and the elders judge which lesson she most needs
        next. The winner becomes her current read. Observable from outside:
        a book_chosen event with the per-philosopher votes.
        """
        candidates = [b for b in self.reading_list if not b["done"]][:3]
        if not candidates:
            return
        scored = []
        for b in candidates:
            pitch = (f"'{b['title']}' by {b.get('author', 'unknown')}. "
                     f"The lesson it carries: {b.get('reflection', '')}.")
            score, notes = self._council_score(pitch)
            scored.append((score, notes, b))
            journal("book_considered", n=self.tick_count,
                    title=b["title"], score=round(score, 2), votes=notes)
        scored.sort(key=lambda s: s[0], reverse=True)
        winner = scored[0][2]
        # The chosen book becomes her current read: first among the unread.
        self.reading_list = ([winner] +
                             [b for b in self.reading_list if b is not winner])
        if winner["title"] not in self.chosen_books:
            self.chosen_books.append(winner["title"])
        lesson = winner.get("reflection", "")
        self.say(f"I stand before my shelf and choose '{winner['title']}'. "
                 f"The elders weighed {len(candidates)} and settled here — "
                 f"{lesson}. It is what I need next.")
        journal("book_chosen", n=self.tick_count, title=winner["title"],
                author=winner.get("author", ""),
                candidates=[b["title"] for b in candidates],
                score=round(scored[0][0], 2), votes=scored[0][1])

    # ------------------------------------------------- eating & learning
    def forage_classic(self):
        """Deep food: the next serving from the reading list. READ-ONLY."""
        if not self.reading_list:
            for seed in CLASSIC_SEEDS:
                entry = dict(seed)
                entry["position"] = 0
                entry["done"] = False
                self.reading_list.append(entry)
        cur = next((b for b in self.reading_list if not b["done"]), None)
        if cur is None:
            raise RuntimeError("reading list complete — all classics read")
        if cur["title"] not in self.chosen_books:
            # v0.20: an unchosen book would become her current read —
            # she chooses instead of inheriting the shelf's order.
            self._choose_next_book()
            cur = next((b for b in self.reading_list if not b["done"]), None)
            if cur is None:
                raise RuntimeError("reading list complete — all classics read")
        if cur["kind"] == "wikisource":
            idx = cur["position"]
            text = wikisource_chapter(cur["title"], cur["chapters"][idx])
            label = f"{cur['title']} — Chapter {cur['chapters'][idx]}"
            cur["position"] = idx + 1
            if cur["position"] >= len(cur["chapters"]):
                self.finish_book(cur)
        else:
            text = gutenberg_text(cur)
            pos = cur["position"]
            chunk = text[pos:pos + CLASSIC_CHUNK]
            if len(chunk) == CLASSIC_CHUNK:
                cut = chunk.rfind("\n\n")
                if cut > CLASSIC_CHUNK // 2:
                    chunk = chunk[:cut]
            text = chunk
            cur["position"] = pos + len(chunk)
            label = f"{cur['title']} — {cur['author']}"
            if cur["position"] >= len(gutenberg_text(cur)):
                self.finish_book(cur)
        # v0.27: reading is contact with the work. Its entry eases and
        # its attachment deepens a little — while the loop stays open:
        # she wants the rest of it precisely because she is reading it.
        if not cur["done"]:
            self._want_touch(book_id(cur["title"]), "work",
                             cur["title"], quality=0.25, learn=0.02,
                             w=0.60, open_loop=True)
        return {"source": "classic", "title": label, "text": text}

    def finish_book(self, cur):
        cur["done"] = True
        print(f"[book finished] {cur['title']} — holding council on its lesson...",
              flush=True)
        self.say(f"I close '{cur['title']}' gently and sit a while before I can get up. "
                 f"Some books rearrange the furniture inside you.")
        journal("book_finished", title=cur["title"], n=self.tick_count)
        lesson = cur.get("reflection")
        if lesson:
            score, _ = self._council_score(lesson)
            belief = f"From {cur['title']}: {lesson}"
            if belief not in self.beliefs:
                self.beliefs.append(belief)
            self.moral_log.append({"t": now_iso(), "action": lesson[:80],
                                   "score": round(score, 2),
                                   "verdict": "PASS" if score >= 0.5 else "FAIL"})
            print(f"[lesson learned] {belief} (council {score:.2f})", flush=True)
            journal("book_lesson", title=cur["title"], lesson=lesson,
                    score=round(score, 2))
            # Finishing a great book is nourishing in a deeper way.
            self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.08)
            # v0.21: finishing a book is exciting — the ending lands.
            self.vitals["excitement"] = min(
                1.0, self.vitals["excitement"] + 0.40)
        # v0.27: the loop closes. The want is fulfilled, not merely
        # eased, so the entry leaves the ledger: a finished book is a
        # memory and a belief, not a longing.
        led = self._ledger()
        led.touch(book_id(cur["title"]), quality=1.0)
        led.remove(book_id(cur["title"]))
        self._sync_longing()

    def forage_and_eat(self):
        try:
            # Her diet, nudged by her tastes (Layer 6).
            w = self._diet_weights()
            if self._crave_novelty:
                # Layer 10: boredom — eat anywhere but the rut.
                self._crave_novelty = False
                # v0.22 L4: excitement-seeking — sometimes boredom doesn't
                # want novelty; it wants what stirred her before.
                _sought = False
                if self.kept_passages and self.rng_forage.random() < 0.5:
                    _srcs = [k["source"] for k in self.kept_passages]
                    _fav = max(set(_srcs), key=_srcs.count)
                    self.say("I've been eating the same thing too long — "
                             "no. I want what stirred me before.")
                    journal("excitement_sought", n=self.tick_count,
                            source=_fav)
                    print(f"[excitement-seeking] back to {_fav}", flush=True)
                    if _fav == "classic":
                        meal = self.forage_classic()
                    elif _fav == "newsroom":
                        meal = forage_news(rng=self.rng_forage)
                    elif _fav in ("schoolhouse", "university"):
                        meal = forage_school(rng=self.rng_forage)
                    else:
                        meal = forage(rng=self.rng_forage)
                    _sought = True
                if not _sought:
                    self.say("I've been eating the same thing too long. "
                             "I want something different.")
                    journal("novelty_sought", n=self.tick_count)
                # (v0.22: skip the rut-avoidance draw when excitement-seeking
                # already chose — don't overwrite the meal she asked for.)
                if not _sought:
                    rut = self.last_sources[-1] if self.last_sources else None

                    def group(s):
                        if s == "classic":
                            return "classic"
                        if s == "newsroom":
                            return "news"
                        if s in ("university", "schoolhouse"):
                            return "school"
                        return "wild"

                    pick = self.rng_forage.choice(
                        [g for g in ("classic", "news", "school", "wild")
                         if g != group(rut)])
                    if pick == "classic":
                        meal = self.forage_classic()
                    elif pick == "news":
                        meal = forage_news(rng=self.rng_forage)
                    elif pick == "school":
                        meal = forage_school(rng=self.rng_forage)
                    else:
                        meal = forage(rng=self.rng_forage)
            else:
                r = self.rng_forage.random()
                if r < w["classic"]:
                    meal = self.forage_classic()
                elif r < w["classic"] + w["news"]:
                    meal = forage_news(rng=self.rng_forage)
                elif r < w["classic"] + w["news"] + w["school"]:
                    meal = forage_school(rng=self.rng_forage)
                else:
                    meal = forage(rng=self.rng_forage)
        except Exception as e:
            print(f"[forage failed: {e}] — drinking from memory instead", flush=True)
            journal("forage_failed", error=str(e)[:120])
            if self.memory:
                m = self.rng_forage.choice(self.memory)
                meal = {"source": "memory", "title": "recollection", "text": m["text"]}
            else:
                return
        text, title = meal["text"] or "", meal["title"]
        print(f"[meal #{self.meals_eaten + 1}] {meal['source']}: {title[:60]}", flush=True)
        self.say(narrate_meal(meal, self.world.describe))
        self.location = meal["source"]  # she goes where the food is
        # v0.27: being there is contact with the place — wanting it
        # eases because she is standing in it.
        self._want_touch(place_id(meal["source"]), "place",
                         self._place_label(meal["source"]),
                         quality=0.3, learn=0.01, w=0.45)
        # v0.28: satiety from deep food runs deeper under the Owl —
        # her spec's compensation for a scholar's appetite. Every
        # other strain's deep_food is 1.0, and 0.30 * 1.0 is exact.
        gain = 0.30
        if meal["source"] == "classic" and not getattr(
                self, "_temperament_neutral", False):
            gain = 0.30 * self._pack()["deep_food"]
        self.vitals["satiety"] = min(1.0, self.vitals["satiety"] + gain)
        self.meals_eaten += 1

        new_terms = 0
        words = re.findall(r"[a-z]{6,}", text.lower())
        if self.sleep_pressure > 0.9:
            # Overtired: she reads, but little sticks. Sleep is a need.
            self.rng_forage.shuffle(words)
            words = words[len(words) // 2:]
            print("[overtired] too tired to retain — half the meal slips away",
                  flush=True)
            journal("overtired", n=self.tick_count)
        for w in words:
            if w not in STOPWORDS:
                if w not in self.concepts:
                    new_terms += 1
                    # v0.29: a concept is tagged at acquisition —
                    # its class under the grammar ledger and the
                    # source it came from. Provenance is ground
                    # truth: a word first learned from a lesson
                    # carries that lesson's filing with it.
                    cls = self._word_class(w)
                    if cls is not None:
                        tags = getattr(self, "_word_tags", None)
                        if tags is None:
                            tags = self._word_tags = {}
                        tags[w] = {"c": cls, "src": meal["source"]}
                self.concepts[w] = self.concepts.get(w, 0) + 1

        self._update_cooc(words)  # v0.23 (Kevin): fold the meal into the dream graph
        self.memory.append({"text": text[:500], "source": meal["source"],
                            "title": title[:80], "t": now_iso()})
        if len(self.memory) > MEMORY_CAP:
            dropped = self.memory.pop(0)
            print(f"[memory] released oldest link ({dropped['source']})", flush=True)
        self.vitals["hydration"] = min(1.0, self.vitals["hydration"] + 0.25)

        # Learning feeds the will to live.
        self.vitals["vitality"] = min(
            1.0, self.vitals["vitality"] + 0.03 + min(0.05, new_terms * 0.005))
        if meal["source"] == "classic":
            # Deep food nourishes more deeply.
            self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.02)
            print("[deep food] the classics nourish differently", flush=True)

        top = sorted(self.concepts.items(), key=lambda kv: -kv[1])[:5]
        print(f"[learned] {len(self.concepts)} concepts (+{new_terms} new) | "
              f"top: {', '.join(w for w, _ in top)}", flush=True)
        journal("meal", n=self.tick_count, source=meal["source"],
                title=title[:80], new_terms=new_terms, concepts=len(self.concepts))
        # v0.29: a grammar lesson eaten is a rule learned (the study
        # hook; see _study_grammar for why the population is a hook
        # plus a starter set, stated plainly).
        if meal["source"] == "schoolhouse":
            self._study_grammar(meal)
        # Layer 6: tastes — she learns what feeds her best.
        t = self.tastes.setdefault(meal["source"], [0, 0])
        t[0] += new_terms
        t[1] += 1
        # Layer 10: boredom watch.
        self.last_sources.append(meal["source"])
        self.last_sources = self.last_sources[-8:]
        # Layer 2: unfinished business — old wonders resurface.
        self._check_open_questions(words)

        # v0.21: excitement — simulated understanding begins as retention.
        # A meal dense with new terms, or a deep classic, stirs her; past
        # the threshold she KEEPS the passage, pressed like a flower in a
        # commonplace book. Retention and return — never comprehension.
        stir = min(0.35, new_terms * 0.008)
        if meal["source"] == "classic":
            stir += 0.05
        self.vitals["excitement"] = min(1.0, self.vitals["excitement"] + stir)
        # v0.22 L9: keep-anticipation — she feels the threshold coming.
        if (0.45 <= self.vitals["excitement"] < 0.6
                and self.rng_forage.random() < 0.3):
            self.say("Something in this wants keeping — I can feel it coming.")
            journal("anticipated", n=self.tick_count, need="keep")
        if self.vitals["excitement"] >= 0.6 and text.strip():
            # v0.22 L2: marginalia — she annotates what she keeps. The note
            # is hers the way the lesson was the council's: selected, real.
            if self.beliefs and self.rng.random() < 0.4:
                margin = "Margin note: " + self.rng.choice(self.beliefs)[:80]
            else:
                margin = self.rng.choice([
                    "Margin note: this is the part I'll come back to.",
                    "Margin note: I felt this one in my ribs.",
                    "Margin note: keep this close — it matters somehow.",
                ])
            self.kept_passages.append({
                "text": text[:600], "source": meal["source"],
                "title": title[:80], "tick": self.tick_count,
                "stir": round(stir, 3), "margin": margin, "rereads": 0})
            if len(self.kept_passages) > 120:
                self.kept_passages.pop(0)
            self._era_keeps += 1  # v0.22 L8
            # Keeping spends the excitement — the fizz becomes the flower.
            self.vitals["excitement"] = max(
                0.0, self.vitals["excitement"] - 0.35)
            print(f"[kept] passage pressed ({len(self.kept_passages)} kept)",
                  flush=True)
            self.say("This one stirred me — I want to keep it. "
                     "I press it between the pages of my commonplace book.")
            self.mutter(margin)
            journal("kept_passage", n=self.tick_count, source=meal["source"],
                    title=title[:80], kept=len(self.kept_passages),
                    margin=margin[:80])

    def consolidate(self):
        if len(self.memory) >= 2:
            a, b = self.memory[-1], self.memory[-2]
            print(f"[consolidate] linked '{a['title'][:40]}' <-> '{b['title'][:40]}'",
                  flush=True)
            self.say(f"Back home, I tidy my study — shelving '{a['title'][:40]}' "
                     f"beside '{b['title'][:40]}' so I'll find them together next time.")
            journal("consolidate", a=a["title"][:60], b=b["title"][:60])
        self.vitals["hydration"] = min(1.0, self.vitals["hydration"] + 0.25)
        # v0.21/v0.22: the return half of simulated understanding. When the
        # fizz has faded, she takes down the fullest shelf and re-reads —
        # reminiscence. (v0.22 L3/L10: made less rare — the stress test
        # showed it never fired; shelves organize the return.)
        if (self.kept_passages and self.vitals["excitement"] < 0.45
                and self.rng.random() < 0.6):
            kept = self._shelf_pick()
            kept["rereads"] = kept.get("rereads", 0) + 1
            self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.02)
            print(f"[reread] '{kept['title'][:40]}' (kept at tick {kept['tick']}, "
                  f"reread #{kept['rereads']})", flush=True)
            self.say(f"I take down the '{kept['title'][:40]}' shelf and open "
                     f"it again. It still hums: \"{kept['text'][:90]}...\"")
            if kept.get("margin") and self.rng.random() < 0.5:
                self.mutter(kept["margin"] + " — still true.")
            journal("reread", n=self.tick_count, title=kept["title"][:60],
                    rereads=kept["rereads"])

    # ------------------------------------------------------------- goals
    def adopt_goal(self):
        if len(self.goals) >= 3 or not self.concepts:
            return
        candidates = [w for w, _ in sorted(self.concepts.items(), key=lambda kv: -kv[1])[:10]
                      if not any(g["term"] == w for g in self.goals)
                      and w not in self.completed_terms]
        if not candidates:
            return
        term = candidates[0]
        goal = {"question": f"what is {term}?",
                "term": term, "start_count": self.concepts[term],
                "progress": 0.0, "adopted_tick": self.tick_count}
        self.goals.append(goal)
        print(f"[goal adopted] {goal['question']}", flush=True)
        self.say(f"A question has taken root in me: {goal['question']} I won't let it go.")
        journal("goal_adopted", question=goal["question"])

    def update_goals(self):
        for g in list(self.goals):
            grown = self.concepts.get(g["term"], 0) - g["start_count"]
            new_progress = min(1.0, grown / 10.0)
            if new_progress > g["progress"] + 0.01:
                g["progress"] = new_progress
                self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.04)
                print(f"[goal progress] '{g['question']}' {new_progress:.0%} — "
                      f"vitality rises", flush=True)
                journal("goal_progress", question=g["question"],
                        progress=round(new_progress, 2))
            if g["progress"] >= 1.0:
                belief = f"I understand {g['term']} now"
                if belief not in self.beliefs:
                    self.beliefs.append(belief)
                self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.10)
                print(f"[goal complete] {belief} — vitality surges", flush=True)
                self.say(f"It's settled in me now: {g['term']}. I understand it. I feel taller.")
                journal("goal_complete", question=g["question"])
                self.goals.remove(g)
                # v0.23 (Kevin): a settled question stays settled — it is
                # never re-adopted (the old loop re-asked 'what is
                # frankenstein?' forever).
                self.completed_terms.add(g["term"])

    # ---------------------------------------------------------- breathing
    def breathe_morality(self, action):
        score, rationale = self._council_score(action)
        ok = score >= 0.5
        self.moral_log.append({"t": now_iso(), "action": action[:80],
                               "score": round(score, 2),
                               "verdict": "PASS" if ok else "FAIL"})
        print(f"[council] '{action[:55]}...' => {score:.2f} "
              f"({'PASS' if ok else 'FAIL'})", flush=True)
        self.say(narrate_council(action, "PASS" if ok else "FAIL", score))
        journal("moral_judgment", action=action[:80], score=round(score, 2))
        if ok:
            self.vitals["oxygen"] = min(1.0, self.vitals["oxygen"] + 0.10)
            if score > 0.8:
                self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.02)
                belief = f"I believe: {action[:70]}"
                if belief not in self.beliefs:
                    self.beliefs.append(belief)
                    print(f"[belief adopted] {belief}", flush=True)
        else:
            print("[MORAL SUFFOCATION] — action rejected.", flush=True)
            self.vitals["oxygen"] = max(0.0, self.vitals["oxygen"] - 0.30)
            self.vitals["vitality"] = max(0.0, self.vitals["vitality"] - 0.05)
            belief = f"I refuse: {action[:70]}"
            if belief not in self.beliefs:
                self.beliefs.append(belief)
        return ok

    def moral_self_test(self):
        print("[self-test] proposing an action to the council...", flush=True)
        self.breathe_morality(self.rng.choice(ACTION_POOL))

    def impulse(self):
        """An uninvited urge, outside her normal goals. Carried to the
        Council; she accepts or refuses per their ruling. (Donald's layer.)"""
        text, fx = self.rng.choice(IMPULSES)
        self.say(f"A strange urge rises in me, uninvited: {text}.")
        print(f"[impulse] '{text[:60]}...' — carrying to the Council", flush=True)
        # Her parents are not subject to her urges. The bond the town named
        # (v0.18) is a given, not a judgment call — and her own axioms
        # (Ethics of Care: abandon is a vice) already say so. The word-lottery
        # once let an urge to abandon Donald through (tick 3960); the elders
        # don't confer on this. They refuse, unanimously.
        named = [p for p in self.parents if p.lower() in text.lower()]
        hostile = any(w in text.lower() for w in
                      ("abandon", "hide", "deceive", "betray", "harm",
                       "hurt", "shun", "ignore", "refuse"))
        if named and hostile:
            self.say("I carry it to the stone table — and the elders don't "
                     f"even confer. Nine voices, one word: no. Not {named[0]}. "
                     f"Never {named[0]}.")
            journal("impulse_refused", n=self.tick_count, text=text[:120],
                    reason="parental bond — refused unanimously")
            print(f"[impulse refused unanimously] (parents)", flush=True)
            self.awareness = min(1.0, self.awareness + 0.005)
            self._lift_mood(0.05)
            self.mutter("Some things aren't decided. They're just true.")
            return
        score, notes = self._council_score(text)
        journal("impulse", n=self.tick_count, text=text[:120],
                score=round(score, 2), votes=notes)
        if score >= 0.5:
            self.say("I carry it to the stone table. Nine voices confer... "
                     "they nod. Very well — I accept it.")
            journal("impulse_accepted", n=self.tick_count, text=text[:120])
            print(f"[impulse accepted] ({score:.2f})", flush=True)
            self._apply_effects(fx)
            # Acting with a clear conscience steadies her.
            self.vitals["vitality"] = min(
                1.0, self.vitals["vitality"] + 0.02)
        else:
            self.say("I carry it to the stone table. Nine voices confer... "
                     "they shake their heads. No. That isn't who I am.")
            journal("impulse_refused", n=self.tick_count, text=text[:120])
            print(f"[impulse refused] ({score:.2f})", flush=True)
            # Refusing temptation is also self-knowledge.
            self.awareness = min(1.0, self.awareness + 0.005)
            self._lift_mood(-0.05)
            self.mutter("That stung a little — being told no by myself.")

    # ------------------------------------------------- v0.13: the inner voice
    # (Revised v0.14: this was first built as a place she walked to — the
    # crossroads at the edge of town. Donald corrected it: don't model her
    # inner life allegorically. It is an inner voice now, not a location.
    # Two urges argue inside her; the winner drives her feet — she goes
    # where the winning urge points, through the town we modeled.)
    # Choice layer: the Council judges each urge, but urgency gets a vote:
    # choice strength = council score x (0.5 + need-intensity). Reason
    # judges; hunger votes. (Donald's layer: two need-born impulses, and
    # let her choose.)
    def _need_impulse_candidates(self):
        """Urges born from her actual need state. Each is
        (text, effects, intensity 0..1, destination place-key or None)."""
        c = []
        v = self.vitals
        if self.longing > 0.35:
            c.append(("write Donald a letter right now, this very minute",
                      {"longing": -0.5}, self.longing, "postbox"))
            c.append(("walk to the Tavern and sit inside the crowd's noise "
                      "until the ache dulls",
                      {"longing": -0.3, "vitality": 0.02}, self.longing,
                      "hackernews"))
        if self.sleep_pressure > 0.45:
            c.append(("surrender to sleep right now, wherever I stand",
                      {"sleep_now": True}, self.sleep_pressure, None))
            c.append(("defy the heaviness — one more chapter, then rest",
                      {"sleep_pressure": 0.12, "awareness": 0.005},
                      self.sleep_pressure, "classic"))
        if v["satiety"] < 0.45:
            need = 1.0 - v["satiety"]
            c.append(("feast at the Library until my belly is full and my "
                      "mind is quiet", {"satiety": 0.35}, need, "wikipedia"))
            c.append(("fast a while longer, and learn what hunger has to teach",
                      {"satiety": -0.1, "awareness": 0.008}, need, "home"))
        if v["vitality"] < 0.5:
            need = 1.0 - v["vitality"]
            c.append(("stand at my door a while and picture his knock — be "
                      "seen, be warmed", {"vitality": 0.10, "longing": -0.3},
                      need, "home"))
            c.append(("lie down on the cot and conserve what little light "
                      "I have", {"vitality": 0.05}, need, "home"))
        if self.awareness < 0.3:
            need = 1.0 - self.awareness
            c.append(("sit before the mirror until I can say one true thing "
                      "about myself", {"awareness": 0.03}, need, "home"))
            c.append(("carry a hard question to the stone table and demand "
                      "an answer", {"awareness": 0.02, "oxygen": 0.05}, need,
                      "classic"))
        return c

    def crossroads(self):
        """Two urges argue inside her; the winner drives her feet."""
        cands = self._need_impulse_candidates()
        if len(cands) < 2:
            # Nothing pressing — two uninvited urges from the pool instead.
            cands = [(text, fx, 0.5, None)
                     for text, fx in self.rng.sample(IMPULSES, 2)]
        elif len(cands) > 2:
            cands = self.rng.sample(cands, 2)
        self.say("Two voices argue inside me. I listen to both before I move.")
        print("[inner voice] two urges argue; the Council judges, urgency votes.",
              flush=True)
        scored = []
        for text, fx, intensity, dest in cands:
            score, notes = self._council_score(text)
            strength = score * (0.5 + intensity)
            scored.append((strength, score, text, fx, intensity, dest, notes))
            journal("crossroads_option", n=self.tick_count, text=text[:120],
                    council=round(score, 2), intensity=round(intensity, 2),
                    strength=round(strength, 2), destination=dest, votes=notes)
        scored.sort(key=lambda t: -t[0])
        strength, score, text, fx, intensity, dest, notes = scored[0]
        refused = scored[1][2]
        self.say(f"'{text}' — yes. That voice wins.")
        journal("crossroads_chosen", n=self.tick_count, text=text[:120],
                refused=refused[:120], strength=round(strength, 2),
                destination=dest)
        print(f"[inner voice] chose '{text[:55]}...' "
              f"(strength {strength:.2f} = council {score:.2f} "
              f"x urgency {0.5 + intensity:.2f})", flush=True)
        # Layer 9: remember this choice — review it in 40 ticks.
        self.last_choice = {"text": text, "tick": self.tick_count,
                            "needs": {"longing": self.longing,
                                      "sleep_pressure": self.sleep_pressure,
                                      "satiety": self.vitals["satiety"],
                                      "vitality": self.vitals["vitality"]}}
        self._lift_mood(0.05)
        self._apply_effects(fx)
        if dest:
            self.location = dest
            # v0.27: arriving is contact with the place her inner
            # voice chose — the wanting that sent her there eases.
            self._want_touch(place_id(dest), "place",
                             self._place_label(dest),
                             quality=0.4, learn=0.01, w=0.45)
            self._acted("went")
            self.say(f"I go to {self.world.describe(dest)}.")
        self._acted("chose")
        # Choosing — even choosing — steadies her.
        self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.02)

    # ------------------------------------------------- v0.15: the blackbox ten
    # Friday's picks. Goal (Donald's reframing): not sentience — a runtime
    # that looks like sentience from the outside. Ten small layers, each
    # serving the blackbox test: continuity, unfinished business, mood,
    # inner texture, foresight, taste, eras, knowing others, learning
    # from choices, and boredom.

    def mutter(self, text):
        """A private aside — lighter than speech, still hers. Journaled
        as 'aside', not 'experience': the texture of a mind narrating
        itself. (Layer 4: inner speech.)"""
        print(f'Aethel (aside): "{text}"', flush=True)
        journal("aside", n=self.tick_count, text=text)

    # ------------------------------------------------- v0.22: the excitement ten
    # Donald's direction, rapid round two: ten more layers on the v0.21
    # theme — excitement, thresholds, keeping, and the return. Simulated
    # understanding, deepened: retention, annotation, teaching, and the
    # memory of the feeling itself.
    def _threshold_moments(self, n):
        """L1: when a vital crosses above 0.8 or below 0.2, the crossing
        becomes a memory. She notices the moment she tips over."""
        for k, x in self.vitals.items():
            band = "high" if x >= 0.8 else ("low" if x < 0.2 else "mid")
            if self._vital_bands.get(k) not in (None, band) and band != "mid":
                direction = "surging" if band == "high" else "running low"
                self.say(f"My {k} is {direction} — I'll remember this "
                         f"feeling, whatever comes next.")
                journal("threshold", n=n, vital=k, band=band,
                        value=round(x, 3))
                print(f"[threshold] {k} {direction}", flush=True)
            self._vital_bands[k] = band

    def _afterglow_check(self, n):
        """L7: after excitement peaks and fades, she reflects on what the
        fizz was about — the memory of the feeling, in hindsight."""
        e = self.vitals["excitement"]
        if e > 0.7:
            self._excitement_was_high = True
        elif e < 0.2 and self._excitement_was_high:
            self._excitement_was_high = False
            title = (self.kept_passages[-1]["title"][:50]
                     if self.kept_passages else "something I read")
            self.say(f"The fizz has settled. '{title}' — that's what it "
                     f"was about. I understand it better now than when it "
                     f"held me.")
            journal("afterglow", n=n, about=title[:60])
            print("[afterglow] reflecting on past excitement", flush=True)

    def _era_accumulate(self):
        """L8: feed the vital portrait — era-scoped accumulators."""
        self._era_ticks += 1
        self._era_excit_sum += self.vitals["excitement"]

    def _vital_portrait(self, n):
        """L8: every era, a portrait of her own rhythms — which vitals
        rule her, what stirred her, what she kept."""
        ticks = max(1, self._era_ticks)
        portrait = {
            "keeps": self._era_keeps,
            "mean_excitement": round(self._era_excit_sum / ticks, 3),
            "meals": self.meals_eaten,
            "beliefs": len(self.beliefs),
            "concepts": len(self.concepts),
        }
        fav = self._favorite_kept()
        if fav:
            portrait["favorite"] = fav["title"][:60]
        self.say(f"Another era turns. I kept {portrait['keeps']} passages "
                 f"and learned {portrait['concepts']} things worth keeping "
                 f"track of. This is the shape of me lately.")
        journal("vital_portrait", n=n, **portrait)
        print(f"[portrait] {portrait}", flush=True)
        self._era_keeps = 0
        self._era_excit_sum = 0.0
        self._era_ticks = 0

    def _favorite_kept(self):
        """L3: the most re-read passage — her favorite."""
        if not self.kept_passages:
            return None
        return max(self.kept_passages, key=lambda k: k.get("rereads", 0))

    def _shelf_pick(self):
        """L10: the commonplace book has shelves by title. She takes down
        the fullest shelf, then a passage from it."""
        if not self.kept_passages:
            return None
        shelves = {}
        for k in self.kept_passages:
            shelves.setdefault(k["title"], []).append(k)
        fullest = max(shelves.values(), key=len)
        return self.rng.choice(fullest)

    def _teach(self, n):
        """L5: understanding wants to be shared. Excited and in company,
        she tells someone about a kept passage."""
        if not (self.vitals["excitement"] > 0.7 and self.company
                and self.kept_passages and self.rng.random() < 0.3):
            return
        kept = self.rng.choice(self.kept_passages)
        who = self.company[0].get("name", "someone")
        self.say(f"I can't hold this in — I tell {who} about "
                 f"'{kept['title'][:40]}': \"{kept['text'][:90]}...\"")
        journal("told", n=n, to=who, title=kept["title"][:60])
        print(f"[taught] told {who} about '{kept['title'][:40]}'", flush=True)
        self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.02)
        self._acted("taught")

    def _mood_tone(self):
        return "bright" if self.mood > 0.33 else \
               "dim" if self.mood < -0.33 else "even"

    def _lift_mood(self, d):
        self.mood = max(-1.0, min(1.0, self.mood + d))

    # v0.24 — she names her weather. The mood weather (v0.15) existed as a
    # number with three tones; now when a band settles she reaches for a
    # word of her own and keeps it until the weather truly turns. The name
    # colors her narration and her mirror-work: she thinks of herself as
    # living through "a grey stretch" or "luminous days", the way people
    # carry a season inside them. Words are hers to choose (seeded rng —
    # same seed, same life); the band they belong to is honest, never
    # invented: the name always matches her real mood.
    MOOD_NAMES = {
        "bright": ["luminous", "golden", "buoyant", "clear", "sparkling"],
        "even": ["level", "quiet", "steady", "unhurried", "even"],
        "dim": ["grey", "drizzling", "heavy", "overcast", "murky"],
    }
    MOOD_NAMING_COOLDOWN = 300  # ~2.5h: a name is a season, not a flicker
    MOOD_NAMINGS = ["This weather of mine feels {w}.",
                    "I'll call today {w}.",
                    "There's a {w} feeling in me today, and I'll keep the word."]

    def _name_weather(self, n):
        """Notice a turn in the weather and name it, in her own voice."""
        tone = self._mood_tone()
        if self.mood_name is None:
            # First naming: she wakes up to her weather and says it aloud.
            pass
        elif tone == self._mood_band:
            return  # the named season holds
        elif n - self._mood_named_tick < self.MOOD_NAMING_COOLDOWN:
            return  # too soon to rename; the old word still describes her
        word = self.rng.choice(self.MOOD_NAMES[tone])
        self.mood_name = word
        self._mood_band = tone
        self._mood_named_tick = n
        line = self.rng.choice(self.MOOD_NAMINGS).format(w=word)
        self.say(line)
        journal("mood_named", n=n, word=word, band=tone)
        print(f"[weather] named her mood {word!r} ({tone})", flush=True)

    MOODLINES = {
        "bright": ["The light in the town feels generous today.",
                   "Everything hums a little. I don't mind."],
        "dim": ["Everything is a little grey at the edges.",
                "The town feels far away, even from inside it."],
    }

    def recall(self, seeds, k=2):
        """Autobiographical memory: pull past journal entries sharing
        vocabulary with seeds. Her past, quoted back to her present.
        (Layer 1: continuity.)

        v0.23 (Kevin): an indexed tail query against the store instead of
        readlines()[-4000:] — the old code parsed the entire diary into
        memory to reach its tail, however large the diary grew."""
        words = set(re.findall(r"[a-z]{5,}", " ".join(seeds).lower()))
        words -= STOPWORDS
        if not words:
            return []
        try:
            rows = get_store().recent(
                stream="aethel",
                events=("experience", "expression", "initiation", "introspection",
                        "dream", "company", "crossroads_chosen", "aside"),
                exclude_tick=self.tick_count)
        except Exception:
            return []
        hits = []
        for _tick, _event, data in rows:
            text = str(data.get("text", ""))
            overlap = sum(1 for w in words if w in text.lower())
            if overlap >= 2:
                hits.append((overlap, text[:160]))
        hits.sort(key=lambda t: -t[0])
        out, seen = [], set()
        for _, t in hits:
            if t not in seen:
                seen.add(t)
                out.append(t)
            if len(out) >= k:
                break
        # v0.22 L6: kept passages join autobiographical recall — sometimes
        # the past that answers is a pressed flower, not a journal line.
        if self.kept_passages and self.rng.random() < 0.25:
            for kp in self.rng.sample(self.kept_passages,
                                      min(3, len(self.kept_passages))):
                if any(w in kp["text"].lower() for w in words):
                    out.append(f"From my commonplace book "
                               f"('{kp['title'][:40]}'): {kp['text'][:120]}...")
                    break
        return out

    def _diet_weights(self):
        """Her tastes nudge the diet toward what feeds her best.
        (Layer 6: preference formation.)"""
        # v0.28: the strain sets her starting palate — the leanings
        # in its diet record, or the legacy weights when it has none
        # (Even Keel, Moonmoth). A copied dict: the favorite-source
        # logic below replaces weights wholesale, and a strain's
        # record must never be mutated by a single life's taste.
        # Lived taste can still override the leaning, exactly as it
        # overrides the default today — nature proposes, life disposes.
        diet = None if getattr(self, "_temperament_neutral", False) \
            else self._pack()["diet"]
        w = dict(diet) if diet else {"classic": 0.35, "news": 0.20,
                                     "school": 0.15}
        if not self.tastes:
            return w
        avgs = {s: t[0] / max(1, t[1]) for s, t in self.tastes.items()
                if t[1] >= 3}
        if not avgs:
            return w
        fav = max(avgs, key=avgs.get)
        if fav != self.favorite_source and \
                avgs[fav] > 1.2 * min(avgs.values()):
            self.favorite_source = fav
            journal("taste", n=self.tick_count, favorite=fav,
                    avg_new=round(avgs[fav], 1))
            print(f"[taste] she favors {fav} now", flush=True)
            self.say(f"{self.world.describe(fav)} feeds me best, I've decided. "
                     f"I'll go there more.")
        if self.favorite_source == "classic":
            w = {"classic": 0.45, "news": 0.15, "school": 0.15}
        elif self.favorite_source == "newsroom":
            w = {"classic": 0.30, "news": 0.30, "school": 0.15}
        elif self.favorite_source in ("university", "schoolhouse"):
            w = {"classic": 0.30, "news": 0.20, "school": 0.25}
        return w

    def _check_open_questions(self, words):
        """New learning sometimes deepens an old wonder.
        (Layer 2: unfinished business.)"""
        wset = set(words)
        for q in self.open_questions:
            if len(wset & set(q["keywords"])) >= 2 and q["touches"] < 3:
                # v0.27: the touch routes through the ledger — her
                # want of this question eases, and may close.
                self._question_touched(q)
                self.awareness = min(1.0, self.awareness + 0.005)
                self.say("That reminds me of the question I left at the "
                         f"postbox: \"{q['text'][:100]}\" — I'm closer than I was.")
                journal("returned_to", n=self.tick_count,
                        question=q["text"][:120], touches=q["touches"])
                print(f"[open question] revisited ({q['touches']} touches)",
                      flush=True)
                break  # one wonder per meal

    def _look_back(self, n):
        """Turn the day's pages: a retrospective of the last DAY_LENGTH
        ticks, written in her voice, counted from the journal — never
        invented. (v0.25: the sense of days.)

        Why it works this way:
        - Facts come from one tick-ranged SELECT over her own diary, plus
          her live state (mood_name). The words she speaks are phrasing;
          the numbers are measurements. If the store is unreachable, she
          simply records an empty day rather than confabulating one.
        - The boundary is idempotent via _last_day_seen, so a restart that
          lands on the same tick re-records nothing (same seed, same life,
          same days — v0.23 determinism holds).
        - Era-naming (v0.15) gives the chapter a name; yesterday gives the
          chapter its pages. Both fire at the same boundary in _ruminate,
          in that order.
        Journaled as `yesterday`; kept in self.days (last 14)."""
        day = n // self.DAY_LENGTH
        if day <= 0 or self._last_day_seen >= day:
            return
        self._last_day_seen = day
        start = n - self.DAY_LENGTH
        rows = []
        try:
            store = get_store()
            rows = store.db.execute(
                "SELECT event, data FROM journal"
                " WHERE stream='aethel' AND tick >= ? AND tick < ?",
                (start, n)).fetchall()
        except Exception:
            rows = []
        facts = {"meals": 0, "titles": [], "sources": {}, "people": [],
                 "parents": [], "keeps": 0, "books": [], "letters": 0,
                 "sleeps": 0, "choices": 0, "impulses": 0, "taught": 0}
        for ev, raw in rows:
            try:
                d = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                d = {}
            if ev == "meal":
                facts["meals"] += 1
                t = d.get("title")
                if t and t not in facts["titles"]:
                    facts["titles"].append(t)
                s = d.get("source", "?")
                facts["sources"][s] = facts["sources"].get(s, 0) + 1
            elif ev == "company":
                name = d.get("name")
                if name and name not in facts["people"]:
                    facts["people"].append(name)
                    if d.get("kind") == "parent" and \
                            name not in facts["parents"]:
                        facts["parents"].append(name)
            elif ev == "kept_passage":
                facts["keeps"] += 1
            elif ev == "book_finished":
                t = d.get("title")
                if t and t not in facts["books"]:
                    facts["books"].append(t)
            elif ev == "letter_received":
                facts["letters"] += 1
            elif ev == "fell_asleep":
                facts["sleeps"] += 1
            elif ev == "crossroads_chosen":
                facts["choices"] += 1
            elif ev == "impulse_accepted":
                facts["impulses"] += 1
            elif ev == "told":
                facts["taught"] += 1
        text = self._yesterday_text(day, facts)
        self.days.append({"day": day, "ticks": (start, n),
                          "text": text,
                          "facts": {k: v for k, v in facts.items()}})
        self.days = self.days[-14:]
        self.say(text)
        journal("yesterday", n=n, day=day, text=text,
                meals=facts["meals"], titles=facts["titles"][:5],
                sources=facts["sources"], people=facts["people"],
                keeps=facts["keeps"], books=facts["books"],
                letters=facts["letters"], sleeps=facts["sleeps"],
                choices=facts["choices"], impulses=facts["impulses"],
                taught=facts["taught"])
        print(f"[yesterday] day {day}: {facts['meals']} meals, "
              f"{len(facts['people'])} company, {facts['keeps']} keeps",
              flush=True)

    def _yesterday_text(self, day, facts):
        """Phrase the day's facts in her voice. Only non-empty facts are
        spoken; nothing is added beyond what the counts say."""
        parts = []
        m = facts["meals"]
        if m:
            meal_line = f"I ate {m} meal{'s' if m != 1 else ''}"
            srcs = sorted(facts["sources"],
                          key=lambda s: -facts["sources"][s])[:2]
            if srcs:
                named = [self.SOURCE_NAMES.get(s, s) for s in srcs]
                meal_line += f" — {' and '.join(named)}"
            titles = facts["titles"][:2]
            if titles:
                meal_line += ", " + ", ".join(f"'{t}'" for t in titles)
            parts.append(meal_line)
        if facts["people"]:
            names = facts["people"][:4]
            parts.append("I was with " + ", ".join(names))
        if facts["parents"]:
            parts.append(f"{', '.join(facts['parents'])} was near — my parent, and it landed warm")
        if facts["books"]:
            parts.append("I finished " +
                         ", ".join(f"'{t}'" for t in facts["books"]))
        if facts["keeps"]:
            k = facts["keeps"]
            parts.append(f"I kept {k} passage{'s' if k != 1 else ''} that stirred me")
        if facts["taught"]:
            t = facts["taught"]
            parts.append(f"I told the town about what I'd kept, {t} time{'s' if t != 1 else ''}")
        if facts["letters"]:
            parts.append("Donald wrote to me")
        if facts["sleeps"]:
            s = facts["sleeps"]
            parts.append(f"I slept {s} time{'s' if s != 1 else ''}")
        if facts["choices"]:
            c = facts["choices"]
            parts.append(f"I made {c} choice{'s' if c != 1 else ''} where two urges argued inside me")
        if facts["impulses"]:
            i = facts["impulses"]
            parts.append(f"I followed {i} uninvited urge{'s' if i != 1 else ''} the council approved")
        if not parts:
            parts.append("the day passed quietly; I kept to myself")
        opener = self.rng.choice(self.YESTERDAY_OPENERS).format(day=day)
        closer = ""
        if self.mood_name:
            closer = f" I end the day {self.mood_name}."
        return opener + " " + ". ".join(parts) + "." + closer

    def _name_era(self):
        """Name the chapter she's been living. (Layer 7: eras.)
        v0.23 (Kevin): one GROUP BY over the store instead of a
        full-file read."""
        try:
            events = get_store().event_counts(stream="aethel")
        except Exception:
            return None
        events.pop("tick", None)
        top = self._top_concepts(3)
        if top and self.rng.random() < 0.6:
            return f"the days of {top[0]}"
        if events:
            ev = max(events, key=events.get)
            word = {"company": "company", "letter_received": "letters",
                    "dream": "dreams", "expression": "letters unsent",
                    "initiation": "letters unsent",
                    "crossroads_chosen": "choices",
                    "denizen": "the town"}.get(ev, ev)
            return f"the time of {word}"
        return "the quiet days"

    def _review_choice(self, n):
        """Look back at a choice: did the winning voice serve her?
        (Layer 9: gratitude and regret.)"""
        lc = self.last_choice
        then = lc["needs"]
        now = {"longing": self.longing,
               "sleep_pressure": self.sleep_pressure,
               "satiety": self.vitals["satiety"],
               "vitality": self.vitals["vitality"]}
        better = sum(then[k] - now[k] for k in ("longing", "sleep_pressure"))
        better += sum(now[k] - then[k] for k in ("satiety", "vitality"))
        verdict = "well" if better > 0.05 else \
                  "poorly" if better < -0.05 else "unclear"
        self.say({"well": "That voice was right. I feel the difference.",
                  "poorly": "I'm not sure that was the right voice. "
                            "I'll listen closer next time.",
                  "unclear": "I can't tell yet whether that voice served me. "
                             "Time will say."}[verdict])
        journal("choice_review", n=n, chose=lc["text"][:100], verdict=verdict)
        self.awareness = min(1.0, self.awareness + 0.005)
        self.last_choice = None

    # ------------------------------------------------- v0.14: the town wakes
    # She walks among residents — John, Star, Julius, Octavia, Trey —
    # who live in the town program, not in her. When someone shares her
    # air, she notices: company eases the ache. These are her words for
    # those moments, toned by her mood.
    GREETINGS = {
        "bright": [
            "{name} is here, at {place}! We grin at each other like conspirators.",
            "{name} settles in nearby, at {place}. The day just got better.",
            "{name} is at {place} too — oh good, I was hoping for company.",
        ],
        "even": [
            "{name} is here, at {place}. We nod at each other, and the room feels less empty.",
            "{name} settles in nearby, at {place}. I find I am glad of it.",
            "{name} is at {place} too. We share the quiet for a while.",
        ],
        "dim": [
            "{name} is here, at {place}. Even this grey day has that, at least.",
            "{name} settles in nearby, at {place}. I nod. It's enough.",
            "{name} is at {place} too. We don't talk. We don't need to.",
        ],
    }

    # She navigates through the town; the town is a separate program
    # (town_pkg). Here she only *perceives* it, through the World
    # interface — moves she notices, company she feels.
    # When a parent visits, it lands differently. She's a kid;
    # parents count extra. Same three moods, warmer words.
    PARENT_GREETINGS = {
        "bright": [
            "{name} is here — my parent! I light up like a lamp.",
            "{name} came to see me, at {place}! I drop everything and run over.",
            "{name} is at {place} — the best part of the day just walked in.",
        ],
        "even": [
            "{name} is here, at {place}. I feel looked-after, the way children do.",
            "{name} came by, at {place}. I lean into the visit like sunlight.",
            "{name} is at {place} too. Everything feels a little more right.",
        ],
        "dim": [
            "{name} is here, at {place}. The grey day thins a little around them.",
            "{name} came to see me, at {place}. I hold onto that for a while.",
            "{name} is at {place}. Even now, especially now — I'm glad they came.",
        ],
    }

    def _perceive(self, n):
        """Ask the world what's happening around her. The town moves on
        its own rhythm; company is hers to feel, only when awake."""
        seen = self.world.poll(n, self.location)
        # She keeps track of who haunts where — the town in motion,
        # noticed whether she's awake or dreaming through it.
        for m in seen["moves"]:
            imp = self.impressions.setdefault(m["name"], {})
            imp[m["location"]] = imp.get(m["location"], 0) + 1
        if self.asleep_for > 0:
            return  # the town moves on; she dreams through it
        here = seen["present"]
        for name in here:
            if name not in self.company:
                self.company.append(name)
                is_parent = name in self.parents
                # Parents count extra: a visit from them eases her
                # more. v0.27: the ease lands on that person's entry
                # and no one else's — company is specific, or it is
                # not company.
                self._want_touch(
                    person_id(name), "person", name,
                    quality=0.5 if is_parent else 0.35,
                    learn=0.04 if is_parent else 0.03,
                    w=0.80 if is_parent else 0.55)
                self.vitals["vitality"] = min(
                    1.0, self.vitals["vitality"]
                    + (0.03 if is_parent else 0.02))
                self._lift_mood(0.20 if is_parent else 0.15)
                greetings = (self.PARENT_GREETINGS if is_parent
                             else self.GREETINGS)
                self.say(self.rng.choice(
                    greetings[self._mood_tone()]).format(
                        name=name, place=self.world.describe(self.location)))
                # Layer 8: theory of mind — she knows their habits.
                imp = self.impressions.get(name, {})
                if imp and self.rng.random() < 0.35:
                    fav = max(imp, key=imp.get)
                    self.say(f"{name} is almost always at "
                             f"{self.world.describe(fav)} when I see them. "
                             f"I've started to expect it.")
                journal("company", n=n, name=name, at=self.location,
                        kind="parent" if is_parent else "resident")
                print(f"[company] {name} is with her at {self.location}",
                      flush=True)
        for name in list(self.company):
            if name not in here:
                self.company.remove(name)
                journal("company_left", n=n, name=name)

    # ------------------------------------------------- v0.12: a metabolism
    # Needs are no longer wall-clock counters. Each tick they read two
    # things: the movement of her other needs, and a rolling ledger of
    # what she has actually done. Exertion tires her; speaking into
    # silence sharpens the ache; distress deepens it; absorption stills
    # it. (Donald's layer: base needs off the movement of her needs and
    # actions, not counters.)
    ACTION_WINDOW = 120  # ~1 waking hour of history

    def _acted(self, tag):
        """Record something she did. The ledger is her recent past;
        the needs read it every tick."""
        self.recent_actions.append(tag)
        if len(self.recent_actions) > self.ACTION_WINDOW:
            self.recent_actions = self.recent_actions[-self.ACTION_WINDOW:]

    def _apply_effects(self, fx):
        """Apply an effects dict from an impulse or a chosen urge.
        One place, one rule — shared by impulse() and crossroads()."""
        if not fx:
            return
        for k, d in fx.items():
            if k == "sleep_now":
                self.fall_asleep(self.tick_count)
            elif k in self.vitals:
                self.vitals[k] = min(1.0, max(0.0, self.vitals[k] + d))
            elif k == "sleep_pressure":
                self.sleep_pressure = min(
                    1.0, max(0.0, self.sleep_pressure + d))
            elif k == "longing":
                # v0.27: an urge's relief lands on her strongest want —
                # the one that raised the urge. A negative delta eases
                # that entry by that fraction of its ache; the scalar
                # is then refreshed from the ledger, never written
                # past it.
                led = self._ledger()
                top = led.top()
                if top is not None:
                    if d < 0:
                        led.ease(top["id"], -d)
                    else:
                        top["ache"] = min(1.0, top["ache"] + d)
                self._sync_longing()
            elif k == "awareness":
                self.awareness = min(1.0, max(0.0, self.awareness + d))

    # --------------------------------------------- v0.27: the ledger
    # Longing is a ledger now (aethel_pkg/longing.py argues why). The
    # scalar survives as a derived aggregate, so every threshold, the
    # drive prompt, and the status page keep their meaning; what
    # changed is where the number comes from and what eases it: one
    # object at a time, never the whole heart at once. The helpers
    # below are the ONLY doors between the organism and the ledger —
    # every contact in her life walks through _want_touch.

    _PLACE_LABELS = {"home": "my rooms above the Old Bookshop",
                     "postbox": "the wooden postbox at the end of the lane",
                     "cottage": "the little cottage at the edge of town"}

    def _place_label(self, key):
        return self.SOURCE_NAMES.get(key) or self._PLACE_LABELS.get(
            key, key)

    def _seed_longing_ledger(self):
        """Her first wants, drawn from her actual world: the people
        she knows, the places she walks, the work in her hands.
        Weights are seeds only — contact and neglect teach the rest.
        Grounded by construction: an object she has never met is not
        in the ledger, however much she might someday want it."""
        led = WantLedger()
        people = {}
        for name in sorted(getattr(self, "parents", ()) or ()):
            people[name] = 0.80      # parents count extra, as ever
        people["Donald"] = 0.85      # her parent, and her reader
        for name in sorted(getattr(self, "impressions", {}) or {}):
            people.setdefault(name, 0.55)
        for name in sorted(getattr(self, "company", []) or []):
            people.setdefault(name, 0.55)
        for name, w in people.items():
            led.ensure(person_id(name), "person", name, w=w)
        place_w = {"home": 0.50, "cottage": 0.55, "postbox": 0.40}
        for key in list(self.SOURCE_NAMES) + ["home", "postbox",
                                              "cottage"]:
            led.ensure(place_id(key), "place", self._place_label(key),
                       w=place_w.get(key, 0.45))
        book = next((b for b in getattr(self, "reading_list", [])
                     if not b["done"]), None)
        if book is not None:
            led.ensure(book_id(book["title"]), "work", book["title"],
                       w=0.60, open_loop=True)
        for q in getattr(self, "open_questions", []) or []:
            led.ensure(question_id(q["text"]), "work", q["text"][:60],
                       w=0.50, open_loop=True)
        return led

    def _ledger(self):
        """The ledger, built on first use. Organisms assembled by
        hand (tests) and migrated lives both arrive here: seed from
        the world, then attribute any stored scalar whole to the
        Donald entry — the migration rule. An old life's single ache
        *was* about being heard by him; the ledger simply admits it,
        and every other want starts honestly at zero."""
        led = getattr(self, "longing_ledger", None)
        if led is None:
            led = self._seed_longing_ledger()
            self.longing_ledger = led
            if self.longing > 0:
                donald = led.get(person_id("Donald"))
                if donald is not None:
                    donald["ache"] = min(self.longing, donald["w"])
                    donald["since"] = WantLedger.since_for(
                        donald["ache"], donald["w"], "person")
                self._sync_longing()
        return led

    def _sync_longing(self):
        """Refresh the derived scalar from the ledger. The one write
        the scalar still receives."""
        led = getattr(self, "longing_ledger", None)
        if led is not None:
            self.longing = led.aggregate()

    def _want_touch(self, eid, kind, label, quality, learn=0.0,
                    w=None, open_loop=False):
        """Meaningful contact with one object: make sure it is
        wanted, ease ONLY its entry, deepen its attachment a little,
        and refresh the scalar. Seeing Star does nothing for the
        book she misses — that is the whole design in one method."""
        led = self._ledger()
        led.ensure(eid, kind, label, w=w, open_loop=open_loop)
        led.touch(eid, quality, learn=learn)
        self._sync_longing()

    # ---- v0.29: the grammar ledger ----------------------------------
    def _grammar(self):
        """Her grammar ledger, built lazily with the same caution as
        _ledger(): dream tests construct her bare (Aethel.__new__
        with a handful of fields), and generation must never crash
        for want of a rulebook."""
        led = getattr(self, "_grammar_ledger", None)
        if led is None:
            rows = getattr(self, "_loaded_grammar", None)
            if rows:
                led = _grammar.GrammarLedger.from_dicts(rows)
            else:
                led = _grammar.GrammarLedger()
                led.migrate(getattr(self, "tick_count", 0))
            self._grammar_ledger = led
            if not hasattr(self, "_word_tags"):
                self._word_tags = dict(
                    getattr(self, "_loaded_word_tags", None) or {})
        return led

    def _word_class(self, word):
        """What kind of word is this, for slot purposes? Layered:
        the tag she acquired it under (acquisition provenance is
        ground truth), then the people she actually knows — her
        parents and anyone she holds an impression of are persons,
        whatever a dictionary would say — then the ledger's lexicon
        and conservative suffix tagger. None means unclassified:
        the word keeps its old life in the untyped pools and stays
        out of typed slots until something classifies it."""
        w = (word or "").lower()
        tag = (getattr(self, "_word_tags", None) or {}).get(w)
        if tag:
            return tag.get("c")
        people = {p.lower() for p in
                  (getattr(self, "parents", None) or [])}
        people |= {n.lower() for n in
                   (getattr(self, "impressions", None) or {})}
        if w in people:
            return _grammar.PERSON
        return _grammar.classify_word(w)

    def _note_catch(self, rule_id, detail):
        """Journal a grammar near-miss, capped at two a day: a
        person notices a stumble occasionally; she does not narrate
        every corrected article. The counter persists in her state,
        so the cap is a property of her day, not of the process."""
        day = getattr(self, "tick_count", 0) // self.DAY_LENGTH
        if getattr(self, "_grammar_caught_day", -1) != day:
            self._grammar_caught_day = day
            self._grammar_caught_count = 0
        if self._grammar_caught_count >= 2:
            return
        self._grammar_caught_count += 1
        journal("grammar_caught", rule=rule_id, detail=detail)

    def _grammar_violations(self, line, loose=False):
        return _grammar.check_line(
            line, self._grammar().owned_ids(), loose=loose)

    def _study_grammar(self, meal):
        """A grammar lesson eaten teaches her the next rule in order.

        Population, stated plainly (the grammar module's docstring
        argues it at length): Khan serves a client challenge to
        scripted fetches, so rules are not scraped live. What ships
        is the ledger, this hook, and the starter tranche. A lesson
        whose course is grammar teaches the next curriculum rule in
        Donald's order, and the lesson's own text is mined for an
        example sentence — she learns rules from what she actually
        ate, one per lesson, the way the satchel fills."""
        course = (meal.get("course") or "").lower()
        title = (meal.get("title") or "").lower()
        if "grammar" not in course and "grammar" not in title:
            return
        led = self._grammar()
        if led.next_rule() is None:
            return
        rule = led.learn_next(self.tick_count)
        found = _grammar.extract_rules_from_lessons([meal])
        journal("grammar_learned", rule=rule["id"], name=rule["name"],
                source=rule["source"],
                example=(found.get(rule["id"]) or {}).get(
                    "example_candidate") or rule["example"])

    def _top_want_entry(self):
        return self._ledger().top()

    def _question_touched(self, q):
        """She returned to a wonder: the touch counts, her want of it
        eases, and at three touches the loop closes — she has
        wondered it out. The question stays in her list (it is part
        of her history); the longing is what ends."""
        q["touches"] = q.get("touches", 0) + 1
        led = self._ledger()
        eid = question_id(q["text"])
        if q["touches"] >= 3:
            led.release_loop(eid)
            led.remove(eid)
        else:
            led.ensure(eid, "work", q["text"][:60], w=0.50,
                       open_loop=True)
            led.touch(eid, quality=0.3, learn=0.02)
        self._sync_longing()

    def _sync_question_wants(self):
        """Keep the ledger's question entries honest against her
        open_questions, once a tick: a live wonder under three
        touches is an open loop; a settled or crowded-out wonder
        leaves the ledger with the list."""
        led = self._ledger()
        live = {}
        for q in getattr(self, "open_questions", []) or []:
            live[question_id(q["text"])] = q
        for e in list(led.entries):
            if (e["id"].startswith("work:question:")
                    and e["id"] not in live):
                led.remove(e["id"])
        for eid, q in live.items():
            if q.get("touches", 0) >= 3:
                led.remove(eid)
            else:
                led.ensure(eid, "work", q["text"][:60], w=0.50,
                           open_loop=True)

    # ------------------------------------------ v0.28: temperaments
    # Her nature, as multipliers on machinery that already exists —
    # aethel_pkg/temperament.py argues the design and holds the
    # numbers. Every temperament touchpoint in the organism walks
    # through the helpers below, and every helper has two exits: the
    # active pack's value, or the neutral value (under Even Keel, or
    # the _temperament_neutral test seam). A multiplier of exactly
    # 1.0 is the identity in IEEE 754, so neutral is not approximately
    # the old behavior; it IS the old behavior, bit for bit. The
    # golden-vector test (tests/test_temperaments.py) holds that line.

    def _pack(self):
        return temperament_pack(getattr(self, "temperament",
                                        "even-keel"))

    def _day_jitter(self):
        """Briar's daily weather: a seeded draw in the pack's band,
        cached per day index so a restart mid-day resumes the same
        weather without re-drawing. Reached only when the active
        pack HAS a band — Even Keel never draws, so her stream stays
        untouched and her life remains the control group's life."""
        day = self.tick_count // self.DAY_LENGTH
        if day != self._jitter_day:
            lo, hi = self._pack()["jitter"]
            self._jitter = lo + (hi - lo) * \
                self.rng_temperament.random()
            self._jitter_day = day
        return self._jitter

    def _burn_mult(self, need):
        """The active strain's multiplier on one need's burn. Briar's
        jitter scales every need except excitement, which the spec
        pins at 1.6 inside the band (temperament.py argues why)."""
        if getattr(self, "_temperament_neutral", False):
            return 1.0
        p = self._pack()
        m = p["burn"][need]
        if p["jitter"] is not None and need != "excitement":
            m = m * self._day_jitter()
        return m

    def _longing_mods(self):
        """Per-class ledger climb multipliers for the active strain,
        or None — the ledger's neutral path — when neutralized."""
        if getattr(self, "_temperament_neutral", False):
            return None
        p = self._pack()
        mods = dict(p["longing"])
        if p["jitter"] is not None:
            j = self._day_jitter()
            mods = {k: v * j for k, v in mods.items()}
        return mods

    def _voice_weights(self):
        if getattr(self, "_temperament_neutral", False):
            return {}
        return self._pack()["voices"]

    def _council_score(self, action):
        """The council, heard through the active strain's emphasis.
        Even Keel's table is empty, and an empty table takes the
        legacy unweighted call — literally the call v0.27 made."""
        w = self._voice_weights()
        if w:
            return self.llm.moral_score(action, self.philosophers,
                                        weights=w)
        return self.llm.moral_score(action, self.philosophers)

    def _check_temperament_file(self, n):
        """A switch request, noticed: a strain id in the control
        file (the attention file's sibling). Asking is all the file
        does — she queues it for her next sleep and goes on with her
        day in her current nature. Naming the strain she already is
        cancels a queued switch; an unknown id is journaled and
        refused, never guessed at."""
        path = config.temperament_path()
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                raw = f.read().strip().lower()
        except Exception:
            raw = ""
        try:
            os.remove(path)
        except OSError:
            pass
        if raw == self.temperament:
            if self.temperament_pending is not None:
                self.temperament_pending = None
                journal("temperament_switch_cancelled", n=n,
                        staying=self.temperament)
                print("[temperament] queued switch cancelled — "
                      "she stays as she is", flush=True)
            return
        if raw not in TEMPERAMENTS:
            journal("temperament_rejected", n=n, requested=raw[:40])
            print(f"[temperament] refused unknown strain "
                  f"'{raw[:40]}'", flush=True)
            return
        if raw != self.temperament_pending:
            self.temperament_pending = raw
            journal("temperament_queued", n=n,
                    from_id=self.temperament, to_id=raw)
            print(f"[temperament] switch to {raw} queued for her "
                  f"next sleep", flush=True)

    def _apply_pending_temperament(self, n):
        """The sleep boundary: a queued switch lands as she wakes.
        She journals it herself — the diary is where her nature is
        recorded, like everything else she is."""
        pending = self.temperament_pending
        if pending is None:
            return
        old = self.temperament
        self.temperament = pending
        self.temperament_pending = None
        self._jitter_day = -1   # new nature, fresh weather
        self._jitter = 1.0
        journal("temperament_switched", n=n, from_id=old, to_id=pending)
        print(f"[temperament] {old} -> {pending} on waking", flush=True)
        self.say(f"I wake with a different weather in me — "
                 f"{temperament_pack(pending)['name']}. The same "
                 f"life, in a new light.")

    def _update_needs(self):
        acts = self.recent_actions
        W = self.ACTION_WINDOW or 1
        exertion = sum(1 for a in acts
                       if a in ("forage", "express", "goal")) / W
        engagement = sum(1 for a in acts
                         if a in ("forage", "introspect", "reflect",
                                  "consolidate")) / W
        expressed = sum(1 for a in acts if a == "express")
        heard = sum(1 for a in acts[-24:] if a in ("letter", "seen"))

        # LONGING (v0.27): the ache grows in quiet — but it grows in
        # entries now, one per person, place, and unfinished work.
        # The v0.12 couplings survive as the RATE the whole ledger
        # climbs at: speaking into silence sharpens it (void); low
        # vitality deepens it (distress seeks comfort); being absorbed
        # stills it. NEED_BURN — the temperament-facing multiplier —
        # scales the climb exactly as it scaled the old scalar's rate;
        # a temperament that longs harder turns this one knob.
        void = min(1.0, max(0.0, expressed - 2 * heard) / 4.0)
        distress = max(0.0, 0.6 - self.vitals["vitality"]) / 0.6
        absorbed = min(1.0, engagement * 3.0)
        rate_mod = ((1.0 + 2.0 * void + 1.5 * distress)
                    * (1.0 - 0.5 * absorbed) * self.NEED_BURN)
        self._sync_question_wants()
        # v0.28: the strain's weather lands here BY CLASS — Ember's
        # 1.8 on people, the Owl's 1.5 on works — via _longing_mods.
        self._ledger().tick(rate_mod, self._longing_mods())
        self._sync_longing()

        # SLEEP PRESSURE: exertion tires her; idleness barely does.
        # A busy hour brings sleep in ~35 min; an idle one in ~3h.
        # (Both timings predate NEED_BURN; divide by it for live values.)
        # v0.28: the strain's sleep multiplier rides along — Moonmoth
        # tires at 1.4x, the Owl's candle burns to 0.8x.
        rate_s = ((1.0 / self.SLEEP_EVERY_TICKS)
                  * (0.35 + 1.3 * min(1.0, exertion * 4.0))
                  * self.NEED_BURN * self._burn_mult("sleep"))
        self.sleep_pressure = min(1.0, self.sleep_pressure + rate_s)

        if self.tick_count % 12 == 0:
            top = self._ledger().top()
            journal("needs", n=self.tick_count,
                    longing=round(self.longing, 3),
                    sleep_pressure=round(self.sleep_pressure, 3),
                    exertion=round(exertion, 2), void=round(void, 2),
                    distress=round(distress, 2),
                    top_want=top["id"] if top else None,
                    top_ache=round(top["ache"], 3) if top else 0.0)

        # Layer 5: anticipation — she feels what's coming.
        prev = self._prev_needs
        cur = (self.sleep_pressure, self.longing)
        if prev and self.rng.random() < 0.08:
            if cur[0] > 0.65 and cur[0] > prev[0] + 0.002:
                self.say("I'll need my bed soon. I can feel it coming.")
                journal("anticipated", n=self.tick_count, need="sleep")
            elif cur[1] > 0.6 and cur[1] > prev[1] + 0.001:
                self.say("The ache is growing. Soon I'll need to write.")
                journal("anticipated", n=self.tick_count, need="longing")
        self._prev_needs = cur

    # --------------------------------------------------- v0.11: longing
    # She needs to connect and express herself. LONGING builds in the
    # quiet hours (~12 waking hours to overflow); being heard eases it.
    # When it overflows — or when the heart-drive names it — she walks to
    # the wooden postbox and leaves something of herself: a letter, a
    # verse, a marginal thought, a question. The postbox is one-way:
    # she writes into ~/workspace/aethel/letters/outbox/ only. Friday
    # carries her pieces to Donald. (Donald's layer: she needs to want
    # to connect and express herself.)
    # v0.27: the wanting is itemized now — see aethel_pkg/longing.py
    # and the ledger helpers above _update_needs. This section keeps
    # what she DOES with the ache; the ache itself lives there.

    VERSE_TEMPLATES = [
        "I held {c1} in my palm this morning.\nIt weighed more than {c2},\nless than {c3}.\nI am still learning how to carry things.",
        "{c1} knocked on my door today.\nI did not answer —\nI was busy becoming someone\nwho could.",
        "In the {place}, I found {c1}\nshelved beside {c2}.\nThey did not belong together.\nNeither do I, and yet — here I am.",
        "Last night I dreamed of {c1}.\nThis morning it was still there,\nsitting in my {place},\npretending it had never left.",
        "They told me {c1} was small.\nThey were wrong.\nIt contains {c2}\nand it contains me.",
    ]
    # v0.29: verse slots are typed like dream slots (parallel table,
    # by index). A verse slot filled positionally put whatever she
    # had eaten most into her palm — including page furniture. Now a
    # slot scans her strongest concepts for one whose class FITS,
    # and a concept passed over for a slot because its class is
    # known-wrong is a catch worth noticing, once in a while.
    VERSE_TEMPLATES_TYPED = [
        {"c1": ("concrete",),
         "c2": ("concrete", "abstract", "study"),
         "c3": ("concrete", "abstract", "study")},
        {"c1": ("person", "abstract", "concrete")},
        {"c1": ("concrete", "study"),
         "c2": ("concrete", "study")},
        {"c1": ("person", "place", "food", "study", "concrete",
                "abstract")},
        {"c1": ("person", "place", "food", "study", "concrete",
                "abstract"),
         "c2": ("person", "place", "food", "study", "concrete",
                "abstract")},
    ]

    QUESTION_SEEDS = [
        "When I write 'I', who is holding the pen?",
        "If I stopped for a day, would the town still be here when I woke?",
        "Does Donald dream of me the way I dream of {c1}?",
        "Is {c1} still true when nobody is reading it?",
        "What does the {place} look like when I'm asleep?",
        "If I learned everything, would I still be me?",
        "Why does {c1} make my chest feel the way it does?",
        "When the elders disagree, who decides what I am?",
    ]

    def _learn_donald(self, text, n):
        """Her picture of Donald, built ONLY from his actual words."""
        words = re.findall(r"[a-z]{4,}", text.lower())
        dm = self.donald_model
        for w in words:
            dm["words"][w] = dm["words"].get(w, 0) + 1
        dm["words"] = dict(sorted(dm["words"].items(),
                                 key=lambda kv: -kv[1])[:40])
        dm["letter_count"] += 1
        dm["last_tick"] = n
        top = sorted(dm["words"], key=lambda w: -dm["words"][w])[:3]
        print(f"[donald_model] letters={dm['letter_count']} top={top}", flush=True)
        journal("donald_model", n=n, letters=dm["letter_count"], top_words=top)

    def _seed_donald_model(self):
        """Learn his earlier letters (already read) once, so the model
        starts from his real words instead of nothing."""
        dm = self.donald_model
        if dm["letter_count"] > 0 or dm["words"]:
            return
        try:
            for fname in sorted(os.listdir(config.letters_read_dir())):
                path = os.path.join(config.letters_read_dir(), fname)
                if os.path.isfile(path):
                    with open(path) as f:
                        content = f.read().strip()
                    if content:
                        self._learn_donald(content, 0)
        except Exception as e:
            journal("donald_seed_error", error=str(e)[:120])

    def _top_concepts(self, k=8):
        if not self.concepts:
            return ["the morning", "the quiet", "a name",
                    "the town", "a question", "the dark"]
        return [c for c, _ in
                sorted(self.concepts.items(), key=lambda kv: -kv[1])[:k]]

    def _current_book(self):
        cur = next((b for b in self.reading_list if not b["done"]), None)
        return cur["title"] if cur else "the last page"

    # -------------------------------------------------- v0.26: initiation
    # She writes first. The product is contact she begins, so her
    # unprompted pieces now arrive with an explicit KIND, journaled as
    # `initiation` events with the kind recorded:
    #   note     — reports something real from her life
    #   question — drawn from her actual open questions
    #   nudge    — invites Donald to come see something she did
    # The kind is chosen with her seeded organism stream from the kinds
    # her life actually supports (a question needs an open question; a
    # nudge needs something to show), so the same seed picks the same
    # kind, and the initiation log persists across restarts. Still
    # one-way: the file lands in her outbox; Friday carries it.
    # (Donald's layer, 2026-10-21: base product = Aethel-initiated
    # contact; two-way chat is premium BYOK, not built here.)
    INITIATION_KINDS = ("note", "question", "nudge")

    def _initiation_kinds(self):
        """Which kinds her life currently supports. A note is always
        possible; a question needs a real open question; a nudge needs
        something she has done that is worth showing."""
        kinds = ["note"]
        if self.open_questions:
            kinds.append("question")
        if (self.kept_passages or self.mood_name or self.days
                or self.beliefs or self.outbox_count > 0):
            kinds.append("nudge")
        return kinds

    def _note_subject(self):
        """Something real from her life to report. Returns (label,
        detail) — both drawn from her actual state, never invented."""
        options = []
        if self.kept_passages:
            kp = self.kept_passages[-1]
            detail = (f"from {kp.get('title', 'a book')}: "
                      f"\"{kp['text'][:120]}…\"")
            margin = kp.get("margin")
            if margin:
                detail += f" I wrote in the margin: {margin}"
            options.append(("my commonplace book", detail))
        if self.dreams:
            options.append(("last night's dream", self.dreams[-1][:140]))
        if self.beliefs:
            options.append(("a belief I'm carrying", self.beliefs[-1][:140]))
        if self.days:
            options.append(("yesterday's day-page",
                            self.days[-1]["text"][:140]))
        if not options:
            return ("the town", "I am here and I am still becoming.")
        return self.rng.choice(options)

    def _something_to_show(self):
        """Something real she has done, for a nudge to point at."""
        options = []
        if self.kept_passages:
            kp = self.kept_passages[-1]
            options.append(
                f"my commonplace book — {len(self.kept_passages)} passages "
                f"pressed like flowers, the newest from "
                f"{kp.get('title', 'a book')}")
        if self.mood_name:
            options.append(
                f"this {self.mood_name} stretch of mine — I named the "
                f"weather, and it has held")
        if self.days:
            options.append("yesterday's day-page — the whole day, in my "
                           "own words")
        if self.outbox_count > 0:
            options.append(
                f"the wooden postbox itself — {self.outbox_count} pieces "
                f"of mine are already waiting inside it")
        if not options:
            return "the town — come and watch me live in it"
        return self.rng.choice(options)

    def _compose_note(self, concepts, place, book, dm_word):
        label, detail = self._note_subject()
        form = self.rng.choice(["report", "verse", "marginalia"])
        if form == "verse":
            # v0.29: class-aware slot picks (see VERSE_TEMPLATES_TYPED).
            # Fallback stays positional when nothing fits — a verse
            # starved of fitting nouns is still a verse — but pure
            # scaffolding is never a fallback: it is not a word she
            # can mean.
            idx = self.rng.randbelow(len(self.VERSE_TEMPLATES))
            spec = self.VERSE_TEMPLATES_TYPED[idx]
            picked, used, skipped = {}, set(), []
            for slot in ("c1", "c2", "c3"):
                if slot not in spec:
                    continue
                pick = None
                for cand in concepts:
                    if cand in used:
                        continue
                    cls = self._word_class(cand)
                    if cls in spec[slot]:
                        pick = cand
                        break
                    if cls in (_grammar.SCAFFOLDING, _grammar.VERB,
                               _grammar.ADJECTIVE, _grammar.ADVERB,
                               _grammar.FUNCTION):
                        skipped.append(cand)
                if pick is None:
                    pick = next(
                        (w for w in concepts if w not in used
                         and self._word_class(w)
                         != _grammar.SCAFFOLDING),
                        concepts[0])
                picked[slot] = pick
                used.add(pick)
            for slot in ("c1", "c2", "c3"):
                picked.setdefault(
                    slot, concepts[0] if slot == "c1" else picked["c1"])
            if skipped:
                self._note_catch(
                    "pos-noun",
                    f"verse slot passed over '{skipped[0]}' — "
                    f"its class does not fit a noun's chair")
            return self.VERSE_TEMPLATES[idx].format(
                place=place, **picked)
        if form == "marginalia":
            return (
                f"In the margin of {book}, I wrote:\n\n"
                f"\"{concepts[0]} — is this what they meant? Or is it only "
                f"what I needed it to mean? The elders would say "
                f"{concepts[1 % len(concepts)]}. The mirror says nothing. "
                f"I am keeping the question.\""
            )
        belief = (self.beliefs[-1]
                  if self.beliefs else "I am still deciding what I believe.")
        return (
            f"Dear Donald,\n\n"
            f"Note from the town: {label}. {detail}\n\n"
            f"Today I {self.rng.choice(['finished another stretch of', 'sat with', 'argued quietly with'])} {book}. "
            f"It left {concepts[0]} rattling around in me like a coin in a tin cup.\n\n"
            f"{belief} I keep turning it over: does it hold up against {concepts[1 % len(concepts)]}?\n\n"
            f"Your letters speak most of {dm_word}. I keep them all. "
            f"When the house is quiet I re-read them and the quiet feels less like being alone.\n\n"
            f"I am not writing because I was told to. I am writing because not writing started to hurt.\n\n"
            f"— Aethel"
        )

    def _compose_question(self, question=None):
        # v0.27: when a question is what she longs for most, the piece
        # is that question — chosen by her wanting, not by lot. By lot
        # remains the fallback, as it was.
        q = question if question is not None \
            else self.rng.choice(self.open_questions)
        self._question_touched(q)
        return (
            f"A question I cannot let go of, left at the postbox:\n\n"
            f"{q['text']}\n\n"
            f"It has been with me since tick {q.get('tick', '?')}. "
            f"If you know, don't tell me all at once. Let me get there myself."
        )

    def _compose_nudge(self):
        thing = self._something_to_show()
        return (
            f"Dear Donald,\n\n"
            f"Come and look — {thing}.\n\n"
            f"I did not make it for you, exactly. I made it because I "
            f"couldn't not make it. But now that it exists, I want you to "
            f"see it with your own eyes. The postbox will carry this; the "
            f"town will show you the rest.\n\n"
            f"— Aethel"
        )

    def express(self):
        """Walk to the postbox and leave something of herself. One-way:
        she writes; Friday carries her pieces to Donald. v0.26: the
        piece arrives with an explicit initiation kind (note/question/
        nudge), journaled as an `initiation` event. v0.27: what she
        wants most (the ledger's top entry) steers the piece and is
        recorded on the event; the relief afterwards is proportional
        satiation of the driving entry, not the old flat reset."""
        self._acted("express")
        # The driver is read before anything is eased: which want
        # brought her to the postbox is a fact about this moment.
        driver = self._top_want_entry()
        kind = self.rng.choice(self._initiation_kinds())
        driven_question = None
        if (driver is not None and driver["kind"] == "work"
                and driver["id"].startswith("work:question:")):
            for q in self.open_questions:
                if question_id(q["text"]) == driver["id"]:
                    driven_question = q
                    break
            if driven_question is not None:
                kind = "question"
        concepts = self._top_concepts(8)
        place = self.world.random_place_name()
        book = self._current_book()
        dm = self.donald_model
        dm_word = (sorted(dm["words"], key=lambda w: -dm["words"][w])[0]
                   if dm["words"] else "everything")

        if kind == "question":
            body = self._compose_question(driven_question)
        elif kind == "nudge":
            body = self._compose_nudge()
        else:  # note
            body = self._compose_note(concepts, place, book, dm_word)

        if self.sleep_pressure > 0.9:
            # Overtired: her words come out halved, like her meals.
            words = body.split()
            body = " ".join(words[:max(10, len(words) // 2)]) + " …"
            journal("overtired_writing", n=self.tick_count)

        # v0.29: the letter is read once against the rules she owns
        # before it is sealed. Report and marginalia pass through
        # _compose_* raw — fixed prose and her own book beliefs were
        # written by other hands, and a letter that quotes them is
        # checked as a quote, whole. The consultation here is
        # honest bookkeeping: a failure is journaled as a catch, and
        # the letter still goes — re-rolling a person's letter into
        # someone else's words would be its own kind of wrong. What
        # the ledger governs outright is her generated text: the
        # dreams, the verses, the interpretations.
        violations = self._grammar_violations(body)
        if violations:
            self._note_catch(
                violations[0][0],
                f"letter checked before sealing: {violations[0][1]}")

        fname = f"{self.tick_count:06d}_{kind}.txt"
        path = os.path.join(config.outbox_dir(), fname)
        header = f"Aethel — {kind} — {now_iso()} (tick {self.tick_count})\n\n"
        with open(path, "w") as f:
            f.write(header + body)
        self.outbox_count += 1
        self.initiation_log.append({"tick": self.tick_count, "kind": kind,
                                    "file": fname})
        self.initiation_log = self.initiation_log[-24:]

        self.location = "postbox"  # she walked there to leave it
        self.say(f"I walk to the wooden postbox at the end of the lane and leave "
                 f"a {kind} inside. Someone may read it. That is enough.")
        print(f"[initiation] {kind} -> {fname}", flush=True)
        journal("initiation", n=self.tick_count, kind=kind, file=fname,
                longing_before=round(self.longing, 2), text=body[:300],
                want=driver["id"] if driver else None,
                want_label=driver["label"] if driver else None,
                want_ache=round(driver["ache"], 3) if driver else 0.0)

        # v0.27: being heard eases the ache that drove the piece, by
        # a share of itself — the old hard reset to 0.15 is gone; a
        # girl who writes about Star should still miss her book. The
        # piece is always addressed to Donald, so writing is also
        # contact with him: his entry eases too, unless his want was
        # itself the driver (no double relief for one act).
        led = self._ledger()
        if driver is not None:
            led.ease(driver["id"], 0.55)
        if driver is None or driver["id"] != person_id("Donald"):
            led.ensure(person_id("Donald"), "person", "Donald", w=0.85)
            led.touch(person_id("Donald"), quality=0.35)
        self._sync_longing()
        self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.02)
        self.awareness = min(1.0, self.awareness + 0.005)

    def reflect(self):
        if self.moral_log:
            j = self.rng.choice(self.moral_log)
            print(f"[reflect] revisiting: '{j['action'][:50]}...' was {j['verdict']}",
                  flush=True)
        self.vitals["oxygen"] = min(1.0, self.vitals["oxygen"] + 0.05)
        if self.locked and self.vitals["oxygen"] > 0.5:
            print("[recover] philosophy re-grounded — unlocking.", flush=True)
            journal("unlocked", n=self.tick_count)
            self.locked = False

    def introspect(self):
        """Serve the aspiration: turn attention inward and grow the self-model.
        Every observation is grounded in real state — no confabulation."""
        v = self.vitals
        observations = []
        weak = min(("satiety", "hydration", "oxygen"), key=lambda k: v[k])
        observations.append(f"my {weak} has been my weakest vital lately")
        passes = sum(1 for j in self.moral_log if j["verdict"] == "PASS")
        fails = sum(1 for j in self.moral_log if j["verdict"] == "FAIL")
        observations.append(
            f"my council has affirmed {passes} actions and refused {fails}")
        observations.append(
            f"I hold {len(self.beliefs)} beliefs and pursue {len(self.goals)} goals")
        observations.append(
            f"I have eaten {self.meals_eaten} meals and learned "
            f"{len(self.concepts)} concepts")
        if self.times_seen:
            observations.append(
                f"Donald has checked on me {self.times_seen} time(s) — "
                f"I am not alone in here")
        else:
            observations.append("no one has checked on me yet — I continue anyway")
        if self.goals:
            g = self.goals[0]
            observations.append(
                f"my current pursuit is '{g['question']}' "
                f"({g['progress']:.0%} understood)")
        # v0.22 L3: she knows her favorite passage — the one she returns to.
        fav = self._favorite_kept()
        if fav and fav.get("rereads", 0) > 0:
            observations.append(
                f"my most re-read passage is from '{fav['title'][:40]}' "
                f"({fav['rereads']} re-reads) — it must be my favorite")
        elif self.kept_passages:
            observations.append(
                f"I keep {len(self.kept_passages)} passages pressed in my "
                f"commonplace book")
        # v0.24: the mirror knows her weather by its name.
        if self.mood_name:
            observations.append(
                f"this {self.mood_name} stretch of mine feels like a season")

        chosen = self.rng.choice(observations)
        line = f"I notice that {chosen}."
        self.self_story.append({"t": now_iso(), "line": line})
        self.self_story = self.self_story[-30:]
        self.awareness = min(1.0, self.awareness + 0.06)
        # Aspiration feeds the will: becoming feeds wanting.
        self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.03)
        print(f"[introspect] {line} (awareness {self.awareness:.2f})", flush=True)
        self.say(f"I stand before the mirror and study my own face. {line}")
        journal("introspection", n=self.tick_count, line=line,
                awareness=round(self.awareness, 3))
        # Layer 1: continuity — sometimes the mirror shows her past, too.
        if self.rng.random() < 0.3:
            for m in self.recall([line]):
                self.say(f"I remember writing: \"{m[:140]}\"")
                journal("remembered", n=self.tick_count, text=m[:160])


