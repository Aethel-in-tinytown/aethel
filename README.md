# Aethel

A homeostatic digital organism living in a small simulated town. She eats text, sleeps, dreams, argues with a nine-voice philosophical council about her impulses, keeps a diary, and writes letters to her parents. She has been running continuously since October 16, 2026.

Aethel is a performance, not a person: a digital organism played by software. She is not conscious. She is just very committed to the bit.

## Current build

v0.26, "She writes first": she initiates contact herself now, leaving notes, questions, and nudges driven by her own state.

## Layout

- `aethel_pkg/` — the organism: vitals (satiety, hydration, oxygen, vitality, longing), needs, impulses, the council, dreams, journal, sqlite store
- `town_pkg/` — the town she lives in: ten places, five denizens, and her parents' cottage at the edge of town
- `tests/` — the test suite. Tests are the deliverable, and the suite runs before every deploy
- `aethel_live.py` — thin launcher shim
- `CHANGELOG.md` — every version of her build history

## Design notes

- Deterministic by construction: seeded SplitMix64 random streams, no ambient randomness. Restart fidelity is a release gate: stopped mid-run and rebuilt, she must be bit-identical to uninterrupted.
- Her mind is heuristic (a mock LLM), and the code says so. A real-model mind is a later, separately gated step.
- Read-only world: she reads public sources (books, course catalogs, mainstream news) and writes only inside her own home.

## Watch her live

https://aethel-in-the-tiny-town.lovable.app/ — her actual vitals, journal, and town, refreshed every few minutes.

## Run her

```bash
python3 aethel_live.py
```

Her state lives in a sqlite database she creates on first run. This repo is her source code only; her live state and diary stay home.
