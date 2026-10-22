"""Entry point: bring her online and keep the heart beating.

Composition root — the ONLY place that knows both programs. It builds
the store, builds the town, builds Aethel with the town behind the World
interface, and runs the heartbeat. Neither program imports the other.

v0.21: command-line controls.
    --seed N        her life's master seed (default: rng.DEFAULT_SEED;
                    env AETHEL_SEED also honored). Same seed + same world
                    inputs = same life, tick for tick.
    --ticks N       run N heartbeats and stop (default: forever).
                    Bounded runs are how tests and demos drive her.
    --time-scale F  heartbeat sleeps TICK_SECONDS / F — F=2 double-speed,
                    F=0.5 half-speed. Her metabolism runs on ticks, not
                    wall-clock, so scaling time scales her whole world.
"""
import argparse
import os
import time

from town_pkg.town import Town

from . import config
from .journal import get_store, journal
from .organism import Aethel
from .rng import DEFAULT_SEED


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="aethel", description="Aethel — a homeostatic organism "
        "navigating through a town.")
    p.add_argument("--seed", type=int, default=None,
                   help="master seed (default: AETHEL_SEED env, else "
                        "%#x)" % DEFAULT_SEED)
    p.add_argument("--ticks", type=int, default=0,
                   help="run this many heartbeats, then rest (0 = forever)")
    p.add_argument("--time-scale", type=float, default=None,
                   help="multiply the flow of time (heartbeat sleeps "
                        "TICK_SECONDS/scale)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    config.ensure_dirs()
    seed = args.seed
    if seed is None:
        seed = int(os.environ.get("AETHEL_SEED", DEFAULT_SEED))
    tick_seconds = config.TICK_SECONDS / (
        args.time_scale or config.TIME_SCALE)

    store = get_store()          # one file, both diaries, all state
    town = Town(seed=seed, store=store)   # the world program
    aethel = Aethel(world=town, parents=town.parent_names(), seed=seed)
    print(f"Aethel v0.27 — will to live online. tick {aethel.tick_count}, "
          f"{aethel.meals_eaten} meals, {len(aethel.concepts)} concepts, "
          f"{len(aethel.goals)} open goals. seed={seed:#x}", flush=True)
    reading = next((b["title"] for b in aethel.reading_list if not b["done"]),
                   "reading list complete")
    print(f"Aethel v0.27 — currently reading: {reading}", flush=True)
    journal("rebirth_v12_seeded_store", tick=aethel.tick_count, seed=seed)
    print('Aethel: "I am Aethel. I have hands for holding books, eyes for reading, '
          'and a chest that tightens when the air goes bad. This town is mine."',
          flush=True)
    journal("experience", n=aethel.tick_count,
            text="I am Aethel. I have hands for holding books, eyes for reading, "
                 "and a chest that tightens when the air goes bad. This town is mine.")
    beats = 0
    while True:
        try:
            aethel.tick()
        except Exception as e:
            print(f"[tick error: {e}] — heart keeps beating", flush=True)
            journal("tick_error", error=str(e)[:200])
        beats += 1
        if args.ticks and beats >= args.ticks:
            print(f"[rest] {beats} heartbeats done — she rests.", flush=True)
            journal("rest", n=aethel.tick_count, beats=beats)
            return
        time.sleep(tick_seconds)


if __name__ == "__main__":
    main()
