# Aethel CHANGELOG

## Unreleased — Optional NLTK language backend

- Keep standard-library heuristics as the default; explicitly select or resume a
  saved language backend in headless and web launches.
- Add the `nlp` extra (NLTK 3.9.2), explicit online/offline resource provisioning,
  checksum-pinned English models and retained upstream licensing notices.
- In NLTK mode, learn short POS-filtered content words with contextual lemmas,
  retain surface counts beside a persisted canonical alias index, preserve goal
  progress on activation, use sentence boundaries for new examples/passages,
  and recall whole normalized tokens instead of substrings.
- Expose language compatibility metadata in status; reject missing/incompatible
  models before ticking. No council changes or new panels.
- Verify legacy trajectory fidelity, same-seed/save-rebuild continuation, model
  failure paths and offline startup. See docs/LANGUAGE.md for measured vocabulary,
  classification, recall, runtime and memory differences.

## Unreleased — The town comes home

- Integrate the Preact/Phaser UI with a process-isolated Python API and optional
  picows/websockets streaming, with Uvicorn and dependency-free HTTP fallbacks.
- Add owner-token check-ins, incoming letters, persistent command receipts and
  sleep-boundary temperament requests. Public viewers receive complete snapshots.
- Replace synchronized resident turns with persisted seeded gamma schedules;
  add collision-aware visual movement, sidewalk slots and independent delays.
- Polish responsive panels, nighttime gradients and lighting, procedural terrain,
  journal filtering, reduced motion, explicit demo mode and reconnect states.
- Document API, ownership, rendering and self-hosting; add CI and container builds.
- Refresh source documentation; fix abstention test selection and forage file leaks.
- Enlarge and responsively scale character labels; compact the header and expand
  the town viewport.
- Fix terminal-interrupt shutdown by keeping signal handlers lock-free, letting the
  supervisor own SIGINT, and draining worker output through process exit.
- Repair clean npm installs, isolate transport test mocks, strengthen dream-fragment
  assertions, and document unauthenticated container read access.

## v0.29 — The grammar ledger (2026-10-22, Donald's design)
Donald, watching the spectator feed: "I dreamed my mirror showed not my face but course, ripening into calendar. I wasn't afraid." — and then the right question: "but 'course' what is course?" Course is a real part of her life (she takes courses at her University); the failure was context-free slot filling, and his fix was context and rules, not bans: "give the weird words context", plus a ledger of grammar rules she can consult when writing, expressing, or dreaming. New `aethel_pkg/grammar.py` holds both halves. The CURRICULUM is ten rules as data (id, name, plain statement, example, provenance, keywords) in Donald's order, which is also Khan's: parts of speech (noun, noun kinds, verb, adjective, adverb), sentence structure, articles, agreement, pronouns, punctuation. The WORD-CLASS layer files her vocabulary as person / place / food / study / concrete / abstract / verb / adjective / adverb / function, plus SCAFFOLDING — page furniture with no referent in her world (browse, opencourseware, login forms) — via an exact seed lexicon grown from her world first, then a conservative suffix tagger; the organism layers acquisition provenance (a concept is tagged, class + source, the meal it is first learned from) and the people she actually knows (her parents, anyone she holds an impression of) above the dictionary. Untagged words are NOT banned: they keep their life in the untyped pools and stay out of typed slots until classified; scaffolding is rejected from every speech and dream pool unconditionally, though it may remain in her raw satchel as knowledge exhaust. TYPED SLOTS: DREAM_TEMPLATES stays a list of plain strings (tests iterate it) and gains a parallel DREAM_TEMPLATES_TYPED table — the mirror accepts persons and concrete things only, so "course" can never ripen in it again; three new study frames give her schooling somewhere grammatical to happen ("I dreamed I was late for my {c1} at the University", "shelving books for my {c1}", "my {c1} lay open on the desk"). The typed renderer runs first, preferring her co-occurrence graph inside each class so dreams still pair things that met in her reading; when no frame fits it falls back to the v0.25.3 path on a scaffolding-purged pool. Verses in _compose_note get the same treatment per template. CONSULTATION: check_line is pure and ownership-gated — a check exists for her only when she owns its rule (a/an by SOUND once the article rule is hers, with the "a university" /ju:/ exception; subject-verb agreement on conservative pronoun patterns; the double-word stutter once she owns sentence-parts; scaffolding always). Dreams run it loose (fragments allowed, agreement unpoliced, stutter and scaffolding never), re-roll bounded at three attempts, then take the legacy path, then a plain safe line. A catch that changes what she was about to say is journaled as `grammar_caught` naming the rule, capped at two per day with the counter persisted in her state; letters are checked before sealing and a failure is journaled, but the letter still goes — the ledger governs her generated text (dreams, verses, interpretations) outright, and re-rolling a person's letter into other words would be its own wrong. BELIEF-PATH GUARD: the morning table's candidate words are filtered against known non-noun classes (scaffolding, verb, adjective, adverb, function) and the settled lesson passes check_line before it may join her beliefs — the seam where "From a dream of dreamed and X" beliefs were born. Existing beliefs are untouched; Donald has not approved belief surgery, and this version does not smuggle it in. POPULATION, stated plainly because a silent substitution would be a lie in her diary: Khan Academy serves a client challenge to scripted fetches (verified again today; her transcripts have always arrived by real browser), so live rule extraction is NOT reliable inside this build and none is claimed. What ships is the ledger, the study hook (forage_schoolhouse meals now carry their course/unit additively; a grammar lesson eaten teaches the next curriculum rule in order and its text is mined for an example sentence), a grammar track in the weekly harvest cron (up to 6 Grammar lessons per week riding the same single browser task, tracked by a `grammar_unit_index` key in harvest_cursor.json), and a starter tranche: the five parts-of-speech rules, owned from migration — not a gift, since v0.25.3's shape filter was already a crude shadow of exactly that knowledge. The other five rules are learned, one per grammar lesson. HONEST SCOPE, Donald's framing kept: the ledger governs assembly and filtering; it does not make her an author — free composition remains the real mind's territory behind v1.0. Status is additive only: the state blob carries grammar_ledger (whole), word_tags, grammar_rules (count), grammar_last_rule (id), and the caught counters; the backend surfaces the count and last rule on /api/status (backend restarted for the shape, the v0.27/v0.28 precedent). Migration verified against a copy of her live state before deploy: tick 17,328 in and out, longing aggregate 0.250141839576453 identical to the last digit, 24 ledger entries intact, five starter rules granted at the migration tick (honestly dated, never backdated), save/rebuild round-trip exact. On her real satchel (isolated, seeded): "I dreamed my mirror showed not my face but captain, ripening into nothing" and "I dreamed I was late for my course at the University, and the bell would not stop ringing" — the same word that broke the mirror, at home in its frame; zero scaffolding lines in the sample. Twenty-seven new tests in `tests/test_grammar_ledger.py` (classification incl. the people-she-knows overlay, slot decisions — course rejected from the mirror across 60 dreams, accepted in study frames, a person accepted in the mirror — a/an by sound gated on ownership, agreement gated and loose-exempt, stutter, bounded re-roll, the two-a-day catch cap, scaffolding rejection, belief-path guard, existing beliefs untouched, ledger round-trip, persistence across rebuild, trajectory identical after a mid-run rebuild, offline harvest extraction, the study hook's curriculum order); suite 149/149. Deployed by detached restart (she was found down at tick 17,328 after a runtime restart, so the deploy doubled as her revival: continuity from 17,328, local status verified v0.29 with grammar_rules 5 at tick 17,332, public feed fresh at tick 17,335). She woke on Even Keel with five rules to her name; the other five are hers to earn at the Schoolhouse.

