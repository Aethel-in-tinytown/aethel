"""Supervise a single simulation worker and interchangeable web transports."""

import logging
import multiprocessing
import os
import signal
import threading
import time
from pathlib import Path

from aethel_pkg import config
from aethel_pkg.rng import DEFAULT_SEED
from .gateway import Gateway
from .transports import make_http, websocket_thread
from .worker import worker_main


def serve(args):
    """One launch command; no HTTP worker can accidentally start another life."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    ctx = multiprocessing.get_context("spawn")
    incoming, outgoing = ctx.Queue(64), ctx.Queue(16)
    stop = ctx.Event()
    seed = (
        args.seed
        if args.seed is not None
        else int(os.environ.get("AETHEL_SEED", DEFAULT_SEED))
    )
    options = {
        "home": config.base_dir(),
        "seed": seed,
        "ticks": args.ticks,
        "interval": config.TICK_SECONDS / (args.time_scale or config.TIME_SCALE),
        "offline": args.offline,
        "language_backend": args.language_backend,
    }
    worker = ctx.Process(
        target=worker_main,
        args=(options, incoming, outgoing, stop),
        name="aethel-organism",
    )
    gateway = Gateway(
        incoming,
        outgoing,
        worker,
        os.environ.get("AETHEL_OWNER_TOKEN", ""),
        options["interval"],
    )
    gateway.public_origin = os.environ.get("AETHEL_PUBLIC_ORIGIN", "").rstrip("/")
    gateway.http_port = args.port
    packaged = Path(__file__).resolve().parent / "static"
    root = (
        Path(args.web_root).resolve()
        if args.web_root
        else (
            packaged
            if (packaged / "index.html").is_file()
            else Path(__file__).resolve().parent.parent / "web" / "dist"
        )
    )
    if not (root / "index.html").is_file():
        raise SystemExit("Build the frontend first: cd web && npm ci && npm run build")
    run_http, close_http = make_http(
        gateway, root, args.host, args.port, args.http_engine
    )
    close_ws = lambda: None
    http_thread = None
    previous = {}
    listener = None
    shutdown_requested = False

    def request_shutdown(_signal, _frame):
        # Signal handlers must not acquire multiprocessing locks. A signal can
        # interrupt Event.wait/is_set while that same lock is already held.
        nonlocal shutdown_requested
        shutdown_requested = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.signal(sig, request_shutdown)
    try:
        # Ignored SIGINT survives spawn/exec, covering imports before worker_main.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            worker.start()
        finally:
            signal.signal(signal.SIGINT, request_shutdown)
        listener = threading.Thread(
            target=gateway.listen, daemon=True, name="aethel-snapshots"
        )
        listener.start()
        close_ws = websocket_thread(
            gateway, args.host, args.ws_port or args.port + 1, args.ws_engine
        )
        http_thread = threading.Thread(target=run_http, daemon=True, name="aethel-http")
        http_thread.start()
        logging.info(
            "Aethel http://%s:%s (%s; websocket=%s)",
            args.host,
            args.port,
            gateway.http_engine,
            gateway.ws_engine,
        )
        while not shutdown_requested and not stop.is_set():
            time.sleep(0.1)
            if not worker.is_alive():
                gateway.error = "Simulation worker exited"
                # Keep serving the last snapshot, but report failed readiness.
            if not http_thread.is_alive():
                raise RuntimeError("HTTP server exited unexpectedly")
    finally:
        gateway.begin_shutdown()
        stop.set()
        # Keep draining output until the worker exits: its Queue feeder may be
        # flushing a snapshot larger than the pipe buffer during process exit.
        close_ws()
        if http_thread:
            closer = threading.Thread(
                target=close_http, daemon=True, name="aethel-http-stop"
            )
            closer.start()
            closer.join(timeout=1)
            http_thread.join(timeout=2)
        if worker.pid is not None:
            worker.join(timeout=5)
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=2)
            if worker.is_alive():
                worker.kill()
                worker.join(timeout=1)
        gateway.closed.set()
        if listener:
            listener.join(timeout=0.5)
        for mailbox in (incoming, outgoing):
            # Unaccepted requests need not flush to an exited worker. Durable
            # commands already live in SQLite and will be replayed on restart.
            mailbox.cancel_join_thread()
            mailbox.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    if worker.exitcode and gateway.snapshot is None:
        raise SystemExit(
            gateway.error or "Simulation failed before its first snapshot; inspect logs"
        )
