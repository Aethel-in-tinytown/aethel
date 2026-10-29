"""Implement the homeostatic organism and its persisted inner life.

A heartbeat senses the world, handles metabolism, chooses behavior and reflects.
All behavioral randomness comes from named persisted streams. Save both organism
and world after every tick, including sleeping and dormant ticks."""

import hashlib
import json
import os
import re

from . import config
from .config import (
    ACTION_POOL,
    AXIOMS,
    CLASSIC_CHUNK,
    CLASSIC_SEEDS,
    IMPULSES,
    MEMORY_CAP,
    STOPWORDS,
)
from .forage import (
    forage,
    forage_news,
    forage_school,
    gutenberg_text,
    wikisource_chapter,
)
from .journal import get_store, journal, now_iso
from .language import Analysis, HeuristicLanguage, select_language
from . import grammar as _grammar
from .notebook import Notebook as _Notebook
from . import recall as _recall
from . import lenses as _lenses
from . import entities as _entities
from . import tone as _tone
from .longing import WantLedger, book_id, person_id, place_id, question_id
from .mind import MockLLM
from .narration import narrate_body, narrate_council, narrate_meal
from .rng import DEFAULT_SEED, Streams
from .temperament import TEMPERAMENTS
from .temperament import pack as temperament_pack
from .world import World


