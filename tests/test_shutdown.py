"""A terminal interrupt reaches the whole process group, not just the supervisor."""

import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


@unittest.skipUnless(os.name == "posix", "Process-group terminal signals require POSIX")
class TestServerShutdown(unittest.TestCase):
    def test_repeated_terminal_interrupts_exit_cleanly_and_preserve_state(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "index.html").write_text("<h1>Shutdown fixture</h1>")
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            command = [
                sys.executable,
                str(root / "aethel_live.py"),
                "--serve",
                "--offline",
                "--web-root",
                str(home),
                "--port",
                str(port),
                "--http-engine",
                "stdlib",
                "--ws-engine",
                "none",
                "--time-scale",
                "600",
            ]
            env = {**os.environ, "AETHEL_HOME": str(home), "PYTHONHASHSEED": "0"}
            saved_tick = 0
            for attempt in range(2):
                if attempt:
                    # A large queued snapshot exceeds the pipe buffer. The parent
                    # must keep draining while the worker's feeder flushes at exit.
                    with sqlite3.connect(home / "aethel.db") as db:
                        db.execute(
                            "INSERT INTO journal(stream,tick,ts,event,data) VALUES ('aethel',0,'2026-10-22T00:00:00Z','experience',?)",
                            (
                                json.dumps(
                                    {"text": "A long remembered moment. " * 10000}
                                ),
                            ),
                        )
                with (home / f"run-{attempt}.log").open("w+") as log:
                    process = subprocess.Popen(
                        command,
                        cwd=root,
                        env=env,
                        stdout=log,
                        stderr=log,
                        start_new_session=True,
                    )
                    try:
                        deadline = time.monotonic() + 10
                        while True:
                            try:
                                with urlopen(
                                    f"http://127.0.0.1:{port}/api/v1/snapshot",
                                    timeout=0.5,
                                ) as response:
                                    snapshot = json.load(response)
                                if snapshot["tick"] >= (
                                    3 if attempt == 0 else saved_tick
                                ):
                                    break
                            except (URLError, TimeoutError):
                                pass
                            self.assertIsNone(
                                process.poll(), "Server exited before ready"
                            )
                            self.assertLess(
                                time.monotonic(),
                                deadline,
                                "Server failed to become ready",
                            )
                            time.sleep(0.05)
                        started = time.monotonic()
                        os.killpg(process.pid, signal.SIGINT)
                        # Repeated Ctrl+C must not re-enter a multiprocessing lock.
                        time.sleep(0.02)
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGINT)
                        self.assertEqual(process.wait(timeout=5), 0)
                        self.assertLess(time.monotonic() - started, 5)
                        log.seek(0)
                        output = log.read()
                        self.assertNotIn("Traceback", output)
                        self.assertNotIn("KeyboardInterrupt", output)
                        self.assertNotIn("leaked semaphore", output)
                        with sqlite3.connect(home / "aethel.db") as db:
                            self.assertEqual(
                                db.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                            )
                            state = json.loads(
                                db.execute(
                                    "SELECT value FROM kv WHERE stream='aethel' AND key='state'"
                                ).fetchone()[0]
                            )
                            saved_tick = state["tick_count"]
                            self.assertGreaterEqual(saved_tick, snapshot["tick"])
                    finally:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=5)


@unittest.skipUnless(os.name == "posix", "Process-group terminal signals require POSIX")
class TestStreamingShutdown(unittest.TestCase):
    def test_interrupt_with_connected_websocket_exits_without_waiting_for_the_client(
        self,
    ):
        import importlib.util

        if not (
            importlib.util.find_spec("websockets")
            and importlib.util.find_spec("uvicorn")
        ):
            self.skipTest("Optional web dependencies are not installed")
        from websockets.sync.client import connect

        root = Path(__file__).resolve().parent.parent
        for engine in ("websockets", "picows"):
            if not importlib.util.find_spec(engine):
                continue
            with (
                self.subTest(engine=engine),
                tempfile.TemporaryDirectory() as directory,
            ):
                home = Path(directory)
                (home / "index.html").write_text("<h1>Streaming shutdown fixture</h1>")
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", 0))
                    port = probe.getsockname()[1]
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", 0))
                    ws_port = probe.getsockname()[1]
                with (home / "server.log").open("w+") as log:
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            str(root / "aethel_live.py"),
                            "--serve",
                            "--offline",
                            "--web-root",
                            str(home),
                            "--port",
                            str(port),
                            "--ws-port",
                            str(ws_port),
                            "--http-engine",
                            "uvicorn",
                            "--ws-engine",
                            engine,
                        ],
                        cwd=root,
                        env={**os.environ, "AETHEL_HOME": str(home)},
                        stdout=log,
                        stderr=log,
                        start_new_session=True,
                    )
                    try:
                        deadline = time.monotonic() + 10
                        while True:
                            try:
                                with urlopen(
                                    f"http://127.0.0.1:{port}/health/ready", timeout=0.5
                                ):
                                    break
                            except (URLError, TimeoutError):
                                self.assertIsNone(process.poll())
                                self.assertLess(time.monotonic(), deadline)
                                time.sleep(0.05)
                        with connect(
                            f"ws://127.0.0.1:{ws_port}/api/v1/stream",
                            origin=f"http://127.0.0.1:{port}",
                        ) as client:
                            self.assertIn("tick", json.loads(client.recv(timeout=2)))
                            os.killpg(process.pid, signal.SIGINT)
                            self.assertEqual(process.wait(timeout=5), 0)
                        log.seek(0)
                        self.assertNotIn("Traceback", log.read())
                    finally:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=5)
