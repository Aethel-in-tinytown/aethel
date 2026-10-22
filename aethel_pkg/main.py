"""Compose the organism and town, or supervise the integrated web service.

Simulation time is counted in ticks; time-scale changes heartbeat scheduling
without introducing wall-clock entropy into organism decisions."""

import argparse
import math
import os
import time

from town_pkg.town import Town

from . import config
from .journal import get_store, journal
from .language_resources import LanguageError
from .organism import Aethel
from .rng import DEFAULT_SEED
from .version import VERSION


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="aethel",
        description="Aethel — a homeostatic organism navigating through a town.",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="master seed (default: AETHEL_SEED env, else %#x)" % DEFAULT_SEED,
    )
    p.add_argument(
        "--ticks",
        type=int,
        default=0,
        help="run this many heartbeats, then rest (0 = forever)",
    )
    p.add_argument(
        "--time-scale",
        type=float,
        default=None,
        help="multiply the flow of time (heartbeat sleeps TICK_SECONDS/scale)",
    )
    p.add_argument("--serve", action="store_true", help="serve the web app and API")
    p.add_argument(
        "--language-backend",
        choices=("heuristic", "nltk"),
        default=None,
        help="explicitly select language analysis (default: resume saved backend)",
    )
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--ws-port", type=int, default=None)
    p.add_argument("--web-root", default=None)
    p.add_argument(
        "--http-engine",
        choices=("auto", "fasthttppy", "uvicorn", "stdlib"),
        default="auto",
    )
    p.add_argument(
        "--ws-engine", choices=("auto", "picows", "websockets", "none"), default="auto"
    )
    p.add_argument(
        "--offline",
        action="store_true",
        help="use deterministic local food without network requests",
    )
    args = p.parse_args(argv)
    if args.ticks < 0 or (
        args.time_scale is not None
        and (args.time_scale <= 0 or not math.isfinite(args.time_scale))
    ):
        p.error("ticks must be nonnegative and time-scale must be positive")
    if not 1 <= args.port <= 65534 or (
        args.ws_port is not None and not 1 <= args.ws_port <= 65535
    ):
        p.error("invalid server port")
    if args.ws_port == args.port:
        p.error("HTTP and WebSocket ports must differ")
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.serve:
        from aethel_web.server import serve

        return serve(args)
    if args.offline:
        from aethel_web.worker import configure_offline

        configure_offline()
    config.ensure_dirs()
    seed = args.seed
    if seed is None:
        seed = int(os.environ.get("AETHEL_SEED", DEFAULT_SEED))
    tick_seconds = config.TICK_SECONDS / (args.time_scale or config.TIME_SCALE)

    store = get_store()
    town = Town(seed=seed, store=store)
    try:
        aethel = Aethel(
            world=town,
            parents=town.parent_names(),
            seed=seed,
            language_backend=args.language_backend,
        )
    except LanguageError as exc:
        raise SystemExit(str(exc)) from exc
    seed = aethel.seed
    print(
        f"Aethel v{VERSION} — will to live online. tick {aethel.tick_count}, "
        f"{aethel.meals_eaten} meals, {len(aethel.concepts)} concepts, "
        f"{len(aethel.goals)} open goals. seed={seed:#x}",
        flush=True,
    )
    reading = next(
        (b["title"] for b in aethel.reading_list if not b["done"]),
        "reading list complete",
    )
    print(f"Aethel v{VERSION} — currently reading: {reading}", flush=True)
    journal("rebirth_v12_seeded_store", tick=aethel.tick_count, seed=seed)
    print(
        'Aethel: "I am Aethel. I have hands for holding books, eyes for reading, '
        'and a chest that tightens when the air goes bad. This town is mine."',
        flush=True,
    )
    journal(
        "experience",
        n=aethel.tick_count,
        text="I am Aethel. I have hands for holding books, eyes for reading, "
        "and a chest that tightens when the air goes bad. This town is mine.",
    )
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