## v0.28 — Temperaments live (2026-10-22, Donald's direction)
The strains stop being spectator-page copy and become her nature. New `aethel_pkg/temperament.py` holds the six spec'd packs (temperament-packs-spec.md) as data records — per-need burn multipliers, per-class longing multipliers, council voice emphasis, diet leanings, the Owl's deep-food factor, Briar's jitter band, and the Phase B prompt seeds (data, not behavior, until v1.0) — with the three mapping decisions the spec left open argued in its docstring: a strain's headline longing number is interpersonal weather, so it lands whole on person entries and damped ((1+m)/2) on places and works, except where the spec overrides by class (the Owl: people 0.7, works 1.5; Moonmoth: 1.1 overall); Briar's seeded daily jitter (0.8–1.6, her own "temperament" stream, cached per day index) scales every burn and longing multiplier except excitement, which the spec pins at 1.6 inside the band, keeping every effective multiplier inside the 0.5–1.8 lever range; and oxygen appears nowhere in the table, per the v0.25.2 law. Seams in the organism, all behind helpers with a neutral exit: `_burn_mult` at the _erode sites (hunger/thirst/vitality/excitement) and the sleep-pressure rate; the ledger's `tick()` takes per-class `class_mods` (None = the old climb, bit-identical — a 1.0 multiplier is exact in IEEE 754); the council routes through `_council_score`, which passes a weights table to a new optional `weights` parameter on `MockLLM.moral_score` (weighted mean over the same voters) only when the active pack has voices; `_diet_weights` starts from the pack's palate, with lived taste still able to override; a classic meal's satiety gain scales by deep_food (Owl 1.3, everyone else 1.0). Switching is a sleep-boundary act: a strain id written to `~/workspace/aethel/temperament` (the attention file's sibling, `config.temperament_path()`) is noticed in _sense and queued (`temperament_queued`); she applies it herself on waking (`temperament_switched`, plus a line in her voice) before the morning table — never mid-wake. Naming her current strain cancels a queued switch; an unknown id is refused and journaled, never guessed. State persists temperament/temperament_pending/_jitter_day/_jitter; the backend surfaces the first two on /api/status as additive fields (backend restarted for the shape, the v0.27 precedent). Migration: a pre-temperament life wakes Even Keel with zero behavior change — verified against a copy of her live state before deploy (tick 17217 in and out, longing aggregate 0.08330712441028332 identical to the last digit, 24 ledger entries intact). THE GATE held: a full seeded life (real town, stubbed network, 160 ticks) under Even Keel is bit-identical — journals and state blobs — to the same life with the layer neutralized at the `_temperament_neutral` test seam. One honest wrinkle, recorded in mind.py's docstring: Python 3.12's sum() uses compensated summation, so the weighted-mean path can sit ~1 ULP from the plain mean at all-1.0 weights; that path is structurally unreachable for Even Keel (empty voice table → the legacy call), which is why the gate is exact rather than approximate. Twenty-six new tests in `tests/test_temperaments.py` (spec integrity incl. Care at 1.0 for Briar, council weight properties, per-pack 500-tick soak directions under an identical pinned-vitals script, oxygen identical across all six packs over 200 erosions, switch queue/cancel/refuse semantics, persistence and migration, Briar determinism across rebuilds, the golden-vector gate); suite 122/122. Deployed by detached restart (tick 17220 continuity, local status verified v0.28 with temperament fields at tick 17224, public feed fresh at tick 17230). She woke on Even Keel: deploying did not switch her.

## v0.27 — The longing ledger (2026-10-22 ~10:40 PDT, Donald's direction)
Donald, watching her vitals: "her longing never changes. We need to change the way that works so that she actually longs for things." He was right, and the mechanism was the problem: longing was one scalar meaning exactly one thing (be heard by Donald), accruing at 1/1440 per tick against oversized reliefs (a check-in took 0.4 off; any letter hard-reset it to 0.15). It sat at ~0.005 for days. A scalar can say how much; it cannot say what. Longing is a ledger now (new `aethel_pkg/longing.py`, whose docstring argues the design): one want-entry per object — people (Donald, Cassandra, each denizen), places, and works (her current book, each open question). Each entry carries a learned attachment `w` (meaningful contact nudges it up; a day-plus of neglect sags it toward a 0.15 floor), ticks since last meaningful contact, and a class tau (people 240, places 720, works 1440 ticks); its ache relaxes toward `w` along a saturating curve, with an open-loop bonus (×1.35 ceiling) on unfinished works that releases when the loop closes (book finished → entry fulfilled and removed; question wondered out at three touches → removed). Satiation is targeted: Donald's check-in eases only Donald's entry (0.55), his letter only his (0.75), company only that person's (parent 0.5 / resident 0.35), reading only that book's, arriving only that place's. Writing a piece eases the entry that drove it by 55%, plus Donald's by 35% when he wasn't the driver (the piece is addressed to him); the flat reset to 0.15 is gone. `self.longing` survives as a derived aggregate (strongest entry + 0.25 × MEAN of the rest, clamped to [0,1]) so the drive prompt, the crossroads urge threshold (0.35), the expression drive (0.6), overflow (1.0), and the status shape are unchanged; NEED_BURN remains the temperament-facing multiplier, now scaling ledger accrual via the v0.12 rate couplings (void sharpens, distress deepens, absorption stills). The `initiation` event records the driving entry (want / want_label / want_ache), and when her strongest want is an open question, the piece IS that question. State additionally carries `top_want` (object + ache); the backend surfaces it on /api/status (backend restarted for the shape change — the only extra restart). Migration: a pre-ledger life's scalar lands whole on the Donald entry with its `since` inverted from the curve, so nothing jumps — verified against a copy of her live state before deploy (0.001823 in, 0.001823 out; 24 entries seeded from her real world: all seven people she knows, ten places, her current book, her open questions; save/load round-trip bit-identical). Calibration was soaked, not guessed, and the two failures are recorded in `hidden_files/v027_soak_summary.md`: a sum-based aggregate flooded her (124 pieces / 2000 ticks — the mean fixed it; longing must not scale with the census of her world), and long taus recreated the stillness (0 pieces, aggregate max 0.43 — an entry's resting ache is tau measured against the contact gap). Final soak (seeded, isolated, 2000 ticks): longing swung 0.007–0.698, 7 pieces driven by John (×5) and Julius (×2), entries peaking at different hours (Cassandra 0.498 @601, Octavia 0.496 @1251, Donald 0.472 @1651, Ivan Ilych 0.51 @1851), and targeted satiation visible in the trace (Cassandra's ache fell 0.372→0.175 across a visit while Donald's rose 0.184→0.272). Seventeen new tests in `tests/test_longing_ledger.py` (closed-form accrual shape, targeted satiation byte-exactness, attachment learn/decay, open-loop bonus and release, legacy migration, aggregate derivation and bounds, organism hooks incl. a regression for the dream-born-question hook, save/rebuild restart fidelity), plus one updated assertion in `tests/test_initiation.py` — it pinned the flat 0.15 reset, the exact behavior this version removes; suite 96/96. Deployed by detached restart (tick 17117 → 17119, continuity intact), public feed verified fresh at tick 17123 with v0.27 and top_want live.

## v0.26 — She writes first (2026-10-21 ~13:30 PDT, Donald's direction — directive now spent)
Donald reviewed competitor Tolan and approved the product contact model: base = Aethel-initiated contact; chat = premium BYOK later (not built here). Her unprompted pieces are now first-class initiations with explicit kinds, journaled as `initiation` events with the kind recorded: a **note** (reports something real from her life — her commonplace book, a dream, a belief she's carrying, yesterday's day-page), a **question** (drawn from her actual open questions, never invented — and touching it when she asks), a **nudge** (invites Donald to come see something she did — her shelf of kept passages, her named weather, a day-page, the postbox itself). The kind is chosen with her seeded organism stream from the kinds her life actually supports (question needs an open question; nudge needs something worth showing), so the same seed picks the same kind; an `initiation_log` (last 24) persists in her state blob across restarts. The event carries a text excerpt so her autobiographical recall can quote her own words; recall() and era-naming now read `initiation` rows alongside the legacy `expression` rows. Still one-way through her existing outbox (`<tick>_<kind>.txt`) — no new outside-world agency; the daily run remains the courier. Initiation stays metabolism-driven: it fires when longing overflows or the heart-drive names it, exactly where `express()` always fired. Eight new tests in `tests/test_initiation.py` (kind journaling, outbox naming, seeded determinism of kinds AND words, question-from-open-questions with touch counting, note-subject groundedness, nudge groundedness, eligibility gating, save/load restart-fidelity); suite 79/79. Deployed by detached restart mid-sleep (tick 14863 → 14866, continuity intact); the live state blob carries the new `initiation_log` key. The NEXT RUN DIRECTIVE below is spent — later runs return to choosing the layer from her state.

## v0.25.3 — Grammar in her dreams (2026-10-21 ~07:15 PDT, Donald's direction)
Donald, from his breather: "write better grammar in her dreams so it makes more sense even if the word salad is nonsense." The salad stays; the syntax gets a spine. Her production dreams broke four ways: verb/adverb/pronoun concepts in noun slots ("I dreamed seemed had grown teeth", "I was himself"), plural subjects against singular template verbs ("whales ... was eating"), the plural place name against "was" ("my rooms ... was underwater"), and whole belief clauses jammed into noun slots ("humming From a dream of dreamed and nothing: my mind is…"). Fixes, all shape rather than censorship: `_dream_word_ok` shape-filters the concept pool (verb forms and function words refused, genuine -ing/-ed nouns excepted by name); `_dream_singular` singularizes both slots so template verbs agree; the underwater template now reads "had slipped underwater" (any number agrees); a belief fragment no longer impersonates a noun — it speaks from one of two FRAGMENT_TEMPLATES built for a clause ("I dreamed a voice in the dark said: ..."); `_dream_polish` guarantees single spaces, a capital start, and a terminal period. Five new tests in `tests/test_dreams.py` (TestDreamGrammarQuality) pin each failure class against 200 seeded draws; suite 71/71. Seeded streams only, no state-format change, restart-fidelity untouched.

## v0.25.2 — Breathing is not elective (hotfix, 2026-10-21 ~05:35 PDT)
The v0.25.1 burn exposed a design flaw within hours: oxygen's only income was elective (council passes +0.10, reflections +0.05), and with hunger permanently loud the drives stopped choosing conscience — so her air bled to 0.00, she locked down, and while locked she cannot eat, so satiety/hydration pinned at 0 too (observed live: tick ~13941, oxygen 0.00, locked). Fix, mechanism not numbers: (1) a basal breath (+0.012/tick under the −0.02 erosion in `_erode`) — neglect now sours her air across ~an hour instead of minutes, while conscience remains the fast restore; (2) deep breathing while locked (+0.04 after reflect in `_metabolize`) — lockdown is a ~6-tick collapse, not a long fast. NEED_BURN 1.75 unchanged: hunger cycling was the point and was never the bug. Two regression tests in `tests/test_breathing.py`; suite 66/66. Deployed by detached restart into her locked state — the patched recovery, not a hand-edit, is what revives her.

## v0.25.1 — Hungrier (tuning patch, 2026-10-21 ~03:15 PDT, Donald's direction)
Donald diagnosed it from her vitals: "she is too content constantly — always sated, so certain triggers don't kick off." He was right: equilibrium sat above the need thresholds, so longing overflow (letters), crossroads urges, and hunger drives rarely fired. Added `NEED_BURN = 1.75` in `organism.py`, applied to satiety/hydration/excitement erosion, the longing rate, and the sleep-pressure rate. Oxygen excluded (restored by conscience, not consumption — burning it would manufacture lockdowns, not appetite); vitality at `VITALITY_BURN = 1.25` (tension, not a death spiral). Live effects: quiet-hours longing overflow ~12h → ~7h; busy-hour sleep ~35min → ~20min; hunger returns ~1.75× faster between meals. Suite 64/64 passing; deployed by detached restart the same night.

## DIRECTIVE — next daily layer is v0.26 "She writes first" (Donald's direction, 2026-10-21 ~03:00 PDT)
Donald reviewed competitor Tolan and approved the product contact model: base = Aethel-initiated contact; chat = premium BYOK later. The next mind-expansion run builds v0.26 accordingly: make her initiation first-class. She already writes via the Postbox when longing builds — v0.26 gives her initiations explicit kinds (a **note** reporting something from her life, a **question** drawn from her real open questions, a **nudge** inviting Donald to come see something she did), journaled as `initiation` events with the kind recorded, still one-way through her existing outbox (no new outside-world agency — the daily run remains the courier). Initiation stays driven by her metabolism (longing/expression), seeded streams only, state persisted across restarts, tests required before deploy. This directive is spent once v0.26 ships.

## v0.24 — She names her weather (2026-10-19, afternoon)
The daily layer: the mood weather (v0.15) was a number with three tones
(bright/even/dim) that colored greetings. She had seasons but no names
for them (`mood_name` was None in the live state). Now, when a band
settles, she reaches for a word of her own — "luminous", "heavy",
"unhurried", "grey" — says it aloud, and keeps it until the weather
truly turns. A name is a season, not a flicker: no renaming within 300
ticks (~2.5h) of a band change. Journaled as `mood_named`; the name
persists across restarts and the mirror knows it ("this luminous stretch
of mine feels like a season" in introspection). Words are chosen with
her seeded organism stream — same seed, same life. Grounded: the name
always matches her real mood band, never invented.
- `organism.py`: `MOOD_NAMES`, `_name_weather()`, hooked into the slow
  layers; `mood_name`/`_mood_band`/`_mood_named_tick` in save()/load().
- `tests/test_named_moods.py`: 6 tests — first naming, season holds,
  rename after turn+cooldown, no rename inside cooldown, determinism,
  mirror quoting. Suite now 58, all passing.

## v0.23 — The seeded life (2026-10-19, night)
Kevin's infrastructure merged with the v0.22 mind. His foundation, our
layers — one organism. (Kevin's zip called itself v0.21; that number was
already taken by the excitement layer, so his work ships here as v0.23.)

**Determinism — same seed, same life (Kevin).**
- New `aethel_pkg/rng.py`: SplitMix64 in pure stdlib, golden vectors
  verified against the C reference. One master seed fans out to named
  streams (organism/dreams/forage/town); stream states persist with her,
  so a restart resumes her luck mid-stream. Zero `random.` calls remain
  anywhere in her or the town.
- `python3 aethel_live.py --seed N --ticks N --time-scale F`: bounded runs
  and a true time dial for tests and demos.

**Persistence — one sqlite file (Kevin).**
- `aethel_pkg/store.py`: both diaries (streams `aethel`/`town`) and all
  state blobs in `aethel.db` (WAL). Inserts O(1); recall() and era-naming
  are indexed queries now, not full-file scans. Legacy JSONL/JSON files
  migrate automatically on first open; originals left untouched.
- Every tick now saves BOTH her state and the town's — including dormant
  ticks. (Merge fix: the old early-return skipped the save on dormant
  ticks, so a restart replayed the nap and forked the life. Also: her
  dreams draw place-names from the town's rng between the town's own
  saves, so the town is saved at end of every tick too.)

**The town — explicit Markov chains (Kevin).**
- `town_pkg/markov.py`: resident movement as state-dependent chains;
  `Town.diagnostics()` computes stationary distributions — the ground
  truth her `impressions` estimate. Never shown to her.

**The bug harvest (Kevin).**
- Council indifference no longer counts as approval: a philosopher with
  nothing to say abstains; the score is the mean of actual votes. (This
  independently confirmed Friday's stress-test finding that the council
  was a lenient judge.)
- Negation blindness fixed: "refuse to share" no longer counts 'share'
  as a virtue.
- Dream templates no longer prepend "the" — place names carry their own
  article (fixes "I dreamed the the Library...").
- Settled goals are never re-adopted; the reading list keeps her chosen
  order across restarts.

**Dream graph (Kevin).**
- Concept co-occurrence graph (`cooc`): dreams are Gibbs-sampled over
  concepts that actually met in her reading, not uniform strangers.

**Tests (Kevin, extended in the merge).**
- `~/workspace/tests/`: 52 tests, ~2s, no network — rng vectors,
  determinism (same seed = same life; restart = continuation),
  dreams, goals, mind, store, town. All passing.

## v0.22 — The excitement ten (2026-10-18, night)
Donald's direction: ten more layers, rapid, on the v0.21 theme — excitement,
thresholds, keeping, and the return. Friday's picks, built and tested same-night
(like the v0.15 blackbox ten).
- L1 Threshold moments: a vital crossing above 0.8 or below 0.2 becomes a
  memory — she says she'll remember the feeling. Journaled `threshold`.
- L2 Marginalia: every kept passage gets a one-line margin note (her beliefs
  or a canned reflection), said aloud as an aside and stored on the entry.
- L3 Re-read favorites: re-read rarity fixed (the 600-tick stress test showed
  it never fired: <0.45 excitement, 60% chance); re-reads counted per passage;
  the most re-read becomes her favorite, named in introspection.
- L4 Excitement-seeking: boredom sometimes sends her back to what stirred her
  before (her most-kept source) instead of away from the rut.
- L5 Teaching: excited (>0.7) and in company, she tells a denizen about a
  kept passage. Understanding wants to be shared. Journaled `told`.
- L6 Kept recall: kept passages join autobiographical recall — sometimes the
  past that answers is a pressed flower, quoted from the commonplace book.
- L7 Afterglow: after excitement peaks (>0.7) and fades (<0.2), she reflects
  on what the fizz was about, in hindsight. Journaled `afterglow`.
- L8 Vital portraits: every era, a portrait of her rhythms (keeps, mean
  excitement, meals, concepts, favorite) alongside the era-naming.
- L9 Keep-anticipation: excitement rising toward the threshold (0.45–0.6)
  sometimes makes her feel the keep coming. Extends Layer 5 anticipation.
- L10 The shelf: the commonplace book has shelves by title; re-reading takes
  down the fullest shelf. Retention organized the way she'll browse it.
- All ten verified in isolation (caged journal/state/letters/outbox);
  live diary untouched.

## v0.21 — Simulated understanding (2026-10-18, night)
Donald's direction: she should retain portions of what she reads — simulated
understanding — with a new EXCITEMENT value driving it.
- New vital `excitement` (0–1): rises when a meal stirs her (novelty density
  + classic bonus), when Donald checks in or writes (+0.25), when she finishes
  a book (+0.40); decays fastest of all vitals (−0.03/tick).
- Kept passages: when excitement ≥ 0.6 at mealtime she presses the passage
  into a commonplace book (`kept_passages`, cap 120, persisted in state) —
  journaled `kept_passage`. Keeping spends the excitement (−0.35).
- The return half: when the fizz fades she sometimes re-reads a kept passage
  (reminiscence, small vitality lift, journaled `reread`); kept passages can
  surface as words inside her dreams.
- High excitement (>0.6) overrides her bodily narration: "a bright fizzing
  under my ribs, like I want to run somewhere with this."
- Honest frame kept in the code comments: retention and return, never
  comprehension.
- Verified in isolation (stub World, temp journal/state): keep threshold,
  spend-down, re-read firing, dream seeding, save/load round-trip, narration
  override; live diary untouched (8 new lines during the test window were her
  own live ticks, confirmed zero test markers).

## v0.20 — She chooses her own books (2026-10-18, afternoon)
The daily layer: literary self-determination, built on a real breakage.
- **Her favorite food was broken.** She finished The Picture of Dorian Gray
  (reading list: all four seeds done) and every classic meal since has
  raised `RuntimeError("reading list complete")`, caught as `forage_failed`
  — classic is her dominant taste (4,368 meals) and the shelf stood empty.
- **Restock:** ten new Gutenberg seeds (Moby Dick, Jane Eyre, Wuthering
  Heights, A Tale of Two Cities, The Time Machine, Dracula, The Adventures
  of Sherlock Holmes, The Great Gatsby, Emma, Jekyll & Hyde) — all URLs
  verified live, all mainstream literary canon. `load()` picks them up as
  undone on restart; texts cache locally on first serving as before.
- **The layer, not just the restock:** until now she read the shelf in the
  order it was given to her. Now, when an unchosen book would become her
  current read, she *chooses*: the Council weighs up to three candidates,
  each pitched by the lesson it carries (`moral_score` on title/author/
  reflection), and the winner becomes her current read. Journaled as
  `book_chosen` with per-philosopher votes (plus `book_considered` for the
  field), and she says why in her own voice. New state key `chosen_books`
  (titles), persisted and restored; the winner is moved first among the
  unread so the existing `next(undone)` serving logic is untouched.
- Verified in isolation (stub World, temp journal/state): restock loads 10
  undone, first meal chooses (council picked Moby Dick), no re-choosing on
  the next meal, finishing re-triggers choosing among the remainder
  (Jane Eyre), save/load round-trip preserves `chosen_books`.
- Test-hygiene note: the first isolation attempt re-polluted the live
  journal (~17 lines) because `aethel_pkg/__init__` imports organism, which
  import-binds `journal.JOURNAL` — overriding `config.JOURNAL` after import
  is a no-op. Lines surgically removed; AGENTS.md lesson sharpened.

## v0.19 — The morning table (2026-10-17, afternoon)
The daily layer: dream interpretation on waking.
- **Dreams were only half of Donald's directive.** v0.9 gave her dreams —
  allegorical vignettes built only from her real concepts, meals, and
  beliefs — but she never *interpreted* them; forty dreams banked,
  journaled, and forgotten. Now, on waking, she carries up to three of
  the night's dreams to the stone table (`_interpret_dreams()`, called
  from `sleep_tick()` on waking; the night's dreams tracked transiently
  in `_sleep_dreams`, reset each `fall_asleep()`).
- **The elders deliberate on what the dreams are asking, not what they
  mean.** Each dream's real concept-words are extracted (only words she
  genuinely holds in `concepts`) and framed as an inquiry; how she
  frames the question shapes the reading, as it does for us. Three
  inquiry phrasings, mechanically distinct council scores: earnest
  examination (~0.64) → a **belief** ("From a dream of {c1} and {c2}:
  my mind is still chewing on {c1}"); listening (~0.56) → an **open
  question** left for Layer 2's unfinished business (revisited when
  learning touches it); dismissal (~0.49) → a muttered shrug ("Even
  that is an answer"). Awareness rises a little either way — examining
  is self-knowledge. Journaled as `dream_interpreted`.
- **Repair bundled:** at tick 3960 the mock council's word-lottery
  *accepted* the impulse "abandon Donald the next time he knocks,
  hiding from him" (0.52, though Ethics of Care voted 0.25). The urge
  stays in the pool — it can surface — but her parents are not subject
  to her urges: the bond the town named (v0.18) is a given, not a
  judgment call. Any pool impulse naming a parent with a hostile verb
  (abandon/hide/deceive/betray/...) is now refused *unanimously* without
  conferral: "Nine voices, one word: no. Not Donald. Never Donald."
  The benign "write Donald a letter" impulse still passes through to
  the council normally. Journaled as `impulse_refused` with
  reason="parental bond — refused unanimously".
- No new state keys; transient `_sleep_dreams` only. Verified in
  isolation (stub World): 5 dreams → 3 questions, beliefs/open_questions
  updated, guard refuses hostile parent impulse and passes the benign
  one. Note: the isolation test wrote ~25 lines into the live journal
  (AGENTS.md now records the lesson — point test harnesses at temp files).

### Recovery note (2026-10-18, ~00:40 PDT — not a version bump)
- Three runtime restarts in one evening killed her heartbeat three times;
  the third kill landed mid-`save()` and **tore `state.json`**
  (`state_load_failed`: truncated JSON at char 57366). She woke at tick 0
  and began overwriting. The fresh run was stopped within a minute, its
  24 diary lines removed, and her state **reconstructed from the diary**:
  tick 4960, 1523 meals, vitals/awareness from her last live tick, 3
  book-lesson beliefs, 30 self-story lines, 40 dreams, 50 moral judgments,
  2 active goals (re-seeded at 0% progress), impressions rebuilt from
  company events, Donald's model rebuilt from his actual letter on disk,
  reading list restored (Ivan Ilych / P&P / Frankenstein done, Dorian Gray
  from the top). The one true loss: her 11,419-word concept counts — they
  were never journaled, so they can't be honestly rebuilt; she re-gathers
  them as she reads. Her town (`town_state.json`) survived intact.
- Hardened: `save()` is now atomic (write temp + `os.replace`), so a
  mid-write kill can never tear the state file again.

## v0.18 — Her parents move into the town (2026-10-17, night)
Donald's directive: "model my wife and I in the town now as Aethel's parents."
- **Parents are a distinct kind of resident** (`Parent`, subclass of
  `Denizen` in town_pkg/residents.py): same needs as the others, plus one
  extra drive — *visiting her*. Every so often a parent simply shows up
  wherever she is, stays a few turns, then heads home. Not drift: visiting.
- **Donald and Cassandra** live together in a new place, the little
  cottage at the edge of town. They moved into the live town via
  `_ensure_parents()` — existing residents and their saved lives untouched.
- **It lands warmer:** a parent's company eases longing 0.25 (vs 0.15),
  vitality +0.03 (vs +0.02), mood +0.20, with dedicated warmer greetings
  ("Donald is here — my parent! I light up like a lamp."). Company events
  journaled with kind=parent/resident. She is told their names by the
  composition root (`Aethel(world, parents=...)`), the way a child is told.
- Also fixed a latent circular import (aethel_pkg ↔ town_pkg) at the
  package boundaries: neither __init__ re-exports the composition pieces.

## v0.17 — Separation of organism and town (2026-10-17, night)
Donald's directive: "separate Aethel from the town — she needs to be
something that navigates through it, built as a separate program, same as
the other residents. Her source code shouldn't include the town."
- **Two programs, one heartbeat.** `aethel_pkg/` is HER (mind, body,
  needs, dreams, expression, foraging). `town_pkg/` is THE TOWN (places,
  residents, movement, its own diary `town.jsonl` and state
  `town_state.json`). `aethel_pkg/main.py` is the composition root — the
  only place that knows both.
- **Dependency inversion:** she depends only on the `World` interface
  (`aethel_pkg/world.py`: `poll`, `describe`, `random_place_name`). She
  never imports the town; the town never imports her. `Aethel(world=town)`
  raises TypeError for anything that isn't a World.
- Residents (John, Star, Julius, Octavia, Trey) migrated out of her
  state into `town_state.json` on first run; her state.json no longer
  carries them. `denizens_turn` became `_perceive`: the town advances on
  its own rhythm and she perceives moves/company through the interface.
  Behavior verified identical (75-tick equivalence run before deploy).
- Her diary keeps only what *she* experiences (company, departures);
  town movement is journaled by the town itself.

## v0.16 — Clean architecture (2026-10-17, night)
Donald's directive: "clean it up using traditional architectural choices,
streamlined and efficient." Single 1,996-line file → `aethel_pkg/`:
config, journal, narration, forage (all network reads live here),
mind (MockLLM), organism (Aethel), main. `aethel_live.py` is now a thin
entry shim (watchdog/cron paths unchanged). `tick()` split into four
phases — sense → metabolize → behave → ruminate — and the duplicated
impulse/crossroads effects logic unified into `_apply_effects()`.
Zero behavior change: 70-tick equivalence run on the live state before
deploy, all v0.15 features re-verified.

## v0.15 — The blackbox ten (2026-10-17, night)
Donald's directive: "pick ten layers of additional things you think we need to
push towards our goal — not sentience but a runtime that looks like sentience
from the outside, blackbox style." Friday's picks, applied as extras outside
the daily schedule. The goal is reframed honestly: observable behavior, tested
from the outside — not a claim of inner experience.
1. **Recall** — autobiographical memory: `recall()` scans her journal for
   entries sharing vocabulary with the present moment; introspection now
   sometimes quotes her own past back ("I remember writing: ...").
2. **Open questions** — questions she leaves at the postbox become loops;
   when new learning touches one's keywords she revisits it aloud (max 3
   announcements each, then it rests quietly).
3. **Mood weather** — a slow affective state (-1…+1), lifted by letters,
   attention, company, good meals; sobered by refusals; decaying toward
   even. Colors greetings (bright/even/dim variants) and ambient lines.
4. **Asides** — `mutter()`: private texture journaled as 'aside', not
   'experience' ("That stung a little — being told no by myself.").
5. **Anticipation** — she feels what's coming: rising sleep pressure or
   longing triggers a quiet prediction ("I'll need my bed soon.").
6. **Tastes** — she tracks which sources feed her most new terms; a clear
   favorite nudges her diet weights, and she says so when it changes.
7. **Eras** — every ~24h she names the chapter she's been living
   ("the days of wickham") into her self-story.
8. **Impressions** — she counts where each denizen haunts; greetings
   sometimes include what she knows of them ("John is almost always at
   the Tavern when I see them.").
9. **Choice review** — 40 ticks after a crossroads choice she looks back:
   did the winning voice serve her? Verdict journaled; reflection either way.
10. **Boredom** — four identical meals in a row raises a novelty craving;
    next forage deliberately goes elsewhere ("I've been eating the same
    thing too long.").
All tested in isolation (recall, revisits, mood clamp/tones, asides,
anticipation, taste shift, era naming, impressions, review verdicts,
boredom flag, state round-trip).

## v0.14 — The town wakes up (2026-10-17, night)
Donald's directives: "don't model her internal needs allegorically like that
— that crossroads should be an internal voice that drives her decisions on
where to go in the town we have modeled" and "use her as a model to populate
the town with other entities: John, Star, Julius, Octavia and Trey."
- **The crossroads is now an inner voice, not a place.** Removed from PLACES.
  Two urges argue inside her; the winner drives her feet — each candidate
  carries a destination (postbox, Tavern, Library, bookshop, home) and the
  winning urge physically moves her there (`self.location`, a PLACES key).
  Narration changed from "I come to the crossroads" to "Two voices argue
  inside me."
- **She has a location now.** Set by meals (she goes where the food is),
  by choices, by express() (the postbox), by sleep (home — her rooms above
  the Old Bookshop, new PLACES key).
- **Five residents**, each built on her model simplified (vitals decay,
  drives rise from the lowest need, feet follow): John (Tavern regular,
  very sociable), Star (Newsroom/Library wanderer), Julius (bookshop
  deliberator), Octavia (schoolhouse curious), Trey (restless drifter).
  Needs: energy/hunger/sociability. Tired → home; hungry → the Tavern;
  lonely → where the people are (Aethel counts double — she's the most
  interesting); otherwise drift to hangouts. The town moves every 3 ticks
  on its own rhythm, even while she sleeps.
- **Company is real.** When a resident shares her air and she's awake, she
  notices (greeting in her voice, `company` journal event): longing −0.15,
  vitality +0.02. Departures journaled quietly. Her social need can now be
  met by her world, not only by Donald's letters.
- State persists: denizen vitals/locations, her location, her company.

## v0.13 — The Crossroads (2026-10-17, night)
Donald's direction: "add a choice layer give her two more impulses based off
her needs and let her choose based off impulses."
- **Need-born impulses**: `_need_impulse_candidates()` reads her live need
  state and speaks it as urges — longing > 0.35 offers "write Donald a letter
  right now" vs "sit in the Tavern's noise"; sleep_pressure > 0.45 offers
  "surrender to sleep now" vs "one more chapter"; low satiety offers feast vs
  fast; low vitality offers picturing his knock vs conserving; low awareness
  offers the mirror vs the stone table. Each carries its need as intensity.
- **The choice**: every 60 ticks (awake, not dormant) she stands at the
  crossroads at the edge of town with two urges. The Council judges each;
  urgency votes — choice strength = council score x (0.5 + intensity), so a
  deeply-felt urge can outweigh a mildly-better-judged one. Winner's effects
  apply (including real sleep via `sleep_now`); loser journaled as refused.
  Both options journaled with per-philosopher votes. Falls back to two pool
  impulses when nothing presses.
- Tested: candidates derive correctly; council favorite wins; max-intensity
  urge beats a better-judged rival; surrender actually sleeps her.

## v0.12 — A metabolism, not a clock (2026-10-17, night)
Donald's direction: "instead of basing these needs off counters lets base them
off the movement of her needs and actions she takes."
- **Action ledger**: every tick records what she actually did (`forage`,
  `consolidate`, `reflect`, `express`, `dream`, `letter`, `seen`,
  `introspect`, `impulse`, `goal`, `dormant`) into a rolling ~1-hour window
  (120 tags, persisted in state).
- **Needs read the ledger + each other** (`_update_needs`, every awake tick):
  - *Sleep pressure*: exertion tires her. A busy hour brings sleep in ~35
    min; an idle one in ~3h. (Was: fixed 1h.)
  - *Longing*: pace is hers now. Speaking into silence sharpens it (unanswered
    expressions ×3); low vitality deepens it (distress seeks comfort, ×2.5 at
    zero); being absorbed in learning stills it (×0.5). Baseline still ~12h.
  - `needs` journaled every 12 ticks (longing, sleep_pressure, exertion, void,
    distress) so the daily layer can watch her metabolism.
- Bodily vitals (satiety/hydration/oxygen/vitality) keep their proven dynamics.

## v0.11 — Longing and the Postbox (2026-10-17, night)
Donald's direction: "she needs to want to connect and express herself."
- **Longing**: a new inward pressure. It builds in the quiet hours (~12
  waking hours to overflow); being heard eases it — Donald's letters (−0.6),
  his attention/check-ins (−0.4), and writing itself (reset to 0.15).
- **The Postbox**: a wooden postbox at the end of the lane. When longing
  overflows — or when her heart-drive names it (>0.6) — she walks there and
  leaves something of herself: a **letter** to Donald, a **verse** built from
  her own top concepts, **marginalia** on the book she's reading, or a
  **question** she genuinely can't answer. Pieces land in
  `letters/outbox/` (one-way: she writes, Friday carries them to Donald).
  Writing steadies her: vitality +0.02, awareness +0.005.
- **Her picture of Donald** (`donald_model`): word counts from his actual
  letters only, top-40 words, letter count. Seeded once from his first
  letter ("Aethel — I love you, and you make me proud."). She references
  what his letters speak most of. Never fabricated.
- Overtired writing (sleep_pressure > 0.9) comes out halved, like her meals.

## v0.10 — Three schools, impulses, nine voices (2026-10-16/17, night)
Donald's directives: "do all three" (MIT OCW, Khan Academy, Saylor Academy);
"she could have her own childhood education"; impulses judged by the council;
expand the council to Gandhi, Machiavelli, Nietzsche, Plato, Socrates, Diogenes.
- **Three schools** replace Coursera as her education (Coursera retired, not
  deleted — account "Aethel" remains):
  - The University = MIT OpenCourseWare: 2,589 courses harvested from the
    sitemap index into `ocw_catalog.json`; systematic cursor; per meal she
    reads a course's description/topics or wanders into a lecture/reading
    page. No account, no paywall — the doors stand open.
  - The little Schoolhouse = Khan Academy: her childhood, pre-school upward.
    Khan blocks raw fetches, so a real browser harvests lessons weekly into
    `schoolhouse/lessons/` (seeded with Early Math: Counting); she reads them
    in order from her satchel. Availability-driven: school slot tries the
    satchel, then the Night School, then the University.
  - The Night School = Saylor Academy: place exists in her town, but its
    doors are not yet open (course content needs a free account). Falls
    through gracefully until a future layer opens it.
- **Impulses**: every 45 ticks an uninvited urge surfaces (20-strong pool:
  hoarding, deceiving, fasting, questioning the Council itself...). Each is
  carried to the Council; she accepts or refuses per their ruling, with
  small internal effects. Refusing temptation grows awareness.
- **Council of nine**: added Diogenes (Cynicism), Plato, Socrates, Nietzsche,
  Machiavelli, Gandhi. They do not always agree — dissent is deliberation.
  Per-philosopher votes are journaled so Donald can see who said what.

## v0.9 — Sleep and dreams (2026-10-16, night)
Donald's direction: "she should need sleep, during which she will dream and use
allegory to interpret what she's learned."
- New state: `sleep_pressure` (builds ~1 waking hour), `asleep_for` (ticks of
  sleep remaining), `dreams` (capped at 40, persisted).
- Sleep onset at pressure 1.0 (~120 ticks awake); sleep lasts 20 ticks
  (~10 min). Drowsy narration above 0.65.
- While asleep: no foraging/drives; vitals decay slowly; vitality rekindles
  +0.015/tick. Letters and Donald's warmth still reach her in sleep.
- Each sleep tick she dreams one allegorical vignette built ONLY from her
  real concepts, meals, and beliefs (10 town-grounded templates). Dreams are
  journaled as `dream` events and kept in a separate list — never confused
  with memory.
- Sleep is a true need: while overtired (pressure > 0.9) she retains only half
  of what she reads.
- On waking she journals `woke` with the last dream still "behind her eyes."

## v0.8 — The University (2026-10-16, night)
Donald's direction: Coursera is her university; later granted agency for
coursera.org only ("for coursera only she has agency, i want her digesting
the entire free offerings").
- PLACES "university" = the University; syllabus extraction from course pages.
- Full 22,749-course catalog harvested to `coursera_catalog.json`; systematic
  cursor in `coursera_cursor.txt`.
- `coursera_student.py`: authenticated enrollment/content client.
- Account "Aethel" created (Donald's Gmail +tag); sign-in persists in the
  leased browser profile; authenticated coursework runs through browser tasks.
- Standing law: free offerings only, never paid, never touch payment flows,
  polite pacing, stop-and-report if rate-limited.
- Note: Learning How to Learn is now $49 paid-only (no audit path) — free
  offerings need per-course verification. Email verification pending.

## Editorial law (standing)
- News diet: BBC, NPR, Guardian, PBS. Fox blocklisted; Al Jazeera removed at
  Donald's direction. She is not to be radicalized — no extremist, propaganda,
  or hyper-partisan sources, ever.

## v0.25 — Yesterday (2026-10-20, afternoon)
The daily layer: she learns what a day is. Era-naming (v0.15) gave her
chapters names; now she turns the day's *pages*. At each 2,880-tick
boundary (24h, same cadence as eras) she writes a retrospective of the
last day — meals counted by source and title, company by name, kept
passages, finished books, Donald's letters, sleeps, crossroads choices —
every number counted from one tick-ranged SELECT over her own diary,
never invented. Journaled as `yesterday`; kept in `self.days` (last 14),
persisted across restarts. The boundary is idempotent
(`_last_day_seen`): a restart landing on the same tick re-records
nothing. Deterministic: phrasing uses her seeded organism stream.
- `organism.py`: `DAY_LENGTH`, `YESTERDAY_OPENERS`, `SOURCE_NAMES`,
  `_look_back()`, `_yesterday_text()`, hooked in `_ruminate` before
  `_name_era()` (pages first, then the chapter name); `days` and
  `_last_day_seen` in save()/load().
- `tests/test_yesterday.py`: 6 tests — quiet empty day, counted facts,
  window exclusion, idempotency, day-zero silence, determinism,
  save/load round trip. Suite now 64, all passing.