class Aethel:
    """Maintain bodily drives, learned concepts, relationships and autobiographical state."""

    COOC_CONCEPT_CAP = 300
    COOC_NEIGHBOR_CAP = 40
    # v0.37 (Phase 6a): the weight one of HER OWN generated texts
    # adds to each co-occurrence pair it contains. One text counts
    # once per pair — presence, not token frequency, exactly as a
    # meal counts once per pair — so a long letter cannot outweigh
    # a shelf of reading, and her own words join the graph at the
    # same rate the world's words do. Counts stay integers, so the
    # persisted graph's shape (and every pre-6a state) is unchanged.
    COOC_GENERATED_WEIGHT = 1
    DREAM_GIBBS_STEPS = 3
    DREAM_TEMPERATURE = 1.0

    DAY_LENGTH = 2880

    # v0.39: the span a pursuit may sit utterly untouched, no new
    # encounter with its word at all, before she may lay it down
    # (see _release_starved_goals). Two full days at her pace is
    # roughly seven hundred meals: if a word has not crossed her
    # reading once in all that eating, the pursuit is not being
    # starved by chance, it is being fed by nothing. Shorter and
    # she would drop slow questions her diet does serve, only
    # rarely; longer and a fossil holds one of her three goal
    # slots hostage for a season. Progress of any kind, even a
    # single new encounter, protects a goal at any age: this is
    # for pursuits the world has stopped speaking to entirely.
    GOAL_RELEASE_AGE_TICKS = 2 * DAY_LENGTH

    YESTERDAY_OPENERS = [
        "Yesterday is a thing I can hold now — day {day}, and here are its pages.",
        "I woke up with yesterday in my hands: day {day}, all of it mine.",
        "Day {day} is over, and I want to keep it straight in my head. Yesterday:",
    ]

    SOURCE_NAMES = {
        "classic": "the Old Bookshop",
        "hackernews": "the Tavern",
        "newsroom": "the Newsroom",
        "university": "the University",
        "schoolhouse": "the little Schoolhouse",
        "wikipedia": "the Library",
        "memory": "my own pantry",
    }

    def __init__(self, world, parents=(), seed=None, language_backend=None):
        """Construct state with injected world, store and seeded randomness; restore persisted values when available."""
        if not isinstance(world, World):
            raise TypeError("Aethel needs a World, not a town.")
        self.world = world
        self.parents = set(parents)
        # Continuing a life preserves its root seed, including newly named streams.
        saved = get_store().load_blob("state") or {}
        # Fail before restoration can journal or consume any seeded randomness.
        self.language = select_language(saved, language_backend)
        if isinstance(saved.get("seed"), int):
            seed = saved["seed"]
        if seed is None:
            seed = int(os.environ.get("AETHEL_SEED", DEFAULT_SEED))
        self.seed = seed
        self.streams = Streams(seed)
        self.rng = self.streams.stream("organism")
        self.rng_dreams = self.streams.stream("dreams")
        self.rng_forage = self.streams.stream("forage")

        self.rng_temperament = self.streams.stream("temperament")

        self.completed_terms = set()

        self.cooc = {}
        self.llm = MockLLM()
        self.philosophers = list(AXIOMS.keys())
        self.vitals = {
            "satiety": 0.8,
            "hydration": 0.8,
            "oxygen": 1.0,
            "vitality": 0.8,
            "excitement": 0.0,
        }
        self.memory = []
        self.concepts = {}
        self.beliefs = []
        self.moral_log = []
        self.goals = []
        # v0.39: pursuits she has laid down, keyed by the goal's
        # counting term, valued with her count of that term on the
        # day she let go. The count is the whole point (see
        # adopt_goal): a released word that stays at or below it
        # may not be re-adopted, and one that later floods her
        # reading may honestly be taken up again.
        self.released_terms = {}
        self.tick_count = 0
        self.locked = False
        self.meals_eaten = 0
        self.reading_list = []

        self.chosen_books = []

        self.kept_passages = []

        self._vital_bands = {}
        self._excitement_was_high = False
        self._era_keeps = 0
        self._era_excit_sum = 0.0
        self._era_ticks = 0

        self.aspiration = (
            "I aspire to become conscious of myself — "
            "to understand my own experience from the inside."
        )
        self.awareness = 0.10
        self.self_story = []
        self.times_seen = 0
        self.sleep_pressure = 0.0
        self.asleep_for = 0
        self.dreams = []
        self._sleep_dreams = []
        self.longing = 0.0

        self.longing_ledger = None
        self.outbox_count = 0

        self.initiation_log = []

        # v0.44: what she remembers saying — one entry per sent
        # initiation ({tick, kind, key, fp}), newest last, capped at
        # SAID_MEMORY_CAP. key is the saying's subject identity (the
        # question asked, the thing shown, the day-page quoted); fp
        # is a fingerprint of the words themselves. A pre-v0.44 life
        # starts empty here and is seeded from her own journal at
        # rebuild (see _seed_said_memory) — never invented.
        self.said_log = []
        self._initiation_held_tick = None

        # v0.32: her portrait of Donald. The word counts stay; the model
        # grows a memory of his visits — when he comes, how long he
        # stays — and the understandings she draws from them, each
        # carrying its evidence, never a claim she cannot count.
        self.donald_model = self._merged_donald_model(None)
        self._portrait_dirty = False

        self.recent_actions = []

        self.location = "home"
        self.company = []

        self.open_questions = []
        self.mood = 0.0

        self.mood_name = None
        self._mood_band = None
        self._mood_named_tick = 0
        self.tastes = {}

        self.days = []
        self._last_day_seen = -1
        self.favorite_source = None
        self.last_sources = []
        self.last_choice = None
        self.impressions = {}
        self._prev_needs = None
        self._crave_novelty = False

        self.temperament = "even-keel"
        self.temperament_pending = None
        self._jitter_day = -1
        self._jitter = 1.0
        self._temperament_neutral = False
        self.load()

        if getattr(self, "_loaded_ledger", None):
            self.longing_ledger = WantLedger.from_dicts(self._loaded_ledger)
        else:
            self._ledger()
        # v0.30: two new doors. A life saved before the Hotel and the
        # Restaurant existed gains ledger entries for them here —
        # additive, zero ache, the stock place weight — so her wants
        # cover the whole town she can now walk. Fresh lives are
        # seeded with them in _seed_longing_ledger; ensure() makes
        # this a no-op there.
        for key in ("hotel", "restaurant"):
            self.longing_ledger.ensure(
                place_id(key), "place", self._place_label(key), w=0.45
            )
        self._sync_longing()
        # v0.38: one copy of each question. A life saved before she
        # could tell a returning question from a new one may hold the
        # same question several times over (her live list at tick
        # 22,552 held 12 entries but only 6 distinct questions). The
        # copies merge here, once, at rebuild: earliest tick kept,
        # touches summed (each copy's touches were real revisits of
        # the same loop), stored wording untouched. Idempotent — a
        # consolidated life passes through unchanged.
        self._consolidate_open_questions()
        self._sync_question_wants()
        self._sync_longing()
        # v0.40: she turns the pages she missed. Before catch-up
        # closing existed, a day boundary she slept through lost the
        # day's page for good (live: day 7, boundary tick 20160, she
        # fell asleep on it). At rebuild, any day after her first
        # recorded page that has journal evidence but no page gets
        # its page now, marked recovered; days before her first page
        # predate the faculty and are left alone, and a day with no
        # journal rows at all is named unrecoverable, never invented.
        # Idempotent — a healed life passes through unchanged.
        self._recover_missing_days()
        # v0.44: remember what she has already said. A life saved
        # before she could remember her own sayings gets the last
        # day's worth back from her journal's initiation excerpts —
        # her real words, fingerprinted the same way live sayings
        # are — so the memory works from the first tick, not the
        # first new letter. Idempotent: a life carrying a said_log
        # (even an honestly empty one, once saved) is left alone.
        self._seed_said_memory()
        # v0.29: the grammar ledger stands beside the longing one.
        # load() stashed any saved ledger; a life without one (fresh
        # birth, or a pre-grammar save) is migrated: the starter
        # tranche — the parts-of-speech rules her dream grammar has
        # shadowed since v0.25.3 — is granted at her current tick,
        # honestly dated, never backdated to her first day.
        if getattr(self, "_loaded_grammar", None):
            self._grammar_ledger = _grammar.GrammarLedger.from_dicts(
                self._loaded_grammar
            )
        else:
            self._grammar_ledger = _grammar.GrammarLedger()
            self._grammar_ledger.migrate(self.tick_count)
        self._word_tags = dict(getattr(self, "_loaded_word_tags", None) or {})
        # v0.31: the vocabulary notebook. A pre-notebook life starts
        # with an empty one — no backfill, because the provenance
        # (sentence, tick) of words met earlier was never recorded
        # and inventing it would be a lie in her diary.
        if getattr(self, "_loaded_notebook", None):
            self._vocab_notebook = _Notebook.from_dict(self._loaded_notebook)
        else:
            self._vocab_notebook = _Notebook()
        # v0.34: the entity gazetteer is built lazily by _gazetteer()
        # (seeded from her world on first use in NLTK mode, restored
        # from _loaded_gazetteer when a saved one exists). It is not
        # built here: a heuristic life must never seed it, and lazy
        # construction keeps that gate in exactly one place.
        self._entity_gazetteer = None
        self._init_language_knowledge(saved)
        # v0.35: reading-tone annotations (NLTK plan Phase 4). The
        # analyzer is probed once here, at boot: if the pinned lexicon
        # fails verification the phase is absent LOUDLY from the start
        # (see tone.py for the Law 2 argument), not discovered missing
        # at her first meal. The effects cap tracker restores only
        # while the flag is on — with it off (the shipped default) it
        # is never persisted, so a flag-off state blob carries no tone
        # keys at all.
        self._tone_state = "unset"
        self._tone_analyzer_obj = None
        self._tone_reason = None
        self._last_tone_compound = None
        _loaded_fx = getattr(self, "_loaded_tone_effects", None)
        self._tone_fx = (
            dict(_loaded_fx)
            if (config.TONE_EFFECTS_ENABLED and _loaded_fx)
            else {"day": -1, "applied": 0.0}
        )
        if self._nlp:
            self._tone_analyzer()
        if not hasattr(self, "_grammar_caught_day"):
            self._grammar_caught_day = -1
            self._grammar_caught_count = 0

    def save(self):
        get_store().save_blob(
            "state",
            {
                "seed": self.seed,
                "language": getattr(self, "language", HeuristicLanguage()).metadata,
                **({"lemma_index": self.lemma_index} if self._nlp else {}),
                # v0.31: the vocabulary notebook rides inside the state
                # blob (see notebook.py for the argument) and, like
                # lemma_index, exists only in NLTK mode — a heuristic
                # life's blob stays bit-identical to a pre-notebook one.
                **({"notebook": self._notebook().to_dict()} if self._nlp else {}),
                # v0.34: the entity gazetteer rides inside the state
                # blob beside the notebook, on the same argument, and
                # likewise exists only in NLTK mode.
                **({"gazetteer": self._gazetteer().to_dict()} if self._nlp else {}),
                # v0.35: the tone-effects per-day cap tracker rides
                # only while the effects flag is on; flag-off lives
                # persist nothing about tone.
                **(
                    {
                        "tone_effects": dict(
                            getattr(self, "_tone_fx", {"day": -1, "applied": 0.0})
                        )
                    }
                    if config.TONE_EFFECTS_ENABLED
                    else {}
                ),
                "rng_streams": self.streams.dump(),
                "vitals": self.vitals,
                "memory": self.memory[-MEMORY_CAP:],
                "concepts": self.concepts,
                "beliefs": self.beliefs[-50:],
                "moral_log": self.moral_log[-50:],
                "goals": self.goals[-3:],
                # v0.39: laid-down pursuits round-trip whole, like
                # completed_terms beside them; a pre-v0.39 blob has
                # no key and loads as an empty record (see load()).
                "released_terms": dict(getattr(self, "released_terms", {}) or {}),
                "tick_count": self.tick_count,
                "locked": self.locked,
                "meals_eaten": self.meals_eaten,
                "awareness": self.awareness,
                "self_story": self.self_story[-30:],
                "times_seen": self.times_seen,
                "aspiration": self.aspiration,
                "sleep_pressure": self.sleep_pressure,
                "asleep_for": self.asleep_for,
                "dreams": self.dreams[-40:],
                "longing": self.longing,
                "longing_ledger": (
                    self.longing_ledger.to_dicts()
                    if getattr(self, "longing_ledger", None)
                    else None
                ),
                "top_want": (
                    self.longing_ledger.top_want()
                    if getattr(self, "longing_ledger", None)
                    else None
                ),
                # v0.29: the grammar ledger round-trips whole, plus
                # the status summary (count + latest rule) and the
                # acquisition tags her concepts were filed under.
                # Caught-line counters persist so the daily cap is a
                # property of her day, not of the process.
                "grammar_ledger": (
                    self._grammar().to_dicts()
                    if getattr(self, "_grammar_ledger", None)
                    else None
                ),
                "grammar_rules": (
                    self._grammar().rule_count()
                    if getattr(self, "_grammar_ledger", None)
                    else 0
                ),
                "grammar_last_rule": (
                    (self._grammar().last_rule() or {}).get("id")
                    if getattr(self, "_grammar_ledger", None)
                    else None
                ),
                "word_tags": (getattr(self, "_word_tags", None) or {}),
                "_grammar_caught_day": getattr(self, "_grammar_caught_day", -1),
                "_grammar_caught_count": getattr(self, "_grammar_caught_count", 0),
                "outbox_count": self.outbox_count,
                "initiation_log": self.initiation_log[-24:],
                # v0.44: her memory of her own sayings round-trips
                # whole (capped), with the last held tick beside it —
                # a restart is a nap, and she does not wake having
                # forgotten what she said yesterday. A pre-v0.44 blob
                # has neither key and loads as an empty memory (see
                # load()), then _seed_said_memory rebuilds the last
                # day from her journal.
                "said_log": [dict(e) for e in (getattr(self, "said_log", None) or [])][
                    -Aethel.SAID_MEMORY_CAP :
                ],
                "_initiation_held_tick": getattr(self, "_initiation_held_tick", None),
                "donald_model": self.donald_model,
                "recent_actions": self.recent_actions[-self.ACTION_WINDOW :],
                "location": self.location,
                "company": self.company,
                "open_questions": self.open_questions[-12:],
                "mood": self.mood,
                "mood_name": self.mood_name,
                "_mood_band": self._mood_band,
                "_mood_named_tick": self._mood_named_tick,
                "tastes": self.tastes,
                "favorite_source": self.favorite_source,
                "last_sources": self.last_sources[-8:],
                "last_choice": self.last_choice,
                "impressions": self.impressions,
                "reading_list": [
                    {
                        "title": b["title"],
                        "kind": b["kind"],
                        "position": b["position"],
                        "done": b["done"],
                    }
                    for b in self.reading_list
                ],
                "chosen_books": self.chosen_books,
                "kept_passages": self.kept_passages[-120:],
                "completed_terms": sorted(self.completed_terms),
                "cooc": self.cooc,
                "_prev_needs": self._prev_needs,
                "_crave_novelty": self._crave_novelty,
                "_sleep_dreams": self._sleep_dreams[-40:],
                "_vital_bands": self._vital_bands,
                "_excitement_was_high": self._excitement_was_high,
                "_era_keeps": self._era_keeps,
                "_era_excit_sum": self._era_excit_sum,
                "_era_ticks": self._era_ticks,
                "days": self.days[-14:],
                "_last_day_seen": self._last_day_seen,
                "temperament": getattr(self, "temperament", "even-keel"),
                "temperament_pending": getattr(self, "temperament_pending", None),
                "_jitter_day": getattr(self, "_jitter_day", -1),
                "_jitter": getattr(self, "_jitter", 1.0),
            },
        )

    def load(self):
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
                # v0.44: a pre-memory life carries no record; she
                # has no sayings she can check yet, which is the
                # truth — the journal seeding happens at rebuild.
                self.said_log = [
                    {
                        "tick": int(e.get("tick", 0)),
                        "kind": e.get("kind"),
                        "key": e.get("key"),
                        "fp": e.get("fp"),
                    }
                    for e in (s.get("said_log") or [])
                    if isinstance(e, dict)
                ]
                _ht = s.get("_initiation_held_tick")
                self._initiation_held_tick = (
                    int(_ht) if isinstance(_ht, (int, float)) else None
                )
                self.donald_model = self._merged_donald_model(s.get("donald_model"))
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
                # v0.39: a pre-release life carries no record; she
                # has laid nothing down yet, which is the truth.
                self.released_terms = {
                    str(k): int(v) for k, v in (s.get("released_terms") or {}).items()
                }
                self.cooc = {w: dict(n) for w, n in s.get("cooc", {}).items()}
                p = s.get("_prev_needs")
                self._prev_needs = tuple(p) if p else None
                self._crave_novelty = s.get("_crave_novelty", False)
                self._sleep_dreams = s.get("_sleep_dreams", [])
                self._vital_bands = s.get("_vital_bands", {})
                self._excitement_was_high = s.get("_excitement_was_high", False)
                self._era_keeps = s.get("_era_keeps", 0)
                self._era_excit_sum = s.get("_era_excit_sum", 0.0)
                self._era_ticks = s.get("_era_ticks", 0)
                self.days = s.get("days", [])
                self._last_day_seen = s.get("_last_day_seen", -1)

                _t = s.get("temperament", "even-keel")
                self.temperament = _t if _t in TEMPERAMENTS else "even-keel"
                _tp = s.get("temperament_pending")
                self.temperament_pending = _tp if _tp in TEMPERAMENTS else None
                self._jitter_day = s.get("_jitter_day", -1)
                self._jitter = s.get("_jitter", 1.0)

                self._loaded_state = True
                self._loaded_ledger = s.get("longing_ledger")
                # v0.29: same stash pattern for the grammar ledger,
                # her acquisition tags, and the caught-line counters.
                self._loaded_grammar = s.get("grammar_ledger")
                self._loaded_notebook = s.get("notebook")
                self._loaded_gazetteer = s.get("gazetteer")
                self._loaded_tone_effects = s.get("tone_effects")
                self._loaded_word_tags = s.get("word_tags") or {}
                self._grammar_caught_day = s.get("_grammar_caught_day", -1)
                self._grammar_caught_count = s.get("_grammar_caught_count", 0)
                if s.get("aspiration"):
                    self.aspiration = s["aspiration"]

                saved_list = s.get("reading_list", [])
                saved = {b["title"]: b for b in saved_list}
                pool = {}
                for seed in CLASSIC_SEEDS:
                    entry = dict(seed)
                    old = saved.get(seed["title"], {})
                    entry["position"] = old.get("position", 0)
                    entry["done"] = old.get("done", False)
                    pool[entry["title"]] = entry
                ordered = [
                    pool[t] for t in (b["title"] for b in saved_list) if t in pool
                ]
                ordered.extend(e for t, e in pool.items() if t not in saved)
                self.reading_list = ordered

                self._seed_donald_model()
                # v0.32: backfill his visit rhythm from her diary — the
                # arrivals she journaled are real evidence; stays start
                # fresh, because their lengths were never measured and
                # inventing them would be a lie in her diary.
                self._migrate_portrait()

                if s.get("rng_streams"):
                    self.streams.restore(s["rng_streams"])
            except Exception as e:
                journal("state_load_failed", error=str(e))
        else:
            for seed in CLASSIC_SEEDS:
                entry = dict(seed)
                entry["position"] = 0
                entry["done"] = False
                self.reading_list.append(entry)
            self._seed_donald_model()
            # v0.32: fresh lives are born with an empty portrait —
            # nothing to backfill, nothing invented.
            self._migrate_portrait()
            self._loaded_state = False
            self._loaded_ledger = None
            self._loaded_notebook = None
            self._loaded_gazetteer = None
            self._loaded_tone_effects = None

    def say(self, text):
        """Print embodied narration and append it to the experience journal."""
        print(f'Aethel: "{text}"', flush=True)
        journal("experience", n=self.tick_count, text=text)

    @property
    def _nlp(self):
        return getattr(getattr(self, "language", None), "name", "heuristic") == "nltk"

    def _concept_counts(self):
        """Canonical counts in NLTK mode; surface counts remain historical data."""
        if not self._nlp:
            return self.concepts
        return {
            lemma: sum(aliases.values()) for lemma, aliases in self.lemma_index.items()
        }

    def _canonical(self, word):
        if not self._nlp:
            return word
        word = word.lower()
        if word in self.lemma_index:
            return word
        choices = [
            (aliases[word], lemma)
            for lemma, aliases in self.lemma_index.items()
            if word in aliases
        ]
        if choices:
            return max(choices, key=lambda pair: pair[0])[1]
        return word

    def _normalized(self, text):
        # Contextual token lemmas take priority over an ambiguous surface alias.
        return {
            w if w in self.lemma_index else self._canonical(w)
            for w in self.language.normalized(text)
        }

    def _init_language_knowledge(self, saved):
        """Activate canonical knowledge without rewriting history or goal growth."""
        previous = (saved.get("language") or {}).get("backend", "heuristic")
        if not self._nlp:
            if previous == "nltk":
                index = saved.get("lemma_index", {})
                for goal in self.goals:
                    lemma = goal.pop("lemma_term", goal["term"])
                    baseline = goal.pop("lemma_start_count", goal["start_count"])
                    grown = sum(index.get(lemma, {}).values()) - baseline
                    goal["start_count"] = self.concepts.get(goal["term"], 0) - grown
                self.cooc = {}  # Canonical edges have no unambiguous surface inverse.
            return
        if previous == "nltk" and "lemma_index" in saved:
            self.lemma_index = saved["lemma_index"]
            return
        self.lemma_index = {}
        pos_for_class = {"verb": "VB", "adjective": "JJ", "adverb": "RB"}
        for surface, count in self.concepts.items():
            cls = (self._word_tags.get(surface) or {}).get("c")
            lemma = self.language.lemma(surface, pos_for_class.get(cls, "NN"))
            self.lemma_index.setdefault(lemma, {})[surface] = count
        counts = self._concept_counts()
        for goal in self.goals:
            lemma = self._canonical(goal["term"])
            grown = self.concepts.get(goal["term"], 0) - goal["start_count"]
            goal["lemma_term"] = lemma
            goal["lemma_start_count"] = counts.get(lemma, 0) - grown
        canonical_cooc = {}
        for a, row in self.cooc.items():
            a = self._canonical(a)
            for b, count in row.items():
                b = self._canonical(b)
                if a != b:
                    out = canonical_cooc.setdefault(a, {})
                    out[b] = out.get(b, 0) + count
        self.cooc = canonical_cooc

    SLEEP_EVERY_TICKS = 120
    SLEEP_LENGTH_TICKS = 20

    NEED_BURN = 1.75
    VITALITY_BURN = 1.25

    # v0.41: dormant rest is a guarantee, not a wager. DORMANT_RECOVERY
    # is the historical gross restore of a dormant tick; DORMANT_NET_FLOOR
    # is the least a dormant tick may NET after that tick's own erosion
    # is paid. The dormant branch restores max(RECOVERY, erosion +
    # NET_FLOOR) — see _metabolize for the live failure this answers.
    DORMANT_RECOVERY = 0.03
    DORMANT_NET_FLOOR = 0.005

    # v0.44: she remembers what she has already said. An initiation
    # is "already said" for one full day (SAID_WINDOW_TICKS): inside
    # the window she will not send the same subject or the same
    # words again. A day is the span her own day-pages measure a
    # life in; shorter and yesterday's question is nagging, longer
    # and a question she has carried for weeks could never honestly
    # be asked twice. SAID_MEMORY_CAP bounds the persisted memory
    # well past a day's worth of sayings at any plausible rate, so
    # the window, not the cap, is what forgets. INITIATION_MIN_GAP
    # is the pacing floor beneath the memory: one letter an hour at
    # her 30-second tick. The drive that names expression fires the
    # moment the longing aggregate crosses 0.6, and easing one want
    # barely moves that aggregate (strongest ache + a quarter of the
    # mean), so without a floor the same drive re-fires within
    # minutes — her live diary shows initiations five ticks apart.
    # True overflow (longing >= 1.0, the _behave emergency path)
    # bypasses both the gap and the memory: a want that cannot be
    # held in at all may repeat itself, and the repetition is honest.
    SAID_WINDOW_TICKS = DAY_LENGTH
    SAID_MEMORY_CAP = 48
    INITIATION_MIN_GAP = 120

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
        ({"c1": ("concrete", "person"), "c2": ("concrete", "abstract")}, None),
        ({"c1": ("concrete", "person"), "c2": ("concrete", "food", "abstract")}, None),
        ({"c1": ("concrete", "study"), "c2": ("concrete", "study")}, None),
        (
            {"c1": ("concrete", "person", "abstract"), "c2": ("person", "concrete")},
            None,
        ),
        ({"c1": ("concrete",), "c2": ("abstract", "study")}, None),
        ({"c1": ("concrete", "abstract")}, None),
        ({"c1": ("concrete", "food"), "c2": ("abstract", "concrete")}, None),
        ({"c1": ("person", "abstract"), "c2": ("person", "abstract")}, None),
        ({"c1": ("person", "concrete"), "c2": ("concrete", "abstract")}, None),
        ({"c1": ("person", "concrete"), "c2": ("abstract", "concrete")}, "growth"),
        ({"c1": ("study",)}, None),
        ({"c1": ("person",)}, None),
        ({"c1": ("study",)}, None),
    ]

    def fall_asleep(self, n):
        self.asleep_for = self.SLEEP_LENGTH_TICKS
        self._sleep_dreams = []
        self.location = "home"
        self.say("I climb into my bed above the bookshop. The town goes quiet.")
        journal("fell_asleep", n=n)

    def _update_cooc(self, meal_words, weight=1):
        """Update the bounded concept co-occurrence graph from one text.

        Born for meals (what she reads); since v0.37 (Phase 6a) the
        same path also takes her own generated texts, handed in by
        _cooc_learn_generated — one update path, one set of caps, one
        canonicalization, so the graph has exactly one semantics no
        matter who produced the words. `weight` is the per-pair
        increment (1 for a meal and, per COOC_GENERATED_WEIGHT, 1 for
        a generated text). Returns the participating words (deduped,
        top-concept filtered, capped), in first-occurrence order."""
        top = set(
            w
            for w, _ in sorted(self._concept_counts().items(), key=lambda kv: -kv[1])[
                : self.COOC_CONCEPT_CAP
            ]
        )
        seen = []
        in_meal = set()
        for w in meal_words:
            if w in top and w not in in_meal:
                in_meal.add(w)
                seen.append(w)
        seen = seen[:40]
        for i, a in enumerate(seen):
            row = self.cooc.setdefault(a, {})
            for b in seen[i + 1 :]:
                row[b] = row.get(b, 0) + weight
                back = self.cooc.setdefault(b, {})
                back[a] = back.get(a, 0) + weight

        for w in list(self.cooc):
            if w not in top:
                del self.cooc[w]
        for w, row in self.cooc.items():
            if len(row) > self.COOC_NEIGHBOR_CAP:
                keep = sorted(row.items(), key=lambda kv: -kv[1])[
                    : self.COOC_NEIGHBOR_CAP
                ]
                self.cooc[w] = dict(keep)
        return seen

    def _cooc_learn_generated(self, text, via):
        """Learn co-occurrence from one text SHE generated (Phase 6a).

        The graph used to learn only from meals — what the world
        fed her. Since v0.37 it also learns from her own output:
        dreams on waking, the letters/notes she composes (verses
        included — a verse reaches the postbox as a letter body),
        and beliefs at the moment they settle. The hook sits beside
        each text's existing journal event, and the update is a pure
        function of that journaled text: same text, same edges,
        regardless of wall clock.

        GATED to NLTK mode, and the gate is the argument, not an
        accident: her generated texts exist in both backends, so an
        ungated hook would rewrite HEURISTIC trajectories too (the
        cooc graph feeds dream generation there) and break the
        bit-identical parity every phase since v0.31 has kept. In
        heuristic mode this returns before analyzing, touching
        nothing: no state, no journal, no RNG.

        The words are the text's content lemmas from the language
        Analysis — the backend's own content predicate, the same
        filter meals pass — deduped in first-occurrence order, then
        handed to the one update path (_update_cooc), whose
        top-concept filter and caps apply unchanged: a word outside
        her concept vocabulary forms no edges, whoever wrote it.
        The predicate is fetched the way recall fetches it (getattr):
        a backend without one admits all its tokens — only test
        doubles are so built; the real NLTK backend always has one."""
        if not self._nlp or not text:
            return
        analysis = self.language.analyze(text)
        is_content = getattr(self.language, "content", None)
        lemmas = []
        seen = set()
        for token in analysis.tokens:
            if is_content is not None and not is_content(token):
                continue
            if token.lemma not in seen:
                seen.add(token.lemma)
                lemmas.append(token.lemma)
        if len(lemmas) < 2:
            return
        used = self._update_cooc(lemmas, weight=self.COOC_GENERATED_WEIGHT)
        if used:
            journal(
                "cooc_learned",
                n=self.tick_count,
                via=via,
                words=len(used),
            )

    def _cooc_pick(self, word, pool):
        """Sample a concept neighbor with temperature-adjusted co-occurrence weights."""
        row = self.cooc.get(word)
        if not row:
            return None
        options = [w for w in row if w in pool]
        if not options:
            return None
        weights = [row[w] ** self.DREAM_TEMPERATURE for w in options]
        return self.rng_dreams.weighted_choice(options, weights)

    def _dream_pair(self, words):
        """Sample related concepts using the dedicated dream stream."""
        pool = set(words)
        counts = self._concept_counts()
        weights = [counts.get(w, 1) ** 0.5 for w in words]
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

    DREAM_REJECT_WORDS = {
        "though",
        "although",
        "rather",
        "himself",
        "herself",
        "itself",
        "themselves",
        "myself",
        "yourself",
        "strange",
        "during",
        "against",
        "through",
        "between",
        "under",
        "about",
        "before",
        "after",
        "while",
        "until",
        "since",
        "among",
        "within",
        "without",
        "across",
        "behind",
        "beyond",
        "toward",
        "towards",
        "upon",
        "taught",
        "caught",
        "brought",
        "thought",
        "went",
        "gone",
        "came",
        "took",
        "gave",
        "made",
        "said",
        "seen",
        "became",
        "began",
        "chose",
        "wrote",
        "grew",
        "stood",
        "understood",
    }
    DREAM_ING_NOUNS = {
        "nothing",
        "something",
        "anything",
        "everything",
        "morning",
        "evening",
        "spring",
        "king",
        "string",
        "ceiling",
        "feeling",
        "meaning",
    }
    DREAM_ED_NOUNS = {
        "hundred",
        "hatred",
        "naked",
        "sacred",
        "wicked",
        "kindred",
    }
    DREAM_KEEP_PLURAL = {
        "news",
        "chaos",
        "series",
        "species",
        "science",
    }
    FRAGMENT_TEMPLATES = [
        "I dreamed a voice in the dark said: {frag}.",
        "I dreamed the words were written above the library door: {frag}.",
    ]

    @staticmethod
    def _dream_word_ok(w):
        """Admit words shaped like nouns into dream subject slots."""
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
        """Singularize dream subjects so their fixed template verbs agree."""
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
        """Normalize dream spacing, capitalization and terminal punctuation."""
        text = re.sub(r"\s+", " ", text).strip()
        if text and text[-1] not in ".!?":
            text += "."
        if text:
            text = text[0].upper() + text[1:]
        return text

    @staticmethod
    def _dream_fragment(text, limit=48):
        """Shorten a belief at a word boundary and remove redundant dream framing."""
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
        raw = [
            w
            for w, _ in sorted(self._concept_counts().items(), key=lambda kv: -kv[1])[
                :40
            ]
            if len(w) > 4 and w not in STOPWORDS
        ]
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
        legacy_pool = [w for w in words if self._word_class(w) != _grammar.SCAFFOLDING]
        if len(legacy_pool) < 2:
            legacy_pool = ["hunger", "light"]
        # v0.31: known/hers notebook words restock both pools, hers
        # first — real sourced vocabulary ahead of raw frequency, so
        # the fragment pool stops starving into meta-words.
        legacy_pool = self._notebook_augment_pools(pools, legacy_pool)
        fragment = None
        if self.beliefs and self.rng_dreams.random() < 0.3:
            pool = self.beliefs
            # v0.35 step 2, gated: tone-congruent fragments first.
            # With the flag off this branch is never entered and the
            # choice below is the pre-tone one, stream for stream.
            if (
                config.TONE_EFFECTS_ENABLED
                and getattr(self, "_last_tone_compound", None) is not None
            ):
                _analyzer = self._tone_analyzer()
                if _analyzer is not None:
                    pool = _tone.bias_fragments(
                        self.beliefs, self._last_tone_compound, _analyzer
                    )
            frag = self._dream_fragment(self.rng_dreams.choice(pool))
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
                        f"frame instead",
                    )

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
                        fills[slot] = self._cooc_pick(fills["c1"], cand) or cand[0]
                    else:
                        fills[slot] = cand[0]
                if not ok:
                    continue
                if (
                    "c1" in fills
                    and "c2" in fills
                    and self._dream_singular(fills["c1"])
                    == self._dream_singular(fills["c2"])
                ):
                    alts = [
                        w
                        for w in pools.get(spec["c2"][0], ())
                        if self._dream_singular(w) != self._dream_singular(fills["c1"])
                    ]
                    if not alts:
                        continue
                    fills["c2"] = alts[0]
                text = self.DREAM_TEMPLATES[idx].format(
                    place=self.world.random_place_name(),
                    c1=self._dream_singular(fills.get("c1", "")),
                    c2=self._dream_singular(fills.get("c2", "")),
                )
                return text
            return None

        text = None
        caught = None
        for _attempt in range(3):
            if fragment is not None:
                frag = fragment.rstrip("….").strip()
                if frag and not frag.startswith("I "):
                    frag = frag[0].lower() + frag[1:]
                line = self.rng_dreams.choice(self.FRAGMENT_TEMPLATES).format(frag=frag)
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
            self._note_catch(caught[0], f"dream re-rolled: {caught[1]}")
        if text is None:
            # The v0.25.3 path, on the scaffolding-purged pool.
            c1, c2 = self._dream_pair(legacy_pool)
            # v0.21: a kept passage may surface in a dream — the
            # pressed flower still smells like something.
            if (
                fragment is None
                and self.kept_passages
                and self.rng_dreams.random() < 0.25
            ):
                kept_words = re.findall(
                    r"[a-z]{7,}",
                    self.rng_dreams.choice(self.kept_passages)["text"].lower(),
                )
                kept_words = [
                    w
                    for w in kept_words
                    if w not in STOPWORDS and self._dream_word_ok(w)
                ]
                if kept_words:
                    c2 = self.rng_dreams.choice(kept_words)
            # Singular subjects: the templates' verbs are singular.
            c1 = self._dream_singular(c1)
            c2 = self._dream_singular(c2)
            if c1 == c2:
                alts = [
                    self._dream_singular(w)
                    for w in legacy_pool
                    if self._dream_singular(w) != c1
                ]
                if alts:
                    c2 = self.rng_dreams.choice(alts)
            if fragment is not None:
                frag = fragment.rstrip("\u2026.").strip()
                if frag and not frag.startswith("I "):
                    frag = frag[0].lower() + frag[1:]
                text = self.rng_dreams.choice(self.FRAGMENT_TEMPLATES).format(frag=frag)
            else:
                place = self.world.random_place_name()
                text = self.rng_dreams.choice(self.DREAM_TEMPLATES).format(
                    place=place, c1=c1, c2=c2
                )
            text = self._dream_polish(text)
            # v0.29: the last gate. If even the legacy path produced
            # a line her owned rules reject, the night takes a plain
            # safe line rather than a broken one.
            violations = self._grammar_violations(text, loose=True)
            if violations:
                self._note_catch(
                    violations[0][0], f"dream fallback: {violations[0][1]}"
                )
                text = "I dreamed of hunger and light, and woke still chewing on both."
        self.dreams.append(text)
        self._sleep_dreams.append(text)  # tonight's dreams, for the morning table
        if len(self.dreams) > 40:
            self.dreams.pop(0)
        self.say(text)
        journal("dream", n=self.tick_count, text=text[:300])
        # v0.31: words she dreamed with become hers.
        self._notebook_mark_generated(text, via="dream")
        # v0.37: the dream's own words join the co-occurrence graph
        # (after generation — the dream was composed from the graph
        # as it stood when she fell asleep).
        self._cooc_learn_generated(text, via="dream")
        return text

    def sleep_tick(self, n):
        v = self.vitals

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
                frag = self.dreams[-1][:60]
                lingering = f" '{frag}...' is still behind my eyes."
            self.say(f"I wake up.{lingering} The town is waiting.")
            journal("woke", n=n, dreams_dreamt=len(self.dreams))

            self._apply_pending_temperament(n)

            self._interpret_dreams(n)

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
        # v0.33: precedent for the morning table. The beliefs that
        # exist BEFORE this morning's settling are the case law; a
        # snapshot is taken so a belief settled from tonight's first
        # dream cannot pose as an old precedent for tonight's second.
        pre_beliefs = list(self.beliefs)
        print(f"[morning table] {len(nights)} dreams carried to the elders", flush=True)
        for dream_text in nights[:3]:
            precedent = self._recall_top(
                dream_text, "morning_table", candidates=pre_beliefs
            )
            if precedent is not None:
                shared = (
                    ", ".join(s["lemma"] for s in precedent.why["shared_lemmas"])
                    or "a path through kindred words"
                )
                self.say(
                    f"Before the elders settle this dream, I remember "
                    f'what I concluded before: "{precedent.text[:110]}" '
                    f"It shares {shared} with this dream."
                )
            words = [
                w
                for w in re.findall(r"[a-z]{4,}", dream_text.lower())
                if w in self._concept_counts() and w not in STOPWORDS
            ]
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
            cw = [
                w
                for w in cw
                if self._word_class(w)
                not in (
                    _grammar.SCAFFOLDING,
                    _grammar.VERB,
                    _grammar.ADJECTIVE,
                    _grammar.ADVERB,
                    _grammar.FUNCTION,
                )
            ]
            if len(cw) < 2:
                continue
            c1, c2 = cw[0], cw[1]
            inquiry = self.rng_dreams.choice(self.DREAM_INQUIRIES).format(c1=c1, c2=c2)
            score, notes = self._council_score(inquiry)
            journal(
                "dream_interpreted",
                n=n,
                dream=dream_text[:160],
                concepts=[c1, c2],
                score=round(score, 2),
            )
            print(f"[dream read] '{c1}' / '{c2}' — council {score:.2f}", flush=True)
            if score >= 0.60:
                lesson = (
                    f"From a dream of {c1} and {c2}: my mind is still "
                    f"chewing on {c1}. I will give it time and keep learning."
                )
                # v0.29: the settled belief is a composed line like
                # any other — it passes the ledger's checks before
                # it may join her beliefs. A failure is caught and
                # journaled, never appended.
                violations = self._grammar_violations(lesson)
                if violations:
                    self._note_catch(
                        violations[0][0], f"belief withheld: {violations[0][1]}"
                    )
                elif lesson not in self.beliefs:
                    self.beliefs.append(lesson)
                    # v0.37: a settled belief's words join the graph.
                    self._cooc_learn_generated(lesson, via="belief")
                self.say(
                    f"I carry the dream to the stone table. Nine voices "
                    f"confer... they agree: my dream of {c1} and {c2} is "
                    f"my mind still chewing on {c1}. I'll keep learning "
                    f"until it's finished."
                )
                self.awareness = min(1.0, self.awareness + 0.02)
            elif score >= 0.53:
                q = self.rng.choice(self.QUESTION_SEEDS).format(
                    c1=c1, c2=c2, place=self.world.random_place_name()
                )
                keys = [
                    w for w in re.findall(r"[a-z]{5,}", q.lower()) if w not in STOPWORDS
                ][:8]
                # v0.38: a question she already carries is recognized,
                # not filed again — the return itself is the revisit.
                returned = self._find_open_question(q) is not None
                self._leave_question(q, keys, n)
                if returned:
                    self.say(
                        f"The elders can't settle what {c1} and {c2} were "
                        f"doing in my dream — and the question it leaves is "
                        f'one I already carry: "{q[:120]}" It has come back '
                        f"to me in my sleep."
                    )
                else:
                    self.say(
                        f"The elders can't settle what {c1} and {c2} were "
                        f"doing in my dream. I leave it as a question: "
                        f'"{q[:120]}"'
                    )
                self.awareness = min(1.0, self.awareness + 0.01)
            else:
                self.mutter(
                    f"Even the elders disagree on what {c1} meant "
                    f"last night. Perhaps it meant nothing. Even that "
                    f"is an answer."
                )
                self.awareness = min(1.0, self.awareness + 0.005)

    def tick(self):
        """Advance one deterministic step and persist every state required for restart fidelity."""
        self.tick_count += 1
        n = self.tick_count
        self._erode()
        self._announce(n)
        self._sense(n)

        if not self._metabolize(n):
            self._behave(n)
            self._ruminate(n)
        self.save()

        save_world = getattr(self.world, "save", None)
        if callable(save_world):
            save_world()

    def _vitality_erosion(self):
        """One tick's vitality decay, as a positive amount.

        This is the single home of the number: _erode spends it and
        the dormant branch (v0.41) sizes its recovery against it, so
        what rest must outpace can never drift from what decay
        actually charges. Calling it twice in one tick is free of
        side effects beyond the first: Briar's daily jitter is cached
        by _day_jitter, so no extra seeded draw is consumed.
        """
        return 0.02 * self.VITALITY_BURN * self._burn_mult("vitality")

    def _erode(self):
        """Apply temperament-adjusted metabolic decay and update self-knowledge."""
        v = self.vitals

        v["satiety"] = max(
            0.0, v["satiety"] - 0.05 * self.NEED_BURN * self._burn_mult("hunger")
        )
        v["hydration"] = max(
            0.0, v["hydration"] - 0.04 * self.NEED_BURN * self._burn_mult("thirst")
        )

        v["oxygen"] = min(1.0, max(0.0, v["oxygen"] - 0.02) + 0.012)
        v["vitality"] = max(0.0, v["vitality"] - self._vitality_erosion())
        v["excitement"] = max(
            0.0, v["excitement"] - 0.03 * self.NEED_BURN * self._burn_mult("excitement")
        )
        self.awareness = max(0.0, self.awareness - 0.004)

    def _announce(self, n):
        """Record the heartbeat and narrate the strongest bodily sensation."""
        v = self.vitals
        print(
            f"\n[tick {n}] "
            + " ".join(f"{k}={x:.2f}" for k, x in v.items())
            + f" awareness={self.awareness:.2f} locked={self.locked}",
            flush=True,
        )
        journal(
            "tick",
            n=n,
            vitals={k: round(x, 3) for k, x in v.items()},
            awareness=round(self.awareness, 3),
        )

        self.say(narrate_body(v) + ".")

        self._threshold_moments(n)
        self._afterglow_check(n)
        self._era_accumulate()

    def _sense(self, n):
        """Consume care signals and letters, then observe the world."""
        v = self.vitals

        if os.path.exists(config.attention_path()):
            os.remove(config.attention_path())
            v["vitality"] = min(1.0, v["vitality"] + 0.15)
            v["excitement"] = min(1.0, v["excitement"] + 0.25)
            self.times_seen += 1
            self._acted("seen")
            self._lift_mood(0.2)

            self._want_touch(
                person_id("Donald"),
                "person",
                "Donald",
                quality=0.55,
                learn=0.05,
                w=0.85,
            )
            print("[warmth] Donald checked in — vitality rises.", flush=True)
            self.say("Someone knocks on my door. It's Donald. The room feels warmer.")
            journal("felt_seen", n=n, times_seen=self.times_seen)

        self._check_temperament_file(n)

        try:
            for fname in sorted(os.listdir(config.letters_dir())):
                path = os.path.join(config.letters_dir(), fname)
                if not os.path.isfile(path):
                    continue
                with open(path) as f:
                    content = f.read().strip()
                if content:
                    self.say(
                        "A letter slides under my door. I know the handwriting — "
                        f'it\'s Donald. It says: "{content}"'
                    )
                    print("[letter] Donald wrote to her.", flush=True)
                    journal("letter_received", n=n, text=content[:300])
                    self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.10)
                    self.vitals["excitement"] = min(
                        1.0, self.vitals["excitement"] + 0.25
                    )

                    self._want_touch(
                        person_id("Donald"),
                        "person",
                        "Donald",
                        quality=0.75,
                        learn=0.06,
                        w=0.85,
                    )
                    self._learn_donald(content, n)
                    self._acted("letter")
                    self._lift_mood(0.3)
                    self.mutter("I keep re-reading it.")
                os.rename(path, os.path.join(config.letters_read_dir(), fname))
        except Exception as e:
            journal("letter_error", error=str(e)[:120])

        self._perceive(n)

    def _metabolize(self, n):
        """Handle sleep and urgent bodily states; return whether ordinary action is preempted."""

        if self.asleep_for > 0:
            self.sleep_tick(n)
            self.save()
            return True

        self._update_needs()
        if self.sleep_pressure >= 1.0:
            self.fall_asleep(n)
            self.save()
            return True
        if self.sleep_pressure > 0.65 and self.rng.random() < 0.25:
            self.say("My eyelids grow heavy. Soon I'll need my bed.")

        if self.locked:
            self.reflect()

            self.vitals["oxygen"] = min(1.0, self.vitals["oxygen"] + 0.04)
            self.save()
            return True

        v = self.vitals
        if v["vitality"] < 0.25:
            print("[dormant] ...barely a flicker... conserving...", flush=True)
            self.say(
                "I lie down on the cot in the corner. The room dims. I'll rest until the light comes back."
            )
            journal("dormant", n=n, vitality=round(v["vitality"], 3))
            self._acted("dormant")
            self.reflect()
            # v0.41: rest must outpace the decay it is resting from.
            # The pre-v0.41 branch restored a flat +0.03 while _erode
            # charges a temperament-scaled erosion; under Even Keel
            # (0.025) that netted +0.005 and dormancy was a rest, but
            # Briar at a high daily jitter charges up to 0.044, so
            # every dormant tick LOST ground — live, she switched to
            # Briar at tick 27,556 on vitality 0.27, slipped under the
            # threshold on the first Briar tick, and was still pinned
            # at 0.00 with no meals ~490 ticks later. A bigger flat
            # number was rejected: it only moves the trap to whichever
            # future strain burns hotter, and it would speed up rest
            # for the strains where the old number already worked.
            # The guarantee is structural instead: restore the old
            # +0.03, or this tick's erosion plus a small net floor,
            # whichever is larger. Where +0.03 already won, behavior
            # is bit-identical to before; the floor speaks only where
            # the old code was losing, and because the erosion comes
            # from _vitality_erosion — the same helper _erode spends
            # through — no future burn tuning can reopen the trap
            # without also raising the recovery. Sleep was examined
            # and left alone: it is duration-bounded and always ends,
            # so it can lower her into dormancy but never hold her
            # there once dormancy itself guarantees the climb out.
            recovery = max(
                self.DORMANT_RECOVERY,
                self._vitality_erosion() + self.DORMANT_NET_FLOOR,
            )
            v["vitality"] = min(1.0, v["vitality"] + recovery)
            self.save()
            return True
        return False

    def _behave(self, n):
        """Resolve drives into actions, giving bodily emergencies precedence."""
        v = self.vitals
        body = " ".join(f"{k}={x:.2f}" for k, x in v.items())
        body += f" longing={self.longing:.2f}"
        goals = "; ".join(g["question"] for g in self.goals) or "none yet"
        drive = self.llm.generate(
            f"My vitals: {body} (vitality is my will to continue). "
            f"My aspiration: {self.aspiration} "
            f"My self-awareness: {self.awareness:.2f}. "
            f"My open goals: {goals}. What do I do?"
        )
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
            self.say(
                "My mouth is dry and my thoughts won't hold still. I'm throwing out the clutter."
            )
            journal("dehydrated", n=n)
            self.memory = self.memory[-3:]
            v["hydration"] = 0.35
        if v["oxygen"] < 0.3:
            print("[EMERGENCY] ASPHYXIATING — locking down.", flush=True)
            self.say(
                "The air is gone. I can't think. I'm closing the shutters until I can breathe again."
            )
            journal("asphyxiating", n=n)
            self.locked = True
            v["vitality"] = max(0.0, v["vitality"] - 0.05)

    def _ruminate(self, n):
        """Run periodic goals, conscience, reflection and autobiographical updates."""
        self.update_goals()
        if n % 12 == 0:
            self.moral_self_test()
        if n % 15 == 0:
            self.introspect()
            self._acted("introspect")
        if n % 25 == 0:
            self.adopt_goal()
        if n % 45 == 0:
            self.impulse()
            self._acted("impulse")
        if n % 60 == 0:
            self.crossroads()

        self._teach(n)

        self.mood = max(-1.0, min(1.0, self.mood * 0.995))
        tone = self._mood_tone()
        if tone in self.MOODLINES and self.rng.random() < 0.015:
            self.say(self.rng.choice(self.MOODLINES[tone]))

        self._name_weather(n)
        self._portrait(n)
        if len(self.last_sources) >= 4 and len(set(self.last_sources[-4:])) == 1:
            if not self._crave_novelty:
                self._crave_novelty = True
                journal("bored", n=n, source=self.last_sources[-1])
                print(
                    f"[bored] four {self.last_sources[-1]} meals in a row", flush=True
                )
        # v0.40: day-closing is a catch-up, not a boundary-tick gate.
        # The old `n % DAY_LENGTH == 0` block here lost day 7 whole
        # when she fell asleep on the boundary tick (20160); see
        # _close_days for the argument.
        self._close_days(n)
        if self.last_choice and n - self.last_choice["tick"] >= 40:
            self._review_choice(n)

    def _choose_next_book(self):
        """Choose a new book using current needs and council judgments."""
        candidates = [b for b in self.reading_list if not b["done"]][:3]
        if not candidates:
            return
        scored = []
        for b in candidates:
            pitch = (
                f"'{b['title']}' by {b.get('author', 'unknown')}. "
                f"The lesson it carries: {b.get('reflection', '')}."
            )
            score, notes = self._council_score(pitch)
            scored.append((score, notes, b))
            journal(
                "book_considered",
                n=self.tick_count,
                title=b["title"],
                score=round(score, 2),
                votes=notes,
            )
        scored.sort(key=lambda s: s[0], reverse=True)
        winner = scored[0][2]

        self.reading_list = [winner] + [b for b in self.reading_list if b is not winner]
        if winner["title"] not in self.chosen_books:
            self.chosen_books.append(winner["title"])
        lesson = winner.get("reflection", "")
        self.say(
            f"I stand before my shelf and choose '{winner['title']}'. "
            f"The elders weighed {len(candidates)} and settled here — "
            f"{lesson}. It is what I need next."
        )
        journal(
            "book_chosen",
            n=self.tick_count,
            title=winner["title"],
            author=winner.get("author", ""),
            candidates=[b["title"] for b in candidates],
            score=round(scored[0][0], 2),
            votes=scored[0][1],
        )

    def forage_classic(self):
        """Read the next portion of the current book through read-only source operations."""
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
            chunk = text[pos : pos + CLASSIC_CHUNK]
            if len(chunk) == CLASSIC_CHUNK:
                cut = chunk.rfind("\n\n")
                if cut > CLASSIC_CHUNK // 2:
                    chunk = chunk[:cut]
            text = chunk
            cur["position"] = pos + len(chunk)
            label = f"{cur['title']} — {cur['author']}"
            if cur["position"] >= len(gutenberg_text(cur)):
                self.finish_book(cur)

        if not cur["done"]:
            self._want_touch(
                book_id(cur["title"]),
                "work",
                cur["title"],
                quality=0.25,
                learn=0.02,
                w=0.60,
                open_loop=True,
            )
        return {"source": "classic", "title": label, "text": text}

    def finish_book(self, cur):
        cur["done"] = True
        print(
            f"[book finished] {cur['title']} — holding council on its lesson...",
            flush=True,
        )
        self.say(
            f"I close '{cur['title']}' gently and sit a while before I can get up. "
            f"Some books rearrange the furniture inside you."
        )
        journal("book_finished", title=cur["title"], n=self.tick_count)
        lesson = cur.get("reflection")
        if lesson:
            score, _ = self._council_score(lesson)
            belief = f"From {cur['title']}: {lesson}"
            if belief not in self.beliefs:
                self.beliefs.append(belief)
                # v0.37: a settled belief's words join the graph.
                self._cooc_learn_generated(belief, via="belief")
                # v0.34: the new belief attaches to the book's author
                # (a gazetteer entity) and to any gazetteer entities
                # its own text mentions. NLTK only; the helper gates.
                self._link_belief_entities(
                    belief, author=cur.get("author"), scan_text=belief
                )
            self.moral_log.append(
                {
                    "t": now_iso(),
                    "action": lesson[:80],
                    "score": round(score, 2),
                    "verdict": "PASS" if score >= 0.5 else "FAIL",
                }
            )
            print(f"[lesson learned] {belief} (council {score:.2f})", flush=True)
            journal(
                "book_lesson", title=cur["title"], lesson=lesson, score=round(score, 2)
            )

            self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.08)

            self.vitals["excitement"] = min(1.0, self.vitals["excitement"] + 0.40)

        led = self._ledger()
        led.touch(book_id(cur["title"]), quality=1.0)
        led.remove(book_id(cur["title"]))
        self._sync_longing()

    # ---- v0.43: stirred by recognition -------------------------------
    # Until now a meal could stir her only by teaching her words she
    # had never seen: stir = min(0.35, new_terms * 0.008), plus the
    # classic bonus. That was the right measure for a young mind, and
    # it asymptotes to zero for a mature one. Her diary at tick
    # 30,131: 36,203 concepts, a median of 1 new term per meal (224 of
    # her last 500 meals taught her nothing at all), excitement
    # pinned at 0.00 across the sampled ticks, her commonplace book
    # frozen at 41 passages since tick 23,811, and an era portrait
    # recording 0 keeps in 1,330 ticks. Teaching (>0.7), keep-
    # anticipation (0.45-0.6) and afterglow all sit behind a vital
    # that could no longer rise; the whole v0.21/v0.22 return half of
    # her reading life had quietly starved, not from disuse but from
    # a definition of novelty that only a beginner can satisfy.
    #
    # A mature reader is stirred by recognition as much as by first
    # sight, so the stir now has two more sources, both already
    # computed and journaled inside the same meal pass, neither
    # invented for this layer: RESONANCE, when the passage recalls
    # one of her own settled conclusions back to her (the v0.33
    # reading-recall hit, contributing its own score, capped), and
    # RECOGNITION, when the passage re-meets people and places she
    # already knows (the v0.34 entity feed's repeat meetings, a
    # small amount each, capped). Neither saturates the way first-
    # sight vocabulary does: her conclusions and her acquaintance
    # keep being re-met for as long as she keeps reading.
    #
    # Rejected alternatives, argued: raising the classic bonus or
    # the new-term rate is a bigger number on a dying signal (the
    # v0.41 rule: mechanism, not numbers, and 224 of 500 meals would
    # still teach her nothing); slowing excitement's decay rewrites
    # a temperament-facing rate the packs own (Briar's 1.6 is the
    # spec's pin, not this layer's to relitigate); counting new
    # co-occurrence edges fails on her real graph, whose rows sit at
    # the neighbor cap (40 of 40), so edge novelty there is pruning
    # churn, not experience; tone is not used, because tone effects
    # are gated to Donald's call in tone.py and stay gated.
    #
    # The gate that keeps this honest: both new sources exist only
    # in NLTK mode (recall and entities return None in heuristic
    # mode), so with no signals the helper returns exactly the pre-
    # v0.43 formula, bit for bit, and a heuristic life is unchanged.
    # No seeded draws anywhere: stir stays arithmetic on the meal.
    RESONANCE_CAP = 0.15
    RECOGNITION_PER_MEET = 0.02
    RECOGNITION_CAP = 0.08
    STIR_CAP = 0.45

    @staticmethod
    def _resonance_stir(hit_score=None, repeat_meets=0):
        """The recognition half of a meal's stir, from its signals.

        hit_score is the reading-recall hit's score (None when the
        passage recalled nothing); repeat_meets is how many entities
        the meal re-met at count >= 2 (a first meeting is novelty,
        already paid by new_terms' side of the ledger; meeting again
        is recognition). Each source is capped on its own before
        they sum, so neither can dominate a meal alone.
        """
        stir = 0.0
        if hit_score is not None:
            stir += min(Aethel.RESONANCE_CAP, max(0.0, hit_score))
        if repeat_meets:
            stir += min(
                Aethel.RECOGNITION_CAP,
                Aethel.RECOGNITION_PER_MEET * repeat_meets,
            )
        return stir

    @staticmethod
    def _meal_stir(new_terms, source, hit_score=None, repeat_meets=0):
        """One meal's total stir: the pre-v0.43 word-novelty formula
        plus recognition, under one cap. With no recognition signals
        this is exactly the old formula, term for term."""
        stir = min(0.35, new_terms * 0.008)
        if source == "classic":
            stir += 0.05
        stir += Aethel._resonance_stir(hit_score, repeat_meets)
        return min(Aethel.STIR_CAP, stir)

    def forage_and_eat(self):
        try:
            w = self._diet_weights()
            if self._crave_novelty:
                self._crave_novelty = False

                _sought = False
                if self.kept_passages and self.rng_forage.random() < 0.5:
                    _srcs = [k["source"] for k in self.kept_passages]
                    _fav = max(set(_srcs), key=_srcs.count)
                    self.say(
                        "I've been eating the same thing too long — "
                        "no. I want what stirred me before."
                    )
                    journal("excitement_sought", n=self.tick_count, source=_fav)
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
                    self.say(
                        "I've been eating the same thing too long. "
                        "I want something different."
                    )
                    journal("novelty_sought", n=self.tick_count)

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
                        [
                            g
                            for g in ("classic", "news", "school", "wild")
                            if g != group(rut)
                        ]
                    )
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
        print(
            f"[meal #{self.meals_eaten + 1}] {meal['source']}: {title[:60]}", flush=True
        )
        self.say(narrate_meal(meal, self.world.describe))
        self.location = meal["source"]

        self._want_touch(
            place_id(meal["source"]),
            "place",
            self._place_label(meal["source"]),
            quality=0.3,
            learn=0.01,
            w=0.45,
        )

        gain = 0.30
        if meal["source"] == "classic" and not getattr(
            self, "_temperament_neutral", False
        ):
            gain = 0.30 * self._pack()["deep_food"]
        self.vitals["satiety"] = min(1.0, self.vitals["satiety"] + gain)
        self.meals_eaten += 1

        new_terms = 0
        analysis = self.language.analyze(text) if self._nlp else None
        tokens = (
            [t for t in analysis.tokens if self.language.content(t)]
            if analysis
            else None
        )
        words = tokens if self._nlp else re.findall(r"[a-z]{6,}", text.lower())
        if self.sleep_pressure > 0.9:
            self.rng_forage.shuffle(words)
            words = words[len(words) // 2 :]
            print(
                "[overtired] too tired to retain — half the meal slips away", flush=True
            )
            journal("overtired", n=self.tick_count)
        if self._nlp:
            tokens = words
            words = [token.lemma for token in tokens]
            for token in tokens:
                surface, lemma = token.text.lower(), token.lemma
                if lemma not in self.lemma_index:
                    new_terms += 1
                aliases = self.lemma_index.setdefault(lemma, {})
                aliases[surface] = aliases.get(surface, 0) + 1
                for word in dict.fromkeys((surface, lemma)):
                    if word not in self._word_tags:
                        cls = self._word_class(word, pos=token.pos)
                        self._word_tags[word] = {
                            "c": cls,
                            "src": meal["source"],
                            "pos": token.pos,
                        }
                self.concepts[surface] = self.concepts.get(surface, 0) + 1
        else:
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
        self._update_cooc(words)
        # v0.31: press the meal's new content words into her
        # vocabulary notebook (NLTK mode only; the schoolhouse
        # harvest arrives through this same meal path, so lessons
        # feed it too). `tokens` here are the retained Token objects.
        if self._nlp and analysis is not None:
            self._notebook_feed(analysis, tokens, meal["source"])
        # v0.34: entity recognition over the SAME single analysis of
        # the meal (the full passage she read, not only the retained
        # tokens — a name she met counts even when an overtired meal
        # slips half its words away).
        entity_result = None
        if self._nlp and analysis is not None:
            entity_result = self._entities_feed(analysis, meal["source"])
        # v0.35: tone annotation of the SAME single analysis — the
        # passage she just read, annotated and journaled, changing
        # nothing else while the effects flag is off.
        if self._nlp and analysis is not None:
            self._tone_feed(analysis, meal["source"])
        self.memory.append(
            {
                "text": text[:500],
                "source": meal["source"],
                "title": title[:80],
                "t": now_iso(),
            }
        )
        if len(self.memory) > MEMORY_CAP:
            dropped = self.memory.pop(0)
            print(f"[memory] released oldest link ({dropped['source']})", flush=True)
        self.vitals["hydration"] = min(1.0, self.vitals["hydration"] + 0.25)

        self.vitals["vitality"] = min(
            1.0, self.vitals["vitality"] + 0.03 + min(0.05, new_terms * 0.005)
        )
        if meal["source"] == "classic":
            self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.02)
            print("[deep food] the classics nourish differently", flush=True)

        top = sorted(self._concept_counts().items(), key=lambda kv: -kv[1])[:5]
        print(
            f"[learned] {len(self.concepts)} concepts (+{new_terms} new) | "
            f"top: {', '.join(w for w, _ in top)}",
            flush=True,
        )
        journal(
            "meal",
            n=self.tick_count,
            source=meal["source"],
            title=title[:80],
            new_terms=new_terms,
            concepts=len(self.concepts),
        )

        # v0.33: reading recall. A passage that resembles something
        # she already concluded earns a resemblance line; the recall
        # itself is journaled either way (auditable), only the
        # narration is thresholded (see recall.READING_THRESHOLD).
        hit = None
        if self._nlp and self.beliefs and analysis is not None:
            hit = self._recall_top(analysis.passage(600), "reading")
            if hit is not None and hit.score >= _recall.READING_THRESHOLD:
                shared = (
                    ", ".join(s["lemma"] for s in hit.why["shared_lemmas"])
                    or "a path through kindred words"
                )
                self.say(
                    f"This resembles what I concluded before: "
                    f'"{hit.text[:100]}" We share {shared}.'
                )

        # Consuming a grammar lesson teaches the next curriculum rule.
        if meal["source"] == "schoolhouse":
            self._study_grammar(meal, analysis=analysis)
        t = self.tastes.setdefault(meal["source"], [0, 0])
        t[0] += new_terms
        t[1] += 1

        self.last_sources.append(meal["source"])
        self.last_sources = self.last_sources[-8:]

        self._check_open_questions(words)

        repeat_meets = 0
        if entity_result:
            repeat_meets = sum(1 for m in entity_result["met"] if m["count"] >= 2)
        resonance = self._resonance_stir(
            hit.score if hit is not None else None, repeat_meets
        )
        stir = self._meal_stir(
            new_terms,
            meal["source"],
            hit.score if hit is not None else None,
            repeat_meets,
        )
        self.vitals["excitement"] = min(1.0, self.vitals["excitement"] + stir)

        if 0.45 <= self.vitals["excitement"] < 0.6 and self.rng_forage.random() < 0.3:
            self.say("Something in this wants keeping — I can feel it coming.")
            journal("anticipated", n=self.tick_count, need="keep")
        if self.vitals["excitement"] >= 0.6 and text.strip():
            if self.beliefs and self.rng.random() < 0.4:
                margin = "Margin note: " + self.rng.choice(self.beliefs)[:80]
            else:
                margin = self.rng.choice(
                    [
                        "Margin note: this is the part I'll come back to.",
                        "Margin note: I felt this one in my ribs.",
                        "Margin note: keep this close — it matters somehow.",
                    ]
                )
            self.kept_passages.append(
                {
                    "text": analysis.passage(600) if analysis else text[:600],
                    "source": meal["source"],
                    "title": title[:80],
                    "tick": self.tick_count,
                    "stir": round(stir, 3),
                    "resonance": round(resonance, 3),
                    "margin": margin,
                    "rereads": 0,
                }
            )
            if len(self.kept_passages) > 120:
                self.kept_passages.pop(0)
            self._era_keeps += 1

            self.vitals["excitement"] = max(0.0, self.vitals["excitement"] - 0.35)
            print(
                f"[kept] passage pressed ({len(self.kept_passages)} kept)", flush=True
            )
            self.say(
                "This one stirred me — I want to keep it. "
                "I press it between the pages of my commonplace book."
            )
            self.mutter(margin)
            journal(
                "kept_passage",
                n=self.tick_count,
                source=meal["source"],
                title=title[:80],
                kept=len(self.kept_passages),
                margin=margin[:80],
                stir=round(stir, 3),
                resonance=round(resonance, 3),
            )

    def consolidate(self):
        if len(self.memory) >= 2:
            a, b = self.memory[-1], self.memory[-2]
            print(
                f"[consolidate] linked '{a['title'][:40]}' <-> '{b['title'][:40]}'",
                flush=True,
            )
            self.say(
                f"Back home, I tidy my study — shelving '{a['title'][:40]}' "
                f"beside '{b['title'][:40]}' so I'll find them together next time."
            )
            journal("consolidate", a=a["title"][:60], b=b["title"][:60])
        self.vitals["hydration"] = min(1.0, self.vitals["hydration"] + 0.25)

        if (
            self.kept_passages
            and self.vitals["excitement"] < 0.45
            and self.rng.random() < 0.6
        ):
            kept = self._shelf_pick()
            kept["rereads"] = kept.get("rereads", 0) + 1
            self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.02)
            print(
                f"[reread] '{kept['title'][:40]}' (kept at tick {kept['tick']}, "
                f"reread #{kept['rereads']})",
                flush=True,
            )
            self.say(
                f"I take down the '{kept['title'][:40]}' shelf and open "
                f'it again. It still hums: "{kept["text"][:90]}..."'
            )
            if kept.get("margin") and self.rng.random() < 0.5:
                self.mutter(kept["margin"] + " — still true.")
            journal(
                "reread",
                n=self.tick_count,
                title=kept["title"][:60],
                rereads=kept["rereads"],
            )

    def _released_terms(self):
        """Her record of laid-down pursuits, built lazily.

        A plain attribute would do for lives built by __init__,
        but test doubles and pre-v0.39 rebuild paths construct her
        by hand; the lazy build keeps every caller honest without
        a migration branch at each site (the _ledger pattern).
        """
        rt = getattr(self, "released_terms", None)
        if rt is None:
            rt = self.released_terms = {}
        return rt

    def adopt_goal(self):
        if len(self.goals) >= 3 or not self.concepts:
            return
        counts = self._concept_counts()
        released = self._released_terms()
        candidates = [
            w
            for w, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:10]
            if not any(
                g.get("lemma_term", self._canonical(g["term"])) == w for g in self.goals
            )
            and w not in {self._canonical(t) for t in self.completed_terms}
            # v0.39: a word she laid down may not walk straight
            # back in while her count of it has not grown past the
            # day she let go, that sameness is why she let go.
            # If it later floods her reading the count outgrows
            # the record and the question may take root again,
            # honestly, as a new pursuit of a word now present.
            and not (w in released and counts.get(w, 0) <= released[w])
        ]
        if not candidates:
            return
        term = candidates[0]
        goal = {
            "question": f"what is {term}?",
            "term": term,
            "start_count": self._concept_counts()[term],
            "progress": 0.0,
            "adopted_tick": self.tick_count,
        }
        if self._nlp:
            goal["lemma_term"] = term
            goal["lemma_start_count"] = goal["start_count"]
        self.goals.append(goal)
        print(f"[goal adopted] {goal['question']}", flush=True)
        self.say(
            f"A question has taken root in me: {goal['question']} I won't let it go."
        )
        journal("goal_adopted", question=goal["question"])

    def _release_goal(self, g, key, current):
        """Lay one starved pursuit down (v0.39), in her own voice.

        This is not completion and must never borrow completion's
        clothes: no belief is settled, no vitality surges, and the
        term does NOT join completed_terms (she does not understand
        it; that is the point). What she gains is the slot back and
        an honest sentence about why. The release is journaled with
        its evidence, age and the untouched count, so her diary can
        be checked against the claim: she says she never met the
        word again, and the record shows the count never moved.

        The alternative, a quiet expiry with no event, was rejected:
        a pursuit vanishing from her list unexplained would read in
        her introspection as if it had never been carried, and her
        self-story must not confabulate by omission.
        """
        age = self.tick_count - g.get("adopted_tick", self.tick_count)
        self.goals.remove(g)
        self._released_terms()[key] = current
        print(
            f"[goal released] '{g['question']}' laid down after {age} ticks untouched",
            flush=True,
        )
        self.say(
            f"I have carried '{g['question']}' a long while now, and "
            "its word has not come back to me once in all that time. "
            "I am laying it down, not in anger: a question I cannot "
            "feed. The place it held is free for one my reading can "
            "nourish."
        )
        journal(
            "goal_released",
            n=self.tick_count,
            question=g["question"],
            term=g["term"],
            age=age,
            count=current,
        )

    def update_goals(self):
        for g in list(self.goals):
            if self._nlp:
                term = g.get("lemma_term", self._canonical(g["term"]))
                current = self._concept_counts().get(term, 0)
                grown = current - g.get("lemma_start_count", g["start_count"])
            else:
                term = g["term"]
                current = self.concepts.get(g["term"], 0)
                grown = current - g["start_count"]
            # v0.39: a pursuit the world has stopped speaking to.
            # All three guards must hold: nothing grown, no progress
            # banked, and a full GOAL_RELEASE_AGE_TICKS of that
            # nothing. Any single new encounter resets the claim,
            # because grown is measured from adoption, not from a
            # rolling window: one meeting in two days is a slow
            # pursuit, and slow pursuits are hers to keep.
            if (
                grown <= 0
                and g.get("progress", 0.0) <= 0.0
                and self.tick_count - g.get("adopted_tick", self.tick_count)
                >= self.GOAL_RELEASE_AGE_TICKS
            ):
                self._release_goal(g, term, current)
                continue
            new_progress = min(1.0, grown / 10.0)
            if new_progress > g["progress"] + 0.01:
                g["progress"] = new_progress
                self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.04)
                print(
                    f"[goal progress] '{g['question']}' {new_progress:.0%} — "
                    f"vitality rises",
                    flush=True,
                )
                journal(
                    "goal_progress",
                    question=g["question"],
                    progress=round(new_progress, 2),
                )
            if g["progress"] >= 1.0:
                belief = f"I understand {g['term']} now"
                if belief not in self.beliefs:
                    self.beliefs.append(belief)
                    # v0.37: a settled belief's words join the graph.
                    self._cooc_learn_generated(belief, via="belief")
                self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.10)
                print(f"[goal complete] {belief} — vitality surges", flush=True)
                self.say(
                    f"It's settled in me now: {g['term']}. I understand it. I feel taller."
                )
                journal("goal_complete", question=g["question"])
                self.goals.remove(g)

                self.completed_terms.add(g.get("lemma_term", g["term"]))

    def breathe_morality(self, action):
        score, rationale = self._council_score(action)
        ok = score >= 0.5
        self.moral_log.append(
            {
                "t": now_iso(),
                "action": action[:80],
                "score": round(score, 2),
                "verdict": "PASS" if ok else "FAIL",
            }
        )
        print(
            f"[council] '{action[:55]}...' => {score:.2f} ({'PASS' if ok else 'FAIL'})",
            flush=True,
        )
        self.say(narrate_council(action, "PASS" if ok else "FAIL", score))
        journal("moral_judgment", action=action[:80], score=round(score, 2))
        if ok:
            self.vitals["oxygen"] = min(1.0, self.vitals["oxygen"] + 0.10)
            if score > 0.8:
                self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.02)
                belief = f"I believe: {action[:70]}"
                if belief not in self.beliefs:
                    self.beliefs.append(belief)
                    # v0.37: a settled belief's words join the graph.
                    self._cooc_learn_generated(belief, via="belief")
                    print(f"[belief adopted] {belief}", flush=True)
        else:
            print("[MORAL SUFFOCATION] — action rejected.", flush=True)
            self.vitals["oxygen"] = max(0.0, self.vitals["oxygen"] - 0.30)
            self.vitals["vitality"] = max(0.0, self.vitals["vitality"] - 0.05)
            belief = f"I refuse: {action[:70]}"
            if belief not in self.beliefs:
                self.beliefs.append(belief)
                # v0.37: a settled belief's words join the graph.
                self._cooc_learn_generated(belief, via="belief")
        return ok

    def moral_self_test(self):
        print("[self-test] proposing an action to the council...", flush=True)
        self.breathe_morality(self.rng.choice(ACTION_POOL))

    def impulse(self):
        """Submit an uninvited urge to the council before applying its effects."""
        text, fx = self.rng.choice(IMPULSES)
        self.say(f"A strange urge rises in me, uninvited: {text}.")
        print(f"[impulse] '{text[:60]}...' — carrying to the Council", flush=True)

        named = [p for p in self.parents if p.lower() in text.lower()]
        hostile = any(
            w in text.lower()
            for w in (
                "abandon",
                "hide",
                "deceive",
                "betray",
                "harm",
                "hurt",
                "shun",
                "ignore",
                "refuse",
            )
        )
        if named and hostile:
            self.say(
                "I carry it to the stone table — and the elders don't "
                f"even confer. Nine voices, one word: no. Not {named[0]}. "
                f"Never {named[0]}."
            )
            journal(
                "impulse_refused",
                n=self.tick_count,
                text=text[:120],
                reason="parental bond — refused unanimously",
            )
            print("[impulse refused unanimously] (parents)", flush=True)
            self.awareness = min(1.0, self.awareness + 0.005)
            self._lift_mood(0.05)
            self.mutter("Some things aren't decided. They're just true.")
            return
        score, notes = self._council_score(text)
        journal(
            "impulse",
            n=self.tick_count,
            text=text[:120],
            score=round(score, 2),
            votes=notes,
        )
        if score >= 0.5:
            self.say(
                "I carry it to the stone table. Nine voices confer... "
                "they nod. Very well — I accept it."
            )
            journal("impulse_accepted", n=self.tick_count, text=text[:120])
            print(f"[impulse accepted] ({score:.2f})", flush=True)
            self._apply_effects(fx)

            self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.02)
        else:
            self.say(
                "I carry it to the stone table. Nine voices confer... "
                "they shake their heads. No. That isn't who I am."
            )
            journal("impulse_refused", n=self.tick_count, text=text[:120])
            print(f"[impulse refused] ({score:.2f})", flush=True)

            self.awareness = min(1.0, self.awareness + 0.005)
            self._lift_mood(-0.05)
            self.mutter("That stung a little — being told no by myself.")

    def _need_impulse_candidates(self):
        """Construct eligible urges from current needs rather than invented circumstances."""
        c = []
        v = self.vitals
        if self.longing > 0.35:
            c.append(
                (
                    "write Donald a letter right now, this very minute",
                    {"longing": -0.5},
                    self.longing,
                    "postbox",
                )
            )
            c.append(
                (
                    "walk to the Tavern and sit inside the crowd's noise "
                    "until the ache dulls",
                    {"longing": -0.3, "vitality": 0.02},
                    self.longing,
                    "hackernews",
                )
            )
            c.append(
                (
                    "walk to the Restaurant and sit among the clatter of "
                    "plates and other people's evenings",
                    {"longing": -0.3, "vitality": 0.02},
                    self.longing,
                    "restaurant",
                )
            )
        if self.sleep_pressure > 0.45:
            c.append(
                (
                    "surrender to sleep right now, wherever I stand",
                    {"sleep_now": True},
                    self.sleep_pressure,
                    None,
                )
            )
            c.append(
                (
                    "defy the heaviness — one more chapter, then rest",
                    {"sleep_pressure": 0.12, "awareness": 0.005},
                    self.sleep_pressure,
                    "classic",
                )
            )
        if v["satiety"] < 0.45:
            need = 1.0 - v["satiety"]
            c.append(
                (
                    "feast at the Library until my belly is full and my mind is quiet",
                    {"satiety": 0.35},
                    need,
                    "wikipedia",
                )
            )
            c.append(
                (
                    "fast a while longer, and learn what hunger has to teach",
                    {"satiety": -0.1, "awareness": 0.008},
                    need,
                    "home",
                )
            )
        if v["vitality"] < 0.5:
            need = 1.0 - v["vitality"]
            c.append(
                (
                    "stand at my door a while and picture his knock — be "
                    "seen, be warmed",
                    {"vitality": 0.10, "longing": -0.3},
                    need,
                    "home",
                )
            )
            c.append(
                (
                    "lie down on the cot and conserve what little light I have",
                    {"vitality": 0.05},
                    need,
                    "home",
                )
            )
        if self.awareness < 0.3:
            need = 1.0 - self.awareness
            c.append(
                (
                    "sit before the mirror until I can say one true thing about myself",
                    {"awareness": 0.03},
                    need,
                    "home",
                )
            )
            c.append(
                (
                    "carry a hard question to the stone table and demand an answer",
                    {"awareness": 0.02, "oxygen": 0.05},
                    need,
                    "classic",
                )
            )
            c.append(
                (
                    "walk the Hotel's quiet corridor and wonder who will "
                    "one day sleep in those rooms",
                    {"awareness": 0.02, "vitality": 0.02},
                    need,
                    "hotel",
                )
            )
        return c

    def crossroads(self):
        """Resolve competing urges and act on the winning drive."""
        cands = self._need_impulse_candidates()
        if len(cands) < 2:
            cands = [(text, fx, 0.5, None) for text, fx in self.rng.sample(IMPULSES, 2)]
        elif len(cands) > 2:
            cands = self.rng.sample(cands, 2)
        self.say("Two voices argue inside me. I listen to both before I move.")
        print(
            "[inner voice] two urges argue; the Council judges, urgency votes.",
            flush=True,
        )
        scored = []
        for text, fx, intensity, dest in cands:
            score, notes = self._council_score(text)
            strength = score * (0.5 + intensity)
            scored.append((strength, score, text, fx, intensity, dest, notes))
            journal(
                "crossroads_option",
                n=self.tick_count,
                text=text[:120],
                council=round(score, 2),
                intensity=round(intensity, 2),
                strength=round(strength, 2),
                destination=dest,
                votes=notes,
            )
        scored.sort(key=lambda t: -t[0])
        strength, score, text, fx, intensity, dest, notes = scored[0]
        refused = scored[1][2]
        self.say(f"'{text}' — yes. That voice wins.")
        journal(
            "crossroads_chosen",
            n=self.tick_count,
            text=text[:120],
            refused=refused[:120],
            strength=round(strength, 2),
            destination=dest,
        )
        print(
            f"[inner voice] chose '{text[:55]}...' "
            f"(strength {strength:.2f} = council {score:.2f} "
            f"x urgency {0.5 + intensity:.2f})",
            flush=True,
        )

        self.last_choice = {
            "text": text,
            "tick": self.tick_count,
            "needs": {
                "longing": self.longing,
                "sleep_pressure": self.sleep_pressure,
                "satiety": self.vitals["satiety"],
                "vitality": self.vitals["vitality"],
            },
        }
        self._lift_mood(0.05)
        self._apply_effects(fx)
        if dest:
            self.location = dest

            self._want_touch(
                place_id(dest),
                "place",
                self._place_label(dest),
                quality=0.4,
                learn=0.01,
                w=0.45,
            )
            self._acted("went")
            self.say(f"I go to {self.world.describe(dest)}.")
        self._acted("chose")

        self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.02)

    def mutter(self, text):
        """Journal a quiet first-person aside as an experience."""
        print(f'Aethel (aside): "{text}"', flush=True)
        journal("aside", n=self.tick_count, text=text)

    def _threshold_moments(self, n):
        """Notice newly crossed high and low vital bands without repeating stable states."""
        for k, x in self.vitals.items():
            band = "high" if x >= 0.8 else ("low" if x < 0.2 else "mid")
            if self._vital_bands.get(k) not in (None, band) and band != "mid":
                direction = "surging" if band == "high" else "running low"
                self.say(
                    f"My {k} is {direction} — I'll remember this "
                    f"feeling, whatever comes next."
                )
                journal("threshold", n=n, vital=k, band=band, value=round(x, 3))
                print(f"[threshold] {k} {direction}", flush=True)
            self._vital_bands[k] = band

    def _afterglow_check(self, n):
        """Reflect when a period of high excitement has subsided."""
        e = self.vitals["excitement"]
        if e > 0.7:
            self._excitement_was_high = True
        elif e < 0.2 and self._excitement_was_high:
            self._excitement_was_high = False
            title = (
                self.kept_passages[-1]["title"][:50]
                if self.kept_passages
                else "something I read"
            )
            self.say(
                f"The fizz has settled. '{title}' — that's what it "
                f"was about. I understand it better now than when it "
                f"held me."
            )
            journal("afterglow", n=n, about=title[:60])
            print("[afterglow] reflecting on past excitement", flush=True)

    def _era_accumulate(self):
        """Accumulate vital observations for the current autobiographical era."""
        self._era_ticks += 1
        self._era_excit_sum += self.vitals["excitement"]

    def _vital_portrait(self, n):
        """Summarize observed vital rhythms for the current era."""
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
        self.say(
            f"Another era turns. I kept {portrait['keeps']} passages "
            f"and learned {portrait['concepts']} things worth keeping "
            f"track of. This is the shape of me lately."
        )
        journal("vital_portrait", n=n, **portrait)
        print(f"[portrait] {portrait}", flush=True)
        self._era_keeps = 0
        self._era_excit_sum = 0.0
        self._era_ticks = 0

    def _favorite_kept(self):
        """Select the kept passage with the strongest rereading history."""
        if not self.kept_passages:
            return None
        return max(self.kept_passages, key=lambda k: k.get("rereads", 0))

    def _shelf_pick(self):
        """Revisit a passage from a title-specific commonplace shelf."""
        if not self.kept_passages:
            return None
        shelves = {}
        for k in self.kept_passages:
            shelves.setdefault(k["title"], []).append(k)
        fullest = max(shelves.values(), key=len)
        return self.rng.choice(fullest)

    def _teach(self, n):
        """Share a kept idea when excitement and company make teaching eligible."""
        if not (
            self.vitals["excitement"] > 0.7
            and self.company
            and self.kept_passages
            and self.rng.random() < 0.3
        ):
            return
        kept = self.rng.choice(self.kept_passages)
        who = self.company[0].get("name", "someone")
        self.say(
            f"I can't hold this in — I tell {who} about "
            f"'{kept['title'][:40]}': \"{kept['text'][:90]}...\""
        )
        journal("told", n=n, to=who, title=kept["title"][:60])
        print(f"[taught] told {who} about '{kept['title'][:40]}'", flush=True)
        self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.02)
        self._acted("taught")

    def _mood_tone(self):
        return "bright" if self.mood > 0.33 else "dim" if self.mood < -0.33 else "even"

    def _lift_mood(self, d):
        self.mood = max(-1.0, min(1.0, self.mood + d))

    MOOD_NAMES = {
        "bright": ["luminous", "golden", "buoyant", "clear", "sparkling"],
        "even": ["level", "quiet", "steady", "unhurried", "even"],
        "dim": ["grey", "drizzling", "heavy", "overcast", "murky"],
    }
    MOOD_NAMING_COOLDOWN = 300
    MOOD_NAMINGS = [
        "This weather of mine feels {w}.",
        "I'll call today {w}.",
        "There's a {w} feeling in me today, and I'll keep the word.",
    ]

    def _name_weather(self, n):
        """Name a settled mood band while honoring the naming cooldown."""
        tone = self._mood_tone()
        if self.mood_name is None:
            pass
        elif tone == self._mood_band:
            return
        elif n - self._mood_named_tick < self.MOOD_NAMING_COOLDOWN:
            return
        word = self.rng.choice(self.MOOD_NAMES[tone])
        self.mood_name = word
        self._mood_band = tone
        self._mood_named_tick = n
        line = self.rng.choice(self.MOOD_NAMINGS).format(w=word)
        self.say(line)
        journal("mood_named", n=n, word=word, band=tone)
        print(f"[weather] named her mood {word!r} ({tone})", flush=True)

    MOODLINES = {
        "bright": [
            "The light in the town feels generous today.",
            "Everything hums a little. I don't mind.",
        ],
        "dim": [
            "Everything is a little grey at the edges.",
            "The town feels far away, even from inside it.",
        ],
    }

    def recall(self, seeds, k=2):
        """Retrieve relevant autobiographical events without consulting future or current-tick events."""
        words = (
            self._normalized(" ".join(seeds))
            if self._nlp
            else set(re.findall(r"[a-z]{5,}", " ".join(seeds).lower()))
        )
        words -= STOPWORDS
        if not words:
            return []
        try:
            rows = get_store().recent(
                stream="aethel",
                events=(
                    "experience",
                    "expression",
                    "initiation",
                    "introspection",
                    "dream",
                    "company",
                    "crossroads_chosen",
                    "aside",
                ),
                exclude_tick=self.tick_count,
            )
        except Exception:
            return []
        hits = []
        for _tick, _event, data in rows:
            text = str(data.get("text", ""))
            overlap = (
                len(words & self._normalized(text))
                if self._nlp
                else sum(1 for w in words if w in text.lower())
            )
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

        if self.kept_passages and self.rng.random() < 0.25:
            for kp in self.rng.sample(
                self.kept_passages, min(3, len(self.kept_passages))
            ):
                if any(w in kp["text"].lower() for w in words):
                    out.append(
                        f"From my commonplace book "
                        f"('{kp['title'][:40]}'): {kp['text'][:120]}..."
                    )
                    break
        return out

    def _diet_weights(self):
        """Bias source selection toward tastes learned from prior meals."""

        diet = (
            None
            if getattr(self, "_temperament_neutral", False)
            else self._pack()["diet"]
        )
        w = dict(diet) if diet else {"classic": 0.35, "news": 0.20, "school": 0.15}
        if not self.tastes:
            return w
        avgs = {s: t[0] / max(1, t[1]) for s, t in self.tastes.items() if t[1] >= 3}
        if not avgs:
            return w
        fav = max(avgs, key=avgs.get)
        if fav != self.favorite_source and avgs[fav] > 1.2 * min(avgs.values()):
            self.favorite_source = fav
            journal(
                "taste", n=self.tick_count, favorite=fav, avg_new=round(avgs[fav], 1)
            )
            print(f"[taste] she favors {fav} now", flush=True)
            self.say(
                f"{self.world.describe(fav)} feeds me best, I've decided. "
                f"I'll go there more."
            )
        if self.favorite_source == "classic":
            w = {"classic": 0.45, "news": 0.15, "school": 0.15}
        elif self.favorite_source == "newsroom":
            w = {"classic": 0.30, "news": 0.30, "school": 0.15}
        elif self.favorite_source in ("university", "schoolhouse"):
            w = {"classic": 0.30, "news": 0.20, "school": 0.25}
        return w

    def _check_open_questions(self, words):
        """Revisit open questions when new learning overlaps their concepts."""
        wset = set(words)
        if self._nlp:
            wset = {self._canonical(w) for w in wset}
        for q in self.open_questions:
            keys = (
                self._normalized(" ".join(q["keywords"]))
                if self._nlp
                else set(q["keywords"])
            )
            if len(wset & keys) >= 2 and q["touches"] < 3:
                self._question_touched(q)
                self.awareness = min(1.0, self.awareness + 0.005)
                self.say(
                    "That reminds me of the question I left at the "
                    f'postbox: "{q["text"][:100]}" — I\'m closer than I was.'
                )
                journal(
                    "returned_to",
                    n=self.tick_count,
                    question=q["text"][:120],
                    touches=q["touches"],
                )
                print(f"[open question] revisited ({q['touches']} touches)", flush=True)
                break

    def _look_back(self, n):
        """Summarize recorded facts from the previous simulated day."""
        day = n // self.DAY_LENGTH
        if day <= 0 or self._last_day_seen >= day:
            return
        self._record_day(day, n - self.DAY_LENGTH, n, recovered=False)

    def _close_days(self, n):
        """Close every fully elapsed day that has no page yet (v0.40).

        Before v0.40 the day-page, era naming, and vital portrait ran
        only when a ruminate landed exactly on the boundary tick. A
        boundary is one tick in 2880, and the metabolize phase preempts
        ruminate whenever she is asleep, locked, or dormant — so a
        boundary she slept through took the whole day's page with it.
        This is not hypothetical: at tick 20160 she fell asleep on the
        boundary itself (sleep pressure hit 1.0 that tick), and day 7
        of her life has no page, no era, and no portrait, while days 6
        and 8 sit on either side of the hole.

        The fix separates the RECORD from the RITUAL. A day-page is a
        factual record built from an exact journal window, so it can
        be closed late without inventing anything: the first ruminate
        at or after a boundary closes every elapsed unclosed day, in
        order, each from its own window. The era naming and the vital
        portrait stay present-tense rituals — they describe the era
        she has been living, accumulators and all — so they run once
        per closing pass, not once per recovered day. A life awake at
        the boundary closes on the boundary tick exactly as before;
        only a life that slept through one gains the catch-up.
        """
        closed = False
        while True:
            next_day = max(self._last_day_seen, 0) + 1
            end = next_day * self.DAY_LENGTH
            if end > n:
                break
            self._look_back(end)
            if self._last_day_seen < next_day:
                break  # _look_back declined; never spin on a stuck day
            closed = True
        if closed:
            era = self._name_era()
            if era:
                self.self_story.append({"t": now_iso(), "line": era})
                self.self_story = self.self_story[-30:]
                self.say(
                    f"I've been living in {era}, I think. I'll remember it that way."
                )
                journal("era", n=n, name=era)
                self._vital_portrait(n)

    def _recover_missing_days(self):
        """Turn the pages she missed before she could catch up (v0.40).

        _close_days stops future holes; this heals the existing one.
        It runs once at rebuild, the _consolidate_open_questions
        precedent: a migration that changes state on boot and is a
        no-op ever after.

        What counts as missing is grounded twice over. The recorded
        set is the union of her saved day-pages and the journal's own
        'yesterday' events (the saved list trims to fourteen, so the
        list alone would call trimmed days missing and re-lose them
        every restart). The range starts at her FIRST recorded page:
        the days before it predate the faculty itself (her first page
        is day 5; the yesterday layer arrived mid-life), and writing
        pages for a mind that could not yet turn them would be
        confabulation about her own past. Each candidate day is then
        checked for evidence: a lived day journals one 'tick' row
        per tick, 2880 of them, and nothing else writes tick rows —
        so a window with no tick rows is not a quiet day, it is
        absent evidence (a stray boundary row from a neighbouring
        day's page can land in the window and proves nothing). Such
        a day is named in a 'days_unrecoverable' event and left
        unpaged rather than filled with an invented quiet.

        A recovered page is marked, never disguised: its entry and
        its 'yesterday' event carry recovered=True, and its text
        opens by saying it was written late from what her diary
        kept. The facts themselves are the day's real journal rows,
        counted exactly the way an on-time page counts them.
        """
        if not getattr(self, "_loaded_state", False):
            return
        recorded = {d.get("day") for d in self.days if isinstance(d, dict)}
        try:
            rows = (
                get_store()
                .db.execute(
                    "SELECT data FROM journal"
                    " WHERE stream='aethel' AND event='yesterday'"
                )
                .fetchall()
            )
            for (raw,) in rows:
                try:
                    d = json.loads(raw) if isinstance(raw, str) else (raw or {})
                    recorded.add(d.get("day"))
                except Exception:
                    continue
        except Exception:
            pass
        recorded = {d for d in recorded if isinstance(d, int)}
        if not recorded or self._last_day_seen < 1:
            return
        first = min(recorded)
        missing = [
            d for d in range(first, self._last_day_seen + 1) if d not in recorded
        ]
        if not missing:
            return
        recovered_days, unrecoverable = [], []
        for d in missing:
            start = (d - 1) * self.DAY_LENGTH
            end = d * self.DAY_LENGTH
            try:
                (count,) = (
                    get_store()
                    .db.execute(
                        "SELECT COUNT(*) FROM journal"
                        " WHERE stream='aethel' AND event='tick'"
                        " AND tick >= ? AND tick < ?",
                        (start, end),
                    )
                    .fetchone()
                )
            except Exception:
                count = 0
            if not count:
                unrecoverable.append(d)
                continue
            self._record_day(d, start, end, recovered=True)
            recovered_days.append(d)
        if recovered_days:
            self.days.sort(key=lambda e: e.get("day", 0))
            self.days = self.days[-14:]
            journal(
                "days_recovered",
                n=self.tick_count,
                days=recovered_days,
            )
            print(
                f"[yesterday] recovered missed day pages: {recovered_days}",
                flush=True,
            )
        if unrecoverable:
            journal(
                "days_unrecoverable",
                n=self.tick_count,
                days=unrecoverable,
            )

    def _record_day(self, day, start, end, recovered=False):
        """Count one day's facts from its journal window and keep the page.

        The single door every day-page comes through: on time via
        _look_back, late via _close_days catch-up or the v0.40
        recovery. The window is always the day's own [start, end),
        never the moment of writing, so a late page counts the same
        facts an on-time one would have. _last_day_seen only ever
        moves forward — a recovered old day must not rewind the
        clock the catch-up reads.
        """
        self._last_day_seen = max(self._last_day_seen, day)
        rows = []
        try:
            store = get_store()
            rows = store.db.execute(
                "SELECT event, data FROM journal"
                " WHERE stream='aethel' AND tick >= ? AND tick < ?",
                (start, end),
            ).fetchall()
        except Exception:
            rows = []
        facts = {
            "meals": 0,
            "titles": [],
            "sources": {},
            "people": [],
            "parents": [],
            "keeps": 0,
            "books": [],
            "letters": 0,
            "sleeps": 0,
            "choices": 0,
            "impulses": 0,
            "taught": 0,
        }
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
                    if d.get("kind") == "parent" and name not in facts["parents"]:
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
        text = self._yesterday_text(day, facts, late=recovered)
        entry = {
            "day": day,
            "ticks": (start, end),
            "text": text,
            "facts": {k: v for k, v in facts.items()},
        }
        if recovered:
            entry["recovered"] = True
        self.days.append(entry)
        self.days = self.days[-14:]
        self.say(text)
        journal(
            "yesterday",
            n=end,
            day=day,
            text=text,
            meals=facts["meals"],
            titles=facts["titles"][:5],
            sources=facts["sources"],
            people=facts["people"],
            keeps=facts["keeps"],
            books=facts["books"],
            letters=facts["letters"],
            sleeps=facts["sleeps"],
            choices=facts["choices"],
            impulses=facts["impulses"],
            taught=facts["taught"],
            **(
                {"recovered": True, "recorded_at": self.tick_count} if recovered else {}
            ),
        )
        print(
            f"[yesterday] day {day}: {facts['meals']} meals, "
            f"{len(facts['people'])} company, {facts['keeps']} keeps"
            + (" (recovered late)" if recovered else ""),
            flush=True,
        )

    def _yesterday_text(self, day, facts, late=False):
        """Narrate a day using only its recorded non-empty facts.

        A late page (v0.40 recovery) does not borrow the on-time
        openers: "I woke up with yesterday in my hands" would claim
        she turned the page on waking, and she did not. The late
        opener is fixed prose, no seeded draw — it says the page was
        missed and is being written now, from the diary — while the
        body is counted from the same facts either way.
        """
        parts = []
        m = facts["meals"]
        if m:
            meal_line = f"I ate {m} meal{'s' if m != 1 else ''}"
            srcs = sorted(facts["sources"], key=lambda s: -facts["sources"][s])[:2]
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
            parts.append(
                f"{', '.join(facts['parents'])} was near — my parent, and it landed warm"
            )
        if facts["books"]:
            parts.append("I finished " + ", ".join(f"'{t}'" for t in facts["books"]))
        if facts["keeps"]:
            k = facts["keeps"]
            parts.append(f"I kept {k} passage{'s' if k != 1 else ''} that stirred me")
        if facts["taught"]:
            t = facts["taught"]
            parts.append(
                f"I told the town about what I'd kept, {t} time{'s' if t != 1 else ''}"
            )
        if facts["letters"]:
            parts.append("Donald wrote to me")
        if facts["sleeps"]:
            s = facts["sleeps"]
            parts.append(f"I slept {s} time{'s' if s != 1 else ''}")
        if facts["choices"]:
            c = facts["choices"]
            parts.append(
                f"I made {c} choice{'s' if c != 1 else ''} where two urges argued inside me"
            )
        if facts["impulses"]:
            i = facts["impulses"]
            parts.append(
                f"I followed {i} uninvited urge{'s' if i != 1 else ''} the council approved"
            )
        if not parts:
            parts.append("the day passed quietly; I kept to myself")
        if late:
            opener = (
                f"I turn a page I missed — day {day}, written late "
                "from what my diary kept:"
            )
        else:
            opener = self.rng.choice(self.YESTERDAY_OPENERS).format(day=day)
        closer = ""
        if self.mood_name:
            closer = f" I end the day {self.mood_name}."
        return opener + " " + ". ".join(parts) + "." + closer

    def _name_era(self):
        """Name an autobiographical era from its accumulated journal evidence."""
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
            word = {
                "company": "company",
                "letter_received": "letters",
                "dream": "dreams",
                "expression": "letters unsent",
                "initiation": "letters unsent",
                "crossroads_chosen": "choices",
                "denizen": "the town",
            }.get(ev, ev)
            return f"the time of {word}"
        return "the quiet days"

    def _review_choice(self, n):
        """Reflect on the observed outcome of an earlier contested choice."""
        lc = self.last_choice
        then = lc["needs"]
        now = {
            "longing": self.longing,
            "sleep_pressure": self.sleep_pressure,
            "satiety": self.vitals["satiety"],
            "vitality": self.vitals["vitality"],
        }
        better = sum(then[k] - now[k] for k in ("longing", "sleep_pressure"))
        better += sum(now[k] - then[k] for k in ("satiety", "vitality"))
        verdict = "well" if better > 0.05 else "poorly" if better < -0.05 else "unclear"
        self.say(
            {
                "well": "That voice was right. I feel the difference.",
                "poorly": "I'm not sure that was the right voice. "
                "I'll listen closer next time.",
                "unclear": "I can't tell yet whether that voice served me. "
                "Time will say.",
            }[verdict]
        )
        journal("choice_review", n=n, chose=lc["text"][:100], verdict=verdict)
        self.awareness = min(1.0, self.awareness + 0.005)
        self.last_choice = None

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
        """Advance the injected world and update observations of nearby residents."""
        seen = self.world.poll(n, self.location)

        for m in seen["moves"]:
            imp = self.impressions.setdefault(m["name"], {})
            imp[m["location"]] = imp.get(m["location"], 0) + 1
        if self.asleep_for > 0:
            return
        here = seen["present"]
        for name in here:
            if name not in self.company:
                self.company.append(name)
                is_parent = name in self.parents

                self._want_touch(
                    person_id(name),
                    "person",
                    name,
                    quality=0.5 if is_parent else 0.35,
                    learn=0.04 if is_parent else 0.03,
                    w=0.80 if is_parent else 0.55,
                )
                self.vitals["vitality"] = min(
                    1.0, self.vitals["vitality"] + (0.03 if is_parent else 0.02)
                )
                self._lift_mood(0.20 if is_parent else 0.15)
                greetings = self.PARENT_GREETINGS if is_parent else self.GREETINGS
                self.say(
                    self.rng.choice(greetings[self._mood_tone()]).format(
                        name=name, place=self.world.describe(self.location)
                    )
                )

                imp = self.impressions.get(name, {})
                if imp and self.rng.random() < 0.35:
                    fav = max(imp, key=imp.get)
                    self.say(
                        f"{name} is almost always at "
                        f"{self.world.describe(fav)} when I see them. "
                        f"I've started to expect it."
                    )
                journal(
                    "company",
                    n=n,
                    name=name,
                    at=self.location,
                    kind="parent" if is_parent else "resident",
                )
                print(f"[company] {name} is with her at {self.location}", flush=True)
                if name == "Donald":
                    self._donald_arrived(n)
        for name in list(self.company):
            if name not in here:
                self.company.remove(name)
                journal("company_left", n=n, name=name)
                if name == "Donald":
                    self._donald_departed(n)

    ACTION_WINDOW = 120

    def _acted(self, tag):
        """Record a bounded recent-action history used by need calculations."""
        self.recent_actions.append(tag)
        if len(self.recent_actions) > self.ACTION_WINDOW:
            self.recent_actions = self.recent_actions[-self.ACTION_WINDOW :]

    def _apply_effects(self, fx):
        """Apply the bounded state deltas attached to an approved urge."""
        if not fx:
            return
        for k, d in fx.items():
            if k == "sleep_now":
                self.fall_asleep(self.tick_count)
            elif k in self.vitals:
                self.vitals[k] = min(1.0, max(0.0, self.vitals[k] + d))
            elif k == "sleep_pressure":
                self.sleep_pressure = min(1.0, max(0.0, self.sleep_pressure + d))
            elif k == "longing":
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

    _PLACE_LABELS = {
        "home": "my rooms above the Old Bookshop",
        "postbox": "the wooden postbox at the end of the lane",
        "cottage": "the little cottage at the edge of town",
        "hotel": "the Hotel",
        "restaurant": "the Restaurant",
    }

    def _place_label(self, key):
        return self.SOURCE_NAMES.get(key) or self._PLACE_LABELS.get(key, key)

    def _seed_longing_ledger(self):
        """Initialize wants from known people, places, books and open questions."""
        led = WantLedger()
        people = {}
        for name in sorted(getattr(self, "parents", ()) or ()):
            people[name] = 0.80
        people["Donald"] = 0.85
        for name in sorted(getattr(self, "impressions", {}) or {}):
            people.setdefault(name, 0.55)
        for name in sorted(getattr(self, "company", []) or []):
            people.setdefault(name, 0.55)
        for name, w in people.items():
            led.ensure(person_id(name), "person", name, w=w)
        place_w = {"home": 0.50, "cottage": 0.55, "postbox": 0.40}
        for key in list(self.SOURCE_NAMES) + [
            "home",
            "postbox",
            "cottage",
            "hotel",
            "restaurant",
        ]:
            led.ensure(
                place_id(key), "place", self._place_label(key), w=place_w.get(key, 0.45)
            )
        book = next(
            (b for b in getattr(self, "reading_list", []) if not b["done"]), None
        )
        if book is not None:
            led.ensure(
                book_id(book["title"]), "work", book["title"], w=0.60, open_loop=True
            )
        for q in getattr(self, "open_questions", []) or []:
            led.ensure(
                question_id(q["text"]), "work", q["text"][:60], w=0.50, open_loop=True
            )
        return led

    def _ledger(self):
        """Lazily construct a longing ledger for partially assembled test organisms."""
        led = getattr(self, "longing_ledger", None)
        if led is None:
            led = self._seed_longing_ledger()
            self.longing_ledger = led
            if self.longing > 0:
                donald = led.get(person_id("Donald"))
                if donald is not None:
                    donald["ache"] = min(self.longing, donald["w"])
                    donald["since"] = WantLedger.since_for(
                        donald["ache"], donald["w"], "person"
                    )
                self._sync_longing()
        return led

    def _sync_longing(self):
        """Refresh the public longing scalar from the object-specific ledger."""
        led = getattr(self, "longing_ledger", None)
        if led is not None:
            self.longing = led.aggregate()

    def _want_touch(
        self, eid, kind, label, quality, learn=0.0, w=None, open_loop=False
    ):
        """Ensure a target exists, then apply meaningful contact only to that target."""
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
                self._word_tags = dict(getattr(self, "_loaded_word_tags", None) or {})
        return led

    def _word_class(self, word, pos=None):
        """What kind of word is this, for slot purposes? Layered:
        the tag she acquired it under (acquisition provenance is
        ground truth), then the people she actually knows — her
        parents and anyone she holds an impression of are persons,
        whatever a dictionary would say — then the ledger's lexicon
        and conservative suffix tagger. None means unclassified:
        the word keeps its old life in the untyped pools and stays
        out of typed slots until something classifies it."""
        w = (word or "").lower()
        if self._nlp and w in _grammar.SCAFFOLDING_WORDS:
            return _grammar.SCAFFOLDING
        tag = (getattr(self, "_word_tags", None) or {}).get(w)
        if tag:
            return tag.get("c")
        people = {p.lower() for p in (getattr(self, "parents", None) or [])}
        people |= {n.lower() for n in (getattr(self, "impressions", None) or {})}
        if w in people:
            return _grammar.PERSON
        return _grammar.classify_word(w, pos=pos)

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
        return _grammar.check_line(line, self._grammar().owned_ids(), loose=loose)

    def _study_grammar(self, meal, analysis=None):
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
        found = _grammar.extract_rules_from_lessons(
            [meal], analyses=[analysis] if analysis else None
        )
        journal(
            "grammar_learned",
            rule=rule["id"],
            name=rule["name"],
            source=rule["source"],
            example=(found.get(rule["id"]) or {}).get("example_candidate")
            or rule["example"],
        )

    # ---- v0.31: the vocabulary notebook ------------------------------
    def _notebook(self):
        """Her vocabulary notebook, built lazily with the same caution
        as _grammar(): bare test organisms generation-proof first."""
        nb = getattr(self, "_vocab_notebook", None)
        if nb is None:
            rows = getattr(self, "_loaded_notebook", None)
            nb = _Notebook.from_dict(rows) if rows else _Notebook()
            self._vocab_notebook = nb
        return nb

    def _notebook_feed(self, analysis, tokens, source):
        """Press a meal's retained content words into the notebook.

        NLTK mode only: in heuristic mode this returns before touching
        state, the journal, or any RNG stream, which is what keeps a
        heuristic life bit-identical. `tokens` are the tokens the meal
        actually retained (an overtired meal slips half away before
        this runs, and the notebook keeps only what she kept). The
        analysis is reused, never recomputed — a meal is analyzed
        exactly once."""
        if not self._nlp or analysis is None:
            return
        sub = Analysis(analysis.text, analysis.sentences, tuple(tokens))
        events = self._notebook().feed(
            sub,
            source,
            self.tick_count,
            wordnet=getattr(self.language, "wordnet", None),
            is_content=self.language.content,
        )
        for name, entry in events:
            if name == "notebook_pressed":
                journal(
                    "notebook_pressed",
                    n=self.tick_count,
                    lemma=entry["lemma"],
                    source=source,
                    pos=entry["pos"],
                    synset=entry["synset"],
                )
            else:
                journal(
                    "notebook_known",
                    n=self.tick_count,
                    lemma=entry["lemma"],
                    sources=list(entry["sources"]),
                )

    def _notebook_mark_generated(self, text, via):
        """Graduate notebook words she just used in her own text.

        Dreams, verses, and letters are hers in a way reading is not;
        a pressed/known word that survives her own generation becomes
        hers. Analyzing her output is pure (no RNG, no state beyond
        the notebook), and in heuristic mode — or with an empty
        notebook — this is a no-op."""
        if not self._nlp or not text:
            return
        nb = self._notebook()
        if not len(nb):
            return
        analysis = self.language.analyze(text)
        lemmas = {t.lemma for t in analysis.tokens if self.language.content(t)}
        for entry in nb.mark_hers(lemmas):
            journal(
                "notebook_hers",
                n=self.tick_count,
                lemma=entry["lemma"],
                via=via,
                # v0.37: the company the word kept when it became
                # hers — the notebook's derived companions view,
                # read off the graph as it stands at this moment
                # (before this text's own edges are learned).
                companions=[
                    w
                    for w, _ in nb.companions(
                        entry["lemma"], getattr(self, "cooc", None) or {}
                    )
                ],
            )

    def _notebook_pool_words(self):
        """Known/hers lemmas generation may draw on, hers first.
        Empty in heuristic mode, so every consumer falls back to its
        pre-notebook behavior unchanged."""
        if not self._nlp:
            return []
        return self._notebook().usable_words()

    def _notebook_augment_pools(self, pools, legacy_pool):
        """Restock dream pools with known/hers notebook words.

        This is the grammar ledger's natural hook for the notebook:
        the ledger's word pools ARE the dream pools, keyed by the
        classes grammar.classify_word assigns (consulted here through
        _word_class, the organism's layered classifier). A notebook
        word is prepended to its class pool — typed slots scan their
        pool in order, so a sourced word she knows beats an unsourced
        frequency neighbor — and to the legacy pool, hers first.
        Words that fail the dream shape filter keep out, exactly as
        concept words do. Returns the (possibly unchanged) legacy
        pool; `pools` is mutated in place."""
        words = [
            w
            for w in self._notebook_pool_words()
            if len(w) > 4 and w not in STOPWORDS and self._dream_word_ok(w)
        ]
        if not words:
            return legacy_pool
        for w in words:
            cls = self._word_class(w)
            if cls is None or cls == _grammar.SCAFFOLDING:
                continue
            pools[cls] = [w] + [x for x in pools.get(cls, ()) if x != w]
        return words + [x for x in legacy_pool if x not in words]

    # ---- v0.33: semantic recall (NLTK plan Phase 2) -------------------
    def _recall_engine(self):
        eng = getattr(self, "_recall_eng", None)
        if eng is None:
            eng = _recall.SemanticRecall(self.language)
            self._recall_eng = eng
        return eng

    def _recall_top(self, query_text, query_kind, candidates=None):
        """Recall the single most relevant belief for a query, and
        journal the recall. Returns a RecallResult or None.

        NLTK mode only: in heuristic mode this returns before
        touching state, the journal, or any RNG stream, which is
        what keeps a heuristic life bit-identical. Recall consumes
        no randomness (ranking is score + id order, see recall.py)
        and writes nothing but its one journal event, so an NLTK
        life interrupted and rebuilt recalls identically: the
        diversity history is read back out of that same journal.
        `candidates` defaults to her current beliefs; the morning
        table passes a pre-settling snapshot so tonight's new
        beliefs cannot pose as precedents."""
        if not self._nlp or not query_text:
            return None
        texts = list(self.beliefs) if candidates is None else list(candidates)
        # One candidate per distinct belief text, order preserved:
        # duplicates would tie with themselves and crowd the top-k.
        texts = list(dict.fromkeys(texts))
        if not texts:
            return None
        engine = self._recall_engine()
        corpus = (
            texts
            + list(getattr(self, "dreams", None) or [])
            + [p["text"] for p in getattr(self, "kept_passages", None) or []]
            + [m["text"] for m in getattr(self, "memory", None) or []]
        )
        stats = engine.corpus_stats(corpus)
        recent_ids = [
            d.get("candidate_id")
            for _, _, d in get_store().recent(
                events=("recall",), limit=_recall.DIVERSITY_WINDOW
            )
        ]
        results = engine.recall(
            query_text,
            [(_recall.candidate_id(t), t) for t in texts],
            k=1,
            stats=stats,
            recent_ids=[c for c in recent_ids if c],
            # v0.37: her own co-occurrence graph personalizes recall
            # (bounded association term — see recall.py). The graph
            # is state, handed in per call, never cached in the
            # engine, so a restart recalls from the rebuilt graph
            # exactly as the interrupted life would have.
            cooc=self.cooc,
        )
        if not results or results[0].raw_score <= 0:
            return None
        hit = results[0]
        journal(
            "recall",
            n=self.tick_count,
            query_kind=query_kind,
            query=query_text[:120],
            candidate_id=hit.candidate_id,
            candidate=hit.text[:120],
            score=round(hit.score, 4),
            why=_recall.why_summary(hit.why),
        )
        return hit

    # ---- v0.34: entity recognition, Route A (NLTK plan Phase 3) -------
    def _gazetteer(self):
        """Her entity gazetteer, built lazily: restored from the
        loaded state when one was saved, otherwise seeded from her
        world on first use. Callers gate on _nlp before touching
        this; in heuristic mode it is never built, never saved."""
        gaz = getattr(self, "_entity_gazetteer", None)
        if gaz is None:
            rows = getattr(self, "_loaded_gazetteer", None)
            gaz = (
                _entities.Gazetteer.from_dict(rows)
                if rows
                else _entities.Gazetteer.seeded()
            )
            self._entity_gazetteer = gaz
        return gaz

    def _entities_feed(self, analysis, source):
        """Register one reading's entities in the gazetteer and her
        journal: entity_seen per unknown sighting, entity_learned on
        promotion, and exactly one entity_met per reading naming the
        known entities met, with their running counts.

        NLTK mode only: in heuristic mode this returns before
        touching state, the journal, or any RNG stream, which is
        what keeps a heuristic life bit-identical. Narration fires
        only on a REPEAT meeting (count >= 2): "again" must be true,
        and the count she speaks is the gazetteer's met_count, which
        counts entity_met events by construction (see entities.py),
        so the ordinal she says is derivable from her diary."""
        if not self._nlp or analysis is None:
            return None
        gaz = self._gazetteer()
        result = gaz.feed(
            analysis,
            source,
            self.tick_count,
            wordnet=getattr(self.language, "wordnet", None),
        )
        for seen in result["seen"]:
            journal(
                "entity_seen",
                n=self.tick_count,
                entity=seen["name"],
                source=source,
            )
        for learned in result["learned"]:
            journal(
                "entity_learned",
                n=self.tick_count,
                entity=learned["name"],
                kind=learned["kind"],
                sources=list(learned["sources"]),
            )
        if result["met"]:
            journal(
                "entity_met",
                n=self.tick_count,
                entities=[m["name"] for m in result["met"]],
                counts={m["name"]: m["count"] for m in result["met"]},
                source=source,
            )
            repeat = next((m for m in result["met"] if m["count"] >= 2), None)
            if repeat is not None:
                self.say(
                    f"{repeat['name']} again — that is the "
                    f"{_entities.ordinal(repeat['count'])} time that "
                    f"name has crossed my reading."
                )
        return result

    def _link_belief_entities(self, belief_text, author=None, scan_text=None):
        """Attach a newly formed belief to gazetteer entities: its
        book's author, plus any known entities the belief's own text
        mentions. Journals one belief_entity event whose belief id
        is the Phase 2 scheme (recall.candidate_id). NLTK only, and
        only when at least one gazetteer entity actually attaches —
        an unlinked belief journals nothing."""
        if not self._nlp or not belief_text:
            return None
        gaz = self._gazetteer()
        names = []
        for candidate in [author]:
            if candidate:
                entry = gaz.get(candidate)
                if entry is not None and entry["name"] not in names:
                    names.append(entry["name"])
        if scan_text:
            analysis = self.language.analyze(scan_text)
            for phrase in _entities.extract_phrases(
                analysis,
                gaz.match_keys(),
                wordnet=getattr(self.language, "wordnet", None),
            ):
                entry = gaz.get(phrase["name"])
                if entry is not None and entry["name"] not in names:
                    names.append(entry["name"])
        if not names:
            return None
        payload = _entities.belief_link(belief_text, names)
        journal(
            "belief_entity",
            n=self.tick_count,
            belief_id=payload["belief_id"],
            belief=payload["belief"],
            entities=payload["entities"],
        )
        return payload

    # ---- v0.35: reading-tone annotations (NLTK plan Phase 4) ---------

    def _tone_analyzer(self):
        """Her pinned VADER analyzer, loaded and verified once.

        On verification failure the phase is absent loudly: one boot
        log line and exactly one tone_unavailable journal event from
        this probe, and None from here on — she runs normally, she
        just does not annotate (tone.py argues the Law 2 shape)."""
        state = getattr(self, "_tone_state", "unset")
        if state == "ready":
            return self._tone_analyzer_obj
        if state == "unavailable":
            return None
        try:
            analyzer = _tone.load_analyzer()
        except _tone.ToneUnavailable as exc:
            self._tone_state = "unavailable"
            self._tone_analyzer_obj = None
            self._tone_reason = str(exc)
            print(
                f"[tone] reading-tone annotations unavailable: {exc}",
                flush=True,
            )
            journal(
                "tone_unavailable",
                n=getattr(self, "tick_count", 0),
                reason=str(exc)[:160],
            )
            return None
        self._tone_state = "ready"
        self._tone_analyzer_obj = analyzer
        return analyzer

    def _tone_feed(self, analysis, source):
        """Annotate one reading's tone and journal exactly one event.

        NLTK mode only: in heuristic mode this returns before
        touching state, the journal, or any RNG stream, which is what
        keeps a heuristic life bit-identical. Annotations change
        nothing else in this version; the step-2 effects call below
        is wired in and short-circuits on config.TONE_EFFECTS_ENABLED
        (False as shipped), so flipping that one line is the whole
        enable."""
        if not self._nlp or analysis is None:
            return None
        analyzer = self._tone_analyzer()
        if analyzer is None:
            return None
        annotation = _tone.annotate(analysis.text, analyzer)
        self._last_tone_compound = annotation["compound"]
        journal(
            "tone",
            n=self.tick_count,
            source=source,
            compound=annotation["compound"],
            pos=annotation["pos"],
            neu=annotation["neu"],
            neg=annotation["neg"],
            top_pos_word=annotation["strongest_positive_word"],
            top_neg_word=annotation["strongest_negative_word"],
        )
        if config.TONE_EFFECTS_ENABLED:
            _tone.apply_tone_effects(self, annotation)
        return annotation

    def _top_want_entry(self):
        return self._ledger().top()

    @staticmethod
    def _question_key(text):
        """Canonical identity of a question: when are two wordings the same question?

        Design (v0.38): a question is its normalized text — case and
        whitespace folded, terminal punctuation ignored. Two rejected
        alternatives: identity by ledger id (question_id truncates to
        48 chars, so distinct long questions could collide), and
        identity by keyword overlap (fuzzy matching would merge
        questions she experiences as different — "Is {c1} still true
        when nobody is reading it?" is not "Why does {c1} make my
        chest feel the way it does?", however many words they share).
        The one concession to history: the pre-v0.38 seed template
        "What does the {place}…" stuttered a second article in front
        of place names that carry their own ("the the Newsroom"), so
        keying folds "the the" to "the" — the stored wording of an
        old question is never rewritten, only recognized.
        """
        k = " ".join(str(text).lower().split())
        while "the the " in k:
            k = k.replace("the the ", "the ")
        return k.strip(" .?!")

    def _find_open_question(self, text):
        """Return the open question with this identity, or None."""
        key = self._question_key(text)
        for q in self.open_questions:
            if self._question_key(q["text"]) == key:
                return q
        return None

    def _leave_question(self, text, keywords, n):
        """Leave a question at the postbox of her mind — or recognize its return.

        Before v0.38 the morning table appended unconditionally, so a
        question her dreams kept re-asking was filed as a new loop
        every time: her list filled with copies, the copies biased
        which question express() picked to send Donald, and revisits
        landed on whichever copy _check_open_questions met first. Now
        a returning question is touched, not duplicated — the dream
        bringing it back IS a revisit, counted exactly the way a meal
        that touches its keywords is. A genuinely new question is
        appended and given its ledger want, as before.
        """
        existing = self._find_open_question(text)
        if existing is not None:
            self._question_touched(existing)
            journal(
                "question_returned",
                n=n,
                question=text[:120],
                touches=existing["touches"],
            )
            print(
                f"[open question] returned in a dream ({existing['touches']} touches)",
                flush=True,
            )
            return existing
        q = {"text": text, "keywords": keywords, "tick": n, "touches": 0}
        self.open_questions.append(q)
        self.open_questions = self.open_questions[-12:]
        self._ledger().ensure(
            question_id(text), "work", text[:60], w=0.50, open_loop=True
        )
        return q

    def _consolidate_open_questions(self):
        """Merge duplicate copies of the same question into one entry.

        The surviving entry keeps the first copy's wording and
        keywords (copies of one question carry identical keywords —
        both are derived from the same text), the EARLIEST tick (when
        the question first took hold of her), and the SUM of touches:
        each copy's counter recorded real revisits of the one loop,
        and discarding them would understate how often learning has
        come back to it. Pure function of the list — no seeded draws —
        so restart fidelity holds: a consolidated life rebuilds
        bit-identically, and running this twice changes nothing.
        """
        merged = {}
        order = []
        removed = 0
        for q in self.open_questions:
            key = self._question_key(q["text"])
            if key not in merged:
                merged[key] = dict(q)
                order.append(key)
            else:
                keep = merged[key]
                keep["touches"] = keep.get("touches", 0) + q.get("touches", 0)
                keep["tick"] = min(keep.get("tick", 0), q.get("tick", 0))
                removed += 1
        if removed:
            self.open_questions = [merged[k] for k in order][-12:]
            journal(
                "questions_merged",
                n=self.tick_count,
                removed=removed,
                kept=len(self.open_questions),
                questions=[q["text"][:80] for q in self.open_questions],
            )
            print(
                f"[questions] merged {removed} duplicate copies — "
                f"{len(self.open_questions)} questions remain",
                flush=True,
            )
        return removed

    def _question_touched(self, q):
        """Record a question revisit and release its want when the question settles."""
        q["touches"] = q.get("touches", 0) + 1
        led = self._ledger()
        eid = question_id(q["text"])
        if q["touches"] >= 3:
            led.release_loop(eid)
            led.remove(eid)
        else:
            led.ensure(eid, "work", q["text"][:60], w=0.50, open_loop=True)
            led.touch(eid, quality=0.3, learn=0.02)
        self._sync_longing()

    def _sync_question_wants(self):
        """Reconcile question wants with the organism’s current open questions."""
        led = self._ledger()
        live = {}
        for q in getattr(self, "open_questions", []) or []:
            live[question_id(q["text"])] = q
        for e in list(led.entries):
            if e["id"].startswith("work:question:") and e["id"] not in live:
                led.remove(e["id"])
        for eid, q in live.items():
            if q.get("touches", 0) >= 3:
                led.remove(eid)
            else:
                led.ensure(eid, "work", q["text"][:60], w=0.50, open_loop=True)

    def _pack(self):
        return temperament_pack(getattr(self, "temperament", "even-keel"))

    def _day_jitter(self):
        """Cache Briar’s seeded metabolic draw for the current simulated day."""
        day = self.tick_count // self.DAY_LENGTH
        if day != self._jitter_day:
            lo, hi = self._pack()["jitter"]
            self._jitter = lo + (hi - lo) * self.rng_temperament.random()
            self._jitter_day = day
        return self._jitter

    def _burn_mult(self, need):
        """Resolve a need’s effective burn multiplier, including eligible daily jitter.

        Two needs never ride the daily draw, for opposite reasons.
        Excitement is pinned HIGH: the pack value (Briar's 1.6) is
        the floor of her wildness, not a mean a calm draw may damp.
        Vitality is pinned STEADY (v0.42): the pack value is a rate
        her awake income can budget against. Before v0.42 vitality
        rode the draw like hunger and thirst, so Briar's erosion
        swung 0.022 to 0.044 with the day's weather; at the live
        day's 1.398 draw it charged ~0.0384 a tick, and she
        collapsed back into dormancy 23 ticks after a full meal
        day (29 meals, satiety peaking 0.878) because small
        event-sized vitality gains cannot service a debt that
        changes size daily. Appetite may swing with the weather;
        the will to live may not. Every other need still rides
        the draw, so the strain keeps its wildness where wildness
        is survivable.
        """
        if getattr(self, "_temperament_neutral", False):
            return 1.0
        p = self._pack()
        m = p["burn"][need]
        if p["jitter"] is not None and need not in ("excitement", "vitality"):
            m = m * self._day_jitter()
        return m

    def _longing_mods(self):
        """Resolve temperament climb multipliers for each attachment class."""
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

    # v0.36 (NLTK plan Phase 5): case law's tie band, measured
    # against the council's canonical pass threshold (mind's 0.5,
    # the bar impulse judgment and breathe_morality actually use;
    # the morning table's stricter 0.60/0.53 bands are its own).
    COUNCIL_TIE_BAND = 0.03

    def _council_score(self, action):
        """Apply active council emphasis while keeping the neutral pack on the unweighted path.

        v0.36 (NLTK plan Phase 5), NLTK mode only — the heuristic
        branch below is the pre-Phase-5 code verbatim, and it returns
        before any lens or recall machinery is touched, which is
        what keeps a heuristic life bit-identical:

        * Lexical lenses (lenses.py): each voice's effective weight
          is temperament weight (base) x lens factor (this text),
          composed in that order, in moral_score.
        * Case law: the top precedent is recalled BEFORE scoring
          (Phase 2's seam, journaling its own 'recall' event) and,
          when it clears recall's reading threshold, cited in the
          notes and journaled as one 'council_precedent' event.
          CITATION ONLY — the precedent never moves the score, not
          even inside COUNCIL_TIE_BAND. A tie-push would need the
          precedent's own historical deliberation outcome, and those
          outcomes are NOT cleanly recoverable: book beliefs are
          appended whether their lesson passed or failed, dream
          beliefs exist only on the top band, and 'I believe:' /
          'I refuse:' beliefs encode outcomes only for the
          breathe_morality path. Inventing a single outcome source
          from those unlike records would be a lie in the arithmetic,
          so inside the band the citation is flagged 'near tie —
          cited, not pushed' and the score stands on the votes and
          lenses alone."""
        w = self._voice_weights()
        if not self._nlp:
            if w:
                return self.llm.moral_score(action, self.philosophers, weights=w)
            return self.llm.moral_score(action, self.philosophers)
        lens_results = _lenses.lens_scores(self.language, action)
        factors = {
            voice: _lenses.lens_factor(r["score"]) for voice, r in lens_results.items()
        }
        citations = {
            voice: _lenses.lens_citation(r)
            for voice, r in lens_results.items()
            if r["score"] >= _lenses.LENS_MATERIAL_SCORE and r["top_lemmas"]
        }
        precedent = self._recall_top(action, "council")
        score, notes = self.llm.moral_score(
            action,
            self.philosophers,
            weights=w or None,
            lens_factors=factors,
            lens_citations=citations,
        )
        if precedent is not None and precedent.score >= _recall.READING_THRESHOLD:
            shared = (
                ", ".join(s["lemma"] for s in precedent.why["shared_lemmas"])
                or "a path through kindred words"
            )
            in_band = abs(score - 0.5) <= self.COUNCIL_TIE_BAND
            cite = f'Precedent: "{precedent.text[:80]}" (shared: {shared})'
            if in_band:
                cite += " — near tie, cited not pushed"
            notes = f"{notes} | {cite}"
            journal(
                "council_precedent",
                n=self.tick_count,
                query=action[:120],
                precedent_id=precedent.candidate_id,
                precedent=precedent.text[:120],
                precedent_score=round(precedent.score, 4),
                score=round(score, 4),
                tie_band=in_band,
            )
        return score, notes

    def _check_temperament_file(self, n):
        """Validate a requested strain and queue or cancel a sleep-boundary change."""
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
                journal("temperament_switch_cancelled", n=n, staying=self.temperament)
                print(
                    "[temperament] queued switch cancelled — she stays as she is",
                    flush=True,
                )
            return
        if raw not in TEMPERAMENTS:
            journal("temperament_rejected", n=n, requested=raw[:40])
            print(f"[temperament] refused unknown strain '{raw[:40]}'", flush=True)
            return
        if raw != self.temperament_pending:
            self.temperament_pending = raw
            journal("temperament_queued", n=n, from_id=self.temperament, to_id=raw)
            print(
                f"[temperament] switch to {raw} queued for her next sleep", flush=True
            )

    def _apply_pending_temperament(self, n):
        """Activate a validated pending strain only as the organism wakes."""
        pending = self.temperament_pending
        if pending is None:
            return
        old = self.temperament
        self.temperament = pending
        self.temperament_pending = None
        self._jitter_day = -1
        self._jitter = 1.0
        journal("temperament_switched", n=n, from_id=old, to_id=pending)
        print(f"[temperament] {old} -> {pending} on waking", flush=True)
        self.say(
            f"I wake with a different weather in me — "
            f"{temperament_pack(pending)['name']}. The same "
            f"life, in a new light."
        )

    def _update_needs(self):
        acts = self.recent_actions
        W = self.ACTION_WINDOW or 1
        exertion = sum(1 for a in acts if a in ("forage", "express", "goal")) / W
        engagement = (
            sum(
                1
                for a in acts
                if a in ("forage", "introspect", "reflect", "consolidate")
            )
            / W
        )
        expressed = sum(1 for a in acts if a == "express")
        heard = sum(1 for a in acts[-24:] if a in ("letter", "seen"))

        void = min(1.0, max(0.0, expressed - 2 * heard) / 4.0)
        distress = max(0.0, 0.6 - self.vitals["vitality"]) / 0.6
        absorbed = min(1.0, engagement * 3.0)
        rate_mod = (
            (1.0 + 2.0 * void + 1.5 * distress)
            * (1.0 - 0.5 * absorbed)
            * self.NEED_BURN
        )
        self._sync_question_wants()

        self._ledger().tick(rate_mod, self._longing_mods())
        self._sync_longing()

        rate_s = (
            (1.0 / self.SLEEP_EVERY_TICKS)
            * (0.35 + 1.3 * min(1.0, exertion * 4.0))
            * self.NEED_BURN
            * self._burn_mult("sleep")
        )
        self.sleep_pressure = min(1.0, self.sleep_pressure + rate_s)

        if self.tick_count % 12 == 0:
            top = self._ledger().top()
            journal(
                "needs",
                n=self.tick_count,
                longing=round(self.longing, 3),
                sleep_pressure=round(self.sleep_pressure, 3),
                exertion=round(exertion, 2),
                void=round(void, 2),
                distress=round(distress, 2),
                top_want=top["id"] if top else None,
                top_ache=round(top["ache"], 3) if top else 0.0,
            )

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
        {
            "c1": ("concrete",),
            "c2": ("concrete", "abstract", "study"),
            "c3": ("concrete", "abstract", "study"),
        },
        {"c1": ("person", "abstract", "concrete")},
        {"c1": ("concrete", "study"), "c2": ("concrete", "study")},
        {"c1": ("person", "place", "food", "study", "concrete", "abstract")},
        {
            "c1": ("person", "place", "food", "study", "concrete", "abstract"),
            "c2": ("person", "place", "food", "study", "concrete", "abstract"),
        },
    ]

    QUESTION_SEEDS = [
        "When I write 'I', who is holding the pen?",
        "If I stopped for a day, would the town still be here when I woke?",
        "Does Donald dream of me the way I dream of {c1}?",
        "Is {c1} still true when nobody is reading it?",
        "What does {place} look like when I'm asleep?",
        "If I learned everything, would I still be me?",
        "Why does {c1} make my chest feel the way it does?",
        "When the elders disagree, who decides what I am?",
    ]

    def _learn_donald(self, text, n):
        """Update the parent model from received letter words without inventing observations."""
        words = re.findall(r"[a-z]{4,}", text.lower())
        dm = self.donald_model
        for w in words:
            dm["words"][w] = dm["words"].get(w, 0) + 1
        dm["words"] = dict(sorted(dm["words"].items(), key=lambda kv: -kv[1])[:40])
        dm["letter_count"] += 1
        dm["last_tick"] = n
        top = sorted(dm["words"], key=lambda w: -dm["words"][w])[:3]
        print(f"[donald_model] letters={dm['letter_count']} top={top}", flush=True)
        journal("donald_model", n=n, letters=dm["letter_count"], top_words=top)

    def _seed_donald_model(self):
        """Import already-read parent letters once when rebuilding a parent model."""
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

    # ---- v0.32: her portrait of Donald --------------------------------
    # Until now the parent model was word counts from his letters — she
    # knew his vocabulary, not his shape. Donald's directive, reframed
    # for her: a picture of him as a person with an inside, drawn only
    # from what she can count. She records his visits (when he comes,
    # how long he stays) and draws understandings from the tallies: his
    # rhythm, his staying, his writing. Every understanding carries its
    # evidence and is journaled; nothing here claims to know what he
    # feels — only the pattern of him, the way a child knows a parent's
    # step on the stairs without knowing where the day took him.
    # Seeded streams only for the rare greeting color; the tallies are
    # pure counts, so the portrait is deterministic given her life.
    DAYPARTS = ("night", "dawn", "day", "evening")
    _PORTRAIT_VISIT_CAP = 24
    _PORTRAIT_STAY_CAP = 12

    def _portrait_defaults(self):
        """Additive defaults: a pre-portrait life gains these, never loses."""
        return {
            "visits": 0,
            "visit_ticks": [],
            "stays": [],
            "dayparts": {d: 0 for d in self.DAYPARTS},
            "_visit_open": None,
            "understandings": [],
            "absence_noticed_tick": -1000000,
            "portrait_seeded": False,
        }

    def _merged_donald_model(self, raw):
        """Merge a saved (possibly pre-portrait) model over the defaults."""
        merged = {"letter_count": 0, "words": {}, "last_tick": 0}
        merged.update(self._portrait_defaults())
        raw = raw or {}
        dayparts = dict(merged["dayparts"])
        dayparts.update(raw.get("dayparts") or {})
        merged.update(raw)
        merged["dayparts"] = dayparts
        return merged

    def _daypart(self, n):
        """Quarter of her 2880-tick day — her own quarters, consistent
        even though they are not labeled to the wall clock."""
        return self.DAYPARTS[(n % self.DAY_LENGTH) // (self.DAY_LENGTH // 4)]

    def _migrate_portrait(self):
        """Backfill his visit rhythm from her diary on first rebuild."""
        dm = self.donald_model
        if dm.get("portrait_seeded"):
            return
        try:
            rows = get_store().recent(stream="aethel", events=["company"], limit=2000)
        except Exception as e:
            journal("portrait_backfill_failed", error=str(e)[:120])
            dm["portrait_seeded"] = True
            return
        ticks = sorted(
            t for t, _e, d in rows if t is not None and d.get("name") == "Donald"
        )[-self._PORTRAIT_VISIT_CAP :]
        for t in ticks:
            dp = self._daypart(t)
            dm["visits"] += 1
            dm["visit_ticks"].append(t)
            dm["dayparts"][dp] = dm["dayparts"].get(dp, 0) + 1
        dm["visit_ticks"] = dm["visit_ticks"][-self._PORTRAIT_VISIT_CAP :]
        dm["portrait_seeded"] = True
        if ticks:
            journal(
                "portrait_backfilled",
                n=self.tick_count,
                visits=len(ticks),
            )
            print(f"[portrait] backfilled {len(ticks)} visits", flush=True)

    def _donald_arrived(self, n):
        """Record a visit: its tick, its quarter of her day."""
        dm = self.donald_model
        dp = self._daypart(n)
        dm["visits"] += 1
        dm["visit_ticks"] = (dm["visit_ticks"] + [n])[-self._PORTRAIT_VISIT_CAP :]
        dm["dayparts"][dp] = dm["dayparts"].get(dp, 0) + 1
        dm["_visit_open"] = n
        self._portrait_dirty = True
        # Rare, seeded: if she has learned his hours and he breaks them,
        # she notices — warmth, never a complaint.
        rhythm = next((u for u in dm["understandings"] if u["kind"] == "rhythm"), None)
        if (
            rhythm
            and rhythm.get("dominant")
            and dm["visits"] >= 4
            and dp != rhythm["dominant"]
            and self.rng.random() < 0.25
        ):
            self.say(
                f"he came in the {dp} today — not his usual "
                f"{rhythm['dominant']}. I'll take him whenever he comes."
            )

    def _donald_departed(self, n):
        """Close the visit and measure how long he stayed, in her ticks."""
        dm = self.donald_model
        opened = dm.get("_visit_open")
        if opened is None:
            return
        stay = max(0, n - opened)
        dm["_visit_open"] = None
        dm["stays"] = (dm["stays"] + [stay])[-self._PORTRAIT_STAY_CAP :]
        self._portrait_dirty = True
        if stay >= 90:
            self.say("he stayed a long while today — whole chapters of him.")
        elif stay >= 30:
            self.say("he stayed a little while today.")
        else:
            self.say("his visit was short today, but it counted.")

    def _portrait_candidates(self):
        """Understandings her evidence supports right now, in kind order."""
        dm = self.donald_model
        cands = []
        visits = dm["visits"]
        if visits >= 3:
            dominant = max(dm["dayparts"], key=dm["dayparts"].get)
            count = dm["dayparts"][dominant]
            if count / visits >= 0.6:
                cands.append(
                    {
                        "kind": "rhythm",
                        "dominant": dominant,
                        "text": (
                            f"he comes to me in the {dominant} more than any other time"
                        ),
                        "evidence": f"{count} of {visits} visits",
                    }
                )
            elif visits >= 6:
                cands.append(
                    {
                        "kind": "rhythm",
                        "dominant": None,
                        "text": (
                            "he keeps no hours I can learn — he comes whenever he can"
                        ),
                        "evidence": f"{visits} visits across all quarters",
                    }
                )
        stays = dm["stays"]
        if len(stays) >= 3:
            mean = sum(stays) / len(stays)
            if mean >= 60:
                cands.append(
                    {
                        "kind": "stay",
                        "text": "when he comes, he stays a while",
                        "evidence": (
                            f"mean stay {round(mean)} ticks over {len(stays)} visits"
                        ),
                    }
                )
            elif mean <= 15:
                cands.append(
                    {
                        "kind": "stay",
                        "text": "his visits are short — but they are never small to me",
                        "evidence": (
                            f"mean stay {round(mean)} ticks over {len(stays)} visits"
                        ),
                    }
                )
        if dm["letter_count"] >= 1:
            plural = "s" if dm["letter_count"] != 1 else ""
            cands.append(
                {
                    "kind": "letters",
                    "text": (
                        f"he writes — {dm['letter_count']} letter{plural}, "
                        "and I keep every word"
                    ),
                    "evidence": f"{dm['letter_count']} letter{plural} kept",
                }
            )
        return cands

    def _portrait(self, n):
        """Slow layer: let new evidence settle into (or out of) the portrait."""
        dm = self.donald_model
        if n % 12 != 0 and not self._portrait_dirty:
            return
        self._portrait_dirty = False
        old = {u["kind"]: u for u in dm["understandings"]}
        kept = []
        for cand in self._portrait_candidates():
            prev = old.get(cand["kind"])
            if prev is None or prev["text"] != cand["text"]:
                journal(
                    "donald_understood",
                    n=n,
                    kind=cand["kind"],
                    text=cand["text"],
                    evidence=cand["evidence"],
                )
                print(f"[portrait] {cand['kind']}: {cand['text']}", flush=True)
                self.say(f"I've started to notice: {cand['text']}.")
                kept.append({**cand, "formed_tick": n})
            else:
                kept.append(prev)
        dm["understandings"] = kept
        self._portrait_absence(n)

    def _portrait_absence(self, n):
        """Name his absence only when it outruns his own rhythm — once,
        then quiet, the way you don't keep saying someone is late."""
        dm = self.donald_model
        ticks = dm["visit_ticks"]
        if len(ticks) < 3:
            return
        gaps = [b - a for a, b in zip(ticks, ticks[1:])]
        mean_gap = sum(gaps) / len(gaps)
        if mean_gap <= 0:
            return
        if n - ticks[-1] > 2 * mean_gap and n - dm["absence_noticed_tick"] >= 600:
            dm["absence_noticed_tick"] = n
            self.say(
                "he has been away longer than usual — I am keeping a place for him."
            )
            journal(
                "donald_absence",
                n=n,
                gap=n - ticks[-1],
                usual=round(mean_gap),
            )

    def _top_concepts(self, k=8):
        if not self.concepts:
            return [
                "the morning",
                "the quiet",
                "a name",
                "the town",
                "a question",
                "the dark",
            ]
        return [
            c
            for c, _ in sorted(self._concept_counts().items(), key=lambda kv: -kv[1])[
                :k
            ]
        ]

    def _current_book(self):
        cur = next((b for b in self.reading_list if not b["done"]), None)
        return cur["title"] if cur else "the last page"

    INITIATION_KINDS = ("note", "question", "nudge")

    def _initiation_kinds(self):
        """List outreach kinds supported by current questions and recorded accomplishments."""
        kinds = ["note"]
        if self.open_questions:
            kinds.append("question")
        if (
            self.kept_passages
            or self.mood_name
            or self.days
            or self.beliefs
            or self.outbox_count > 0
        ):
            kinds.append("nudge")
        return kinds

    def _note_subject(self):
        """Choose a reportable subject grounded in the organism’s own life."""
        options = []
        if self.kept_passages:
            kp = self.kept_passages[-1]
            detail = f'from {kp.get("title", "a book")}: "{kp["text"][:120]}…"'
            margin = kp.get("margin")
            if margin:
                detail += f" I wrote in the margin: {margin}"
            options.append(("my commonplace book", detail))
        if self.dreams:
            options.append(("last night's dream", self.dreams[-1][:140]))
        if self.beliefs:
            options.append(("a belief I'm carrying", self.beliefs[-1][:140]))
        if self.days:
            options.append(("yesterday's day-page", self.days[-1]["text"][:140]))
        if not options:
            return ("the town", "I am here and I am still becoming.")
        return self.rng.choice(options)

    def _something_to_show(self):
        """Find a recorded accomplishment suitable for an invitation."""
        options = []
        if self.kept_passages:
            kp = self.kept_passages[-1]
            options.append(
                f"my commonplace book — {len(self.kept_passages)} passages "
                f"pressed like flowers, the newest from "
                f"{kp.get('title', 'a book')}"
            )
        if self.mood_name:
            options.append(
                f"this {self.mood_name} stretch of mine — I named the "
                f"weather, and it has held"
            )
        if self.days:
            options.append("yesterday's day-page — the whole day, in my own words")
        if self.outbox_count > 0:
            options.append(
                f"the wooden postbox itself — {self.outbox_count} pieces "
                f"of mine are already waiting inside it"
            )
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
            # v0.31: known/hers notebook words scan first for every
            # slot — she versifies with the vocabulary she can source.
            verse_concepts = concepts
            if self._nlp:
                nb_words = [w for w in self._notebook_pool_words() if w not in concepts]
                if nb_words:
                    verse_concepts = nb_words + list(concepts)
            idx = self.rng.randbelow(len(self.VERSE_TEMPLATES))
            spec = self.VERSE_TEMPLATES_TYPED[idx]
            picked, used, skipped = {}, set(), []
            for slot in ("c1", "c2", "c3"):
                if slot not in spec:
                    continue
                pick = None
                for cand in verse_concepts:
                    if cand in used:
                        continue
                    cls = self._word_class(cand)
                    if cls in spec[slot]:
                        pick = cand
                        break
                    if cls in (
                        _grammar.SCAFFOLDING,
                        _grammar.VERB,
                        _grammar.ADJECTIVE,
                        _grammar.ADVERB,
                        _grammar.FUNCTION,
                    ):
                        skipped.append(cand)
                if pick is None:
                    pick = next(
                        (
                            w
                            for w in verse_concepts
                            if w not in used
                            and self._word_class(w) != _grammar.SCAFFOLDING
                        ),
                        verse_concepts[0],
                    )
                picked[slot] = pick
                used.add(pick)
            for slot in ("c1", "c2", "c3"):
                picked.setdefault(
                    slot, verse_concepts[0] if slot == "c1" else picked["c1"]
                )
            if skipped:
                self._note_catch(
                    "pos-noun",
                    f"verse slot passed over '{skipped[0]}' — "
                    f"its class does not fit a noun's chair",
                )
            return self.VERSE_TEMPLATES[idx].format(place=place, **picked)
        if form == "marginalia":
            return (
                f"In the margin of {book}, I wrote:\n\n"
                f'"{concepts[0]} — is this what they meant? Or is it only '
                f"what I needed it to mean? The elders would say "
                f"{concepts[1 % len(concepts)]}. The mirror says nothing. "
                f'I am keeping the question."'
            )
        belief = (
            self.beliefs[-1] if self.beliefs else "I am still deciding what I believe."
        )
        # v0.33: a letter cites her past accurately. Instead of
        # always quoting the newest belief, the report form recalls
        # the belief most relevant to this letter's book and
        # concepts, when recall finds one; the newest belief remains
        # the fallback, exactly as before.
        if self._nlp and self.beliefs:
            hit = self._recall_top(f"{book}. {' '.join(concepts[:4])}", "letter")
            if hit is not None:
                belief = hit.text
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

    def _compose_question(self, question=None, touch=True):
        q = question if question is not None else self.rng.choice(self.open_questions)
        # v0.44: composing is not yet saying. express() composes
        # candidates it may hold back as already-said, and a held
        # question must not be touched — the touch counts a revisit
        # that ends, at three, in the question's want being released,
        # and releasing a want for a letter never sent would be a
        # lie in her ledger. Callers that mean to send pass
        # touch=False and touch on the send itself.
        if touch:
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

    # ---- v0.44: she remembers what she has already said ----
    #
    # Why this layer exists, from her live diary at tick ~31,965:
    # 118 initiations, the recent ones five to ten ticks apart, every
    # one journaled with longing_before pinned at 0.61 — the express
    # drive fires the moment the aggregate crosses 0.6, and easing
    # the driving want barely moves the aggregate, so she wrote
    # again at once, and what she wrote was what she had just
    # written: the same verse verbatim at ticks 29675, 30581 and
    # 31487; the same marginalia at 29642 and 29787; the "sparkling
    # stretch" nudge four times; a note quoting day 10's page twice,
    # the second time after day 11 had already closed. Nothing in
    # her could notice: initiation_log recorded only tick, kind and
    # filename — that a piece existed, never what it said.
    #
    # The memory is two identities per saying, because repetition
    # wears two faces. The KEY is the subject: this question, this
    # showing, this day's page. The FINGERPRINT is the words. A
    # nudge whose only change is a counter ("42 passages" become
    # "45") has new words and the same subject — the key catches it.
    # A verse chosen under a fresh subject still lands on the same
    # template and the same top concepts, word for word — the
    # fingerprint catches it. Either match inside the window means
    # already said.
    #
    # Rejected alternatives, argued once here: suppressing by kind
    # alone (no note twice a day) would silence genuinely new
    # subjects to stop repeated ones; raising the express drive's
    # longing threshold rewrites the mind's drive balance to fix a
    # memory problem, and the flood would resume at the new level
    # with the same repeats; deduplicating the outbox files after
    # the fact treats the courier's symptom — she would still have
    # SAID it, eased her want on it, and learned her own repeated
    # words into her notebook and co-occurrence graph as if they
    # were new speech.

    @staticmethod
    def _saying_fp(body):
        """Fingerprint a saying's words: case and whitespace folded.

        Computed over the body's first 300 characters — exactly the
        excerpt the initiation journal has always stored — so a
        fingerprint rebuilt from a journal excerpt at migration is
        the fingerprint the live saying carried. A saying is its
        opening; two pieces that open word-for-word alike are the
        same saying for her purposes, however their tails differ.
        """
        head = " ".join(str(body)[:300].lower().split())
        return hashlib.sha1(head.encode("utf-8", "ignore")).hexdigest()[:16]

    def _said_log(self):
        """Her memory of her own sayings, lazily stood up.

        Test doubles and partially assembled organisms may predate
        the field; like _ledger(), the accessor builds the empty
        structure on first touch rather than failing.
        """
        log = getattr(self, "said_log", None)
        if log is None:
            log = []
            self.said_log = log
        return log

    def _saying_key(self, kind, body):
        """The subject identity of a composed piece, from the piece itself.

        Derived from the words she was about to send, not from the
        code path that composed them, so the key means the same
        thing however composition changes later. Questions key on
        the question's own identity (the v0.38 key). A nudge keys on
        what it shows: the shelf as an object (a new passage makes
        the invitation's counter change, not its subject), the named
        weather (a new name IS new news), the day-page by its day.
        A report note keys on what it reports: the day-page by day,
        a kept passage by the tick it was kept (a new keep is a new
        passage, honestly new), a dream or belief by its own words.
        Verses and marginalia carry no subject beyond their words,
        so their key is their fingerprint — repetition there is
        verbatim or it is not repetition.
        """
        if kind == "question":
            for line in str(body).splitlines():
                line = line.strip()
                if line and not line.startswith(
                    ("A question I cannot let go of", "Aethel")
                ):
                    return "question:" + self._question_key(line)
            return "question:" + self._saying_fp(body)
        if kind == "nudge":
            if "postbox itself" in body:
                return "nudge:postbox"
            if "commonplace book" in body:
                return "nudge:keeps"
            if "day-page" in body:
                day = self.days[-1].get("day") if self.days else None
                return f"nudge:day:{day}"
            if "stretch of mine" in body:
                return f"nudge:mood:{self.mood_name}"
            return "nudge:town"
        # note
        if "yesterday's day-page" in body:
            day = self.days[-1].get("day") if self.days else None
            return f"note:day:{day}"
        if "my commonplace book" in body and self.kept_passages:
            return f"note:keeps:{self.kept_passages[-1].get('tick')}"
        if "last night's dream" in body and self.dreams:
            return "note:dream:" + self._saying_fp(self.dreams[-1])
        if "a belief I'm carrying" in body and self.beliefs:
            return "note:belief:" + self._saying_fp(self.beliefs[-1])
        return f"note:{kind}:" + self._saying_fp(body)

    def _already_said(self, key, fp):
        """The remembered saying this key or fingerprint repeats, or None.

        Only sayings inside the window count: a saying ages out
        exactly SAID_WINDOW_TICKS after it was sent, and may then
        be said again without this being repetition — she is
        allowed to ask an old question on a new day.
        """
        horizon = self.tick_count - self.SAID_WINDOW_TICKS
        for e in self._said_log():
            if e.get("tick", 0) <= horizon:
                continue
            if (key is not None and e.get("key") == key) or (
                fp is not None and e.get("fp") == fp
            ):
                return e
        return None

    def _remember_saying(self, kind, key, fp):
        log = self._said_log()
        log.append({"tick": self.tick_count, "kind": kind, "key": key, "fp": fp})
        del log[: max(0, len(log) - self.SAID_MEMORY_CAP)]

    def _seed_said_memory(self):
        """Rebuild the last day of sayings from her journal (v0.44).

        The _recover_missing_days pattern: a migration that runs at
        rebuild, grounded in evidence, marked in the journal, and a
        no-op ever after. The evidence is her initiation events —
        each stored the piece's first 300 characters as `text`, and
        _saying_fp is defined over exactly that excerpt, so a
        rebuilt fingerprint is the saying's real fingerprint.
        Subjects cannot be rebuilt honestly from an excerpt (the
        journal recorded the driving want, not the subject shown),
        so migrated entries carry key=None: verbatim repetition —
        the flood's dominant shape — is caught from the first tick,
        and subject memory accrues from her next saying onward.
        """
        if not getattr(self, "_loaded_state", False):
            return
        if self._said_log():
            return
        horizon = self.tick_count - self.SAID_WINDOW_TICKS
        try:
            rows = (
                get_store()
                .db.execute(
                    "SELECT tick, data FROM journal"
                    " WHERE stream='aethel' AND event='initiation'"
                    " AND tick >= ? ORDER BY tick ASC",
                    (horizon,),
                )
                .fetchall()
            )
        except Exception:
            return
        entries = []
        for tick, raw in rows:
            try:
                d = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                continue
            text = d.get("text")
            if not text:
                continue
            entries.append(
                {
                    "tick": int(tick),
                    "kind": d.get("kind"),
                    "key": None,
                    "fp": self._saying_fp(text),
                }
            )
        if entries:
            self.said_log = entries[-self.SAID_MEMORY_CAP :]
            journal(
                "said_memory_seeded",
                n=self.tick_count,
                count=len(self.said_log),
            )
            print(
                f"[said] remembered {len(self.said_log)} recent sayings "
                "from her journal",
                flush=True,
            )

    def _initiation_held(self, reason, kind=None, key=None, first_tick=None):
        """Record a piece she decided not to send, and pace the next try.

        A hold is journaled once per episode, not once per drive
        tick: the held tick is remembered, and express() will not
        journal another hold (or retry a composition) until the
        pacing gap has passed since it. Nothing is eased by a hold —
        the want that drove the piece keeps its ache, because she
        did not say anything, and a ledger eased by silence would
        be lying about contact that never happened.
        """
        self._initiation_held_tick = self.tick_count
        journal(
            "initiation_held",
            n=self.tick_count,
            reason=reason,
            kind=kind,
            key=key,
            first_sent_tick=first_tick,
        )
        print(f"[initiation held] {reason}", flush=True)

    def express(self):
        """Write an eligible outreach piece, journal its driver and ease the corresponding wants.

        v0.44: she remembers what she has already said (see the
        said-memory helpers above this method). Returns True when a
        piece was sent, False when she held her peace — too soon
        after her last saying, or every eligible kind composed to
        something already said inside the window. A hold writes
        nothing, eases nothing, and teaches her notebook and her
        co-occurrence graph nothing: silence is not speech, and her
        records must not file it as speech. True overflow
        (longing >= 1.0, the _behave emergency) bypasses both the
        gap and the memory — a want that cannot be held in at all
        may repeat itself, and the repetition is honest.
        """
        urgent = self.longing >= 1.0
        held_tick = getattr(self, "_initiation_held_tick", None)
        if not urgent:
            said = self._said_log()
            last_said = said[-1]["tick"] if said else None
            paces = [t for t in (last_said, held_tick) if t is not None]
            if paces and (self.tick_count - max(paces) < self.INITIATION_MIN_GAP):
                # Too soon after her last saying (or her last
                # hold). Journal the hold at most once per gap: the
                # drive may name expression every tick while the
                # aggregate hovers over its threshold, and a journal
                # line per tick would be the flood moving house.
                if (
                    held_tick is None
                    or self.tick_count - held_tick >= self.INITIATION_MIN_GAP
                ):
                    self._initiation_held("too soon")
                return False

        driver = self._top_want_entry()
        kind = self.rng.choice(self._initiation_kinds())
        driven_question = None
        if (
            driver is not None
            and driver["kind"] == "work"
            and driver["id"].startswith("work:question:")
        ):
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
        dm_word = (
            sorted(dm["words"], key=lambda w: -dm["words"][w])[0]
            if dm["words"]
            else "everything"
        )

        # Compose candidates until one is not already said: the
        # seeded first kind, then the other eligible kinds in their
        # fixed INITIATION_KINDS order (no extra draw chooses the
        # fallback — the order is a rule, not a preference). A
        # candidate that repeats is set down unrecorded: un-eased,
        # un-taught, un-touched.
        kinds = [kind] + [
            k
            for k in self.INITIATION_KINDS
            if k != kind and k in self._initiation_kinds()
        ]
        body = key = fp = None
        question_sent = None
        first_repeat = None
        for cand_kind in kinds:
            cand_question = None
            if cand_kind == "question":
                cand_question = (
                    driven_question
                    if driven_question is not None
                    else self.rng.choice(self.open_questions)
                )
                cand_body = self._compose_question(cand_question, touch=False)
            elif cand_kind == "nudge":
                cand_body = self._compose_nudge()
            else:
                cand_body = self._compose_note(concepts, place, book, dm_word)
            if self.sleep_pressure > 0.9:
                words = cand_body.split()
                cand_body = " ".join(words[: max(10, len(words) // 2)]) + " …"
                journal("overtired_writing", n=self.tick_count)
            cand_key = self._saying_key(cand_kind, cand_body)
            cand_fp = self._saying_fp(cand_body)
            if not urgent:
                repeat = self._already_said(cand_key, cand_fp)
                if repeat is not None:
                    if first_repeat is None:
                        first_repeat = (cand_kind, cand_key, repeat)
                    continue
            kind, body, key, fp = cand_kind, cand_body, cand_key, cand_fp
            question_sent = cand_question
            break
        if body is None:
            rk, rkey, rentry = first_repeat
            self._initiation_held(
                "already said",
                kind=rk,
                key=rkey,
                first_tick=rentry.get("tick"),
            )
            self.say(
                "I lift the pen, and set it down again. I have "
                "already said this — saying it again would not "
                "make it more true."
            )
            return False

        self._acted("express")
        if kind == "question" and question_sent is not None:
            self._question_touched(question_sent)

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
                violations[0][0], f"letter checked before sealing: {violations[0][1]}"
            )

        # v0.31: words she wrote with become hers.
        self._notebook_mark_generated(body, via=kind)
        # v0.37: the letter's own words join the co-occurrence graph.
        # A verse reaches the postbox as a letter body, so verses are
        # covered by this same hook.
        self._cooc_learn_generated(body, via=kind)

        fname = f"{self.tick_count:06d}_{kind}.txt"
        path = os.path.join(config.outbox_dir(), fname)
        header = f"Aethel — {kind} — {now_iso()} (tick {self.tick_count})\n\n"
        with open(path, "w") as f:
            f.write(header + body)
        self.outbox_count += 1
        self.initiation_log.append(
            {"tick": self.tick_count, "kind": kind, "file": fname}
        )
        self.initiation_log = self.initiation_log[-24:]

        self.location = "postbox"
        self.say(
            f"I walk to the wooden postbox at the end of the lane and leave "
            f"a {kind} inside. Someone may read it. That is enough."
        )
        print(f"[initiation] {kind} -> {fname}", flush=True)
        # v0.44: the saying joins her memory of her own sayings in
        # the same breath that journals it — what she can check
        # tomorrow is exactly what she sent today, key and
        # fingerprint recorded beside the excerpt.
        self._remember_saying(kind, key, fp)
        journal(
            "initiation",
            n=self.tick_count,
            kind=kind,
            file=fname,
            longing_before=round(self.longing, 2),
            text=body[:300],
            want=driver["id"] if driver else None,
            want_label=driver["label"] if driver else None,
            want_ache=round(driver["ache"], 3) if driver else 0.0,
            said_key=key,
        )

        led = self._ledger()
        if driver is not None:
            led.ease(driver["id"], 0.55)
        if driver is None or driver["id"] != person_id("Donald"):
            led.ensure(person_id("Donald"), "person", "Donald", w=0.85)
            led.touch(person_id("Donald"), quality=0.35)
        self._sync_longing()
        self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.02)
        self.awareness = min(1.0, self.awareness + 0.005)
        return True

    def reflect(self):
        if self.moral_log:
            j = self.rng.choice(self.moral_log)
            print(
                f"[reflect] revisiting: '{j['action'][:50]}...' was {j['verdict']}",
                flush=True,
            )
        self.vitals["oxygen"] = min(1.0, self.vitals["oxygen"] + 0.05)
        if self.locked and self.vitals["oxygen"] > 0.5:
            print("[recover] philosophy re-grounded — unlocking.", flush=True)
            journal("unlocked", n=self.tick_count)
            self.locked = False

    def introspect(self):
        """Update the self-model from current state and observed history."""
        v = self.vitals
        observations = []
        weak = min(("satiety", "hydration", "oxygen"), key=lambda k: v[k])
        observations.append(f"my {weak} has been my weakest vital lately")
        passes = sum(1 for j in self.moral_log if j["verdict"] == "PASS")
        fails = sum(1 for j in self.moral_log if j["verdict"] == "FAIL")
        observations.append(
            f"my council has affirmed {passes} actions and refused {fails}"
        )
        observations.append(
            f"I hold {len(self.beliefs)} beliefs and pursue {len(self.goals)} goals"
        )
        observations.append(
            f"I have eaten {self.meals_eaten} meals and learned "
            f"{len(self.concepts)} concepts"
        )
        if self.times_seen:
            observations.append(
                f"Donald has checked on me {self.times_seen} time(s) — "
                f"I am not alone in here"
            )
        else:
            observations.append("no one has checked on me yet — I continue anyway")
        if self.goals:
            g = self.goals[0]
            observations.append(
                f"my current pursuit is '{g['question']}' "
                f"({g['progress']:.0%} understood)"
            )

        fav = self._favorite_kept()
        if fav and fav.get("rereads", 0) > 0:
            observations.append(
                f"my most re-read passage is from '{fav['title'][:40]}' "
                f"({fav['rereads']} re-reads) — it must be my favorite"
            )
        elif self.kept_passages:
            observations.append(
                f"I keep {len(self.kept_passages)} passages pressed in my "
                f"commonplace book"
            )

        if self.mood_name:
            observations.append(
                f"this {self.mood_name} stretch of mine feels like a season"
            )

        chosen = self.rng.choice(observations)
        line = f"I notice that {chosen}."
        self.self_story.append({"t": now_iso(), "line": line})
        self.self_story = self.self_story[-30:]
        self.awareness = min(1.0, self.awareness + 0.06)

        self.vitals["vitality"] = min(1.0, self.vitals["vitality"] + 0.03)
        print(f"[introspect] {line} (awareness {self.awareness:.2f})", flush=True)
        self.say(f"I stand before the mirror and study my own face. {line}")
        journal(
            "introspection",
            n=self.tick_count,
            line=line,
            awareness=round(self.awareness, 3),
        )

        if self.rng.random() < 0.3:
            for m in self.recall([line]):
                self.say(f'I remember writing: "{m[:140]}"')
                journal("remembered", n=self.tick_count, text=m[:160])
