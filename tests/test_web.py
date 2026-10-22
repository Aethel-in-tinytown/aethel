"""Public transport boundaries and deterministic worker behavior use isolated homes."""

import contextlib
import gzip
import io
import json
import multiprocessing
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aethel_pkg.main import parse_args
from aethel_pkg.store import Store
from aethel_pkg.rng import SplitMix64
from aethel_web.gateway import ApiError, Gateway, dispatch, validate_command
from aethel_web.transports import make_http, select_engine
from aethel_web.worker import worker_main
from town_pkg.town import Town


class Alive:
    def is_alive(self):
        return True


class TestGateway(unittest.TestCase):
    def setUp(self):
        self.gateway = Gateway(
            queue.Queue(64), queue.Queue(16), Alive(), "owner-secret"
        )
        self.gateway.snapshot = {
            "revision": 2,
            "status": {"stale": False},
            "letters": [],
            "town": {},
        }
        self.gateway.updated = time.monotonic()

    def request(self, method, target, headers=None, body=b"", root=None):
        status, response_headers, data = dispatch(
            self.gateway, method, target, headers or {}, body, static_root=root
        )
        return (
            status,
            response_headers,
            json.loads(data)
            if "json" in response_headers.get("Content-Type", "")
            else data,
        )

    def test_authentication_and_origin_checks(self):
        for headers, expected in [
            ({}, 401),
            ({"authorization": "Bearer wrong"}, 401),
            (
                {
                    "authorization": "Bearer owner-secret",
                    "origin": "https://evil.test",
                    "host": "localhost",
                },
                403,
            ),
        ]:
            self.assertEqual(
                self.request("POST", "/api/v1/commands", headers)[0], expected
            )
        self.gateway.token = ""
        self.assertEqual(self.request("POST", "/api/v1/commands")[0], 403)

    def test_shutdown_releases_waiting_requests_without_closing_the_output_reader(self):
        errors = []

        def pending():
            try:
                self.gateway.request("journal", {})
            except ApiError as error:
                errors.append(error.status)

        thread = threading.Thread(target=pending)
        thread.start()
        self.gateway.incoming.get(timeout=1)
        self.gateway.begin_shutdown()
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [503])
        self.assertFalse(self.gateway.closed.is_set())
        with self.assertRaises(ApiError):
            self.gateway.request("commands")

    def test_public_snapshot_and_staleness(self):
        self.assertEqual(self.request("GET", "/api/v1/snapshot")[2]["revision"], 2)
        self.gateway.updated -= 100
        self.assertTrue(self.request("GET", "/api/v1/snapshot")[2]["status"]["stale"])
        self.assertFalse(self.gateway.snapshot["status"]["stale"])

    def test_bad_json_limits_and_unknown_routes(self):
        auth = {
            "Authorization": "Bearer owner-secret",
            "Content-Type": "application/json",
        }
        self.assertEqual(self.request("POST", "/api/v1/commands", auth, b"{")[0], 400)
        self.assertEqual(
            self.request("POST", "/api/v1/commands", auth, b" " * 17000)[0], 413
        )
        self.assertEqual(self.request("GET", "/api/v1/journal?limit=100000")[0], 400)
        self.assertEqual(self.request("GET", "/api/v1/not-real")[0], 404)

    def test_static_paths_and_cache_policy(self):
        with tempfile.TemporaryDirectory() as home:
            Path(home, "index.html").write_text("<h1>Town</h1>")
            Path(home, "main-ABCDEFGH.js").write_text("export {}")
            Path(home, "main-ABCDEFGH.js.gz").write_bytes(gzip.compress(b"export {}"))
            for target in ["/../README.md", "/%2e%2e/README.md", "/.env", "/missing"]:
                self.assertEqual(self.request("GET", target, root=home)[0], 404)
            self.assertEqual(self.request("GET", "/", root=home)[2], b"<h1>Town</h1>")
            self.assertIn(
                "immutable",
                self.request("GET", "/main-ABCDEFGH.js", root=home)[1]["Cache-Control"],
            )

    def test_compressed_assets_and_command_history_privacy(self):
        with tempfile.TemporaryDirectory() as home:
            Path(home, "main-ABCDEFGH.js").write_bytes(b"export {}")
            Path(home, "main-ABCDEFGH.js.gz").write_bytes(gzip.compress(b"export {}"))
            status, headers, data = self.request(
                "GET", "/main-ABCDEFGH.js", {"Accept-Encoding": "gzip"}, root=home
            )
            self.assertEqual(status, 200)
            self.assertEqual(headers["Content-Encoding"], "gzip")
            self.assertEqual(gzip.decompress(data), b"export {}")
        self.assertEqual(self.request("GET", "/api/v1/commands")[0], 401)

    def test_command_validation_and_rate_limit(self):
        for value in [
            None,
            {},
            {"id": "../bad/path", "kind": "letter"},
            {"id": "valid-id-1", "kind": "temperament", "temperament": "../x"},
            {"id": "valid-id-1", "kind": "letter", "text": " "},
            {"id": "valid-id-1", "kind": "letter", "text": "\ud800"},
            {"id": "valid-id-1", "kind": "temperament", "temperament": []},
            {"id": "valid-id-1", "kind": "letter", "text": "a" * 4001},
        ]:
            with self.assertRaises(ApiError):
                validate_command(value)
        self.assertEqual(
            validate_command(
                {"id": "valid-id-1", "kind": "check-in", "extra": "ignored"}
            ),
            {"id": "valid-id-1", "kind": "check-in"},
        )
        for _ in range(20):
            self.gateway.rate_limit("same-peer")
        with self.assertRaises(ApiError):
            self.gateway.rate_limit("same-peer")

    def test_fallback_and_explicit_engine_errors(self):
        # Replace the adapter's module reference, leaving stdlib importlib intact
        # for unittest.mock's own resolution of subsequent patch targets.
        with patch("aethel_web.transports.importlib") as imports:
            imports.import_module.side_effect = ImportError
            self.assertEqual(
                select_engine("auto", [("fast", "not-installed"), ("stdlib", None)])[0],
                "stdlib",
            )
            with self.assertRaises(RuntimeError):
                select_engine("fast", [("fast", "not-installed")])
        fake = type("Module", (), {"FastHttp": type("FastHttp", (), {})})
        with (
            patch("aethel_web.transports.importlib") as imports,
            patch(
                "aethel_web.transports.asgi_http",
                return_value=(lambda: None, lambda: None),
            ),
        ):
            imports.import_module.return_value = fake
            run, shutdown = make_http(self.gateway, None, "127.0.0.1", 0, "auto")
            self.assertEqual(self.gateway.http_engine, "uvicorn")


class TestLaunchOptions(unittest.TestCase):
    def test_invalid_clocks_and_conflicting_ports_fail_before_startup(self):
        for argv in [
            ["--time-scale", "nan"],
            ["--time-scale", "inf"],
            ["--time-scale", "0"],
            ["--ticks", "-1"],
            ["--port", "8080", "--ws-port", "8080"],
        ]:
            with (
                self.subTest(argv=argv),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                parse_args(argv)


class TestTransactionsAndSchedules(unittest.TestCase):
    def test_outer_transaction_rolls_back_journal_and_state_together(self):
        store = Store(":memory:")
        with self.assertRaises(ValueError):
            with store.transaction():
                store.log("test", {})
                store.save_blob("state", {"tick": 1})
                raise ValueError("abort")
        self.assertEqual(store.recent(), [])
        self.assertIsNone(store.load_blob("state"))
        store.close()

    def test_saved_seed_wins_over_a_different_restart_seed(self):
        with StoreContext() as store:
            original = Town(123, store)
            original.poll(1, "home")
            original.save()
            rebuilt = Town(456, store)
            self.assertEqual(rebuilt.seed, 123)
            self.assertEqual(
                original.streams.stream("a-new-schedule").random(),
                rebuilt.streams.stream("a-new-schedule").random(),
            )

    def test_gamma_waits_and_independent_persisted_schedules(self):
        rng = SplitMix64(42)
        values = [Town._wait(rng) for _ in range(10000)]
        self.assertAlmostEqual(sum(values) / len(values), 3, delta=0.15)
        self.assertGreater(len(set(values)), 10)
        with StoreContext() as store:
            town = Town(42, store)
            town.poll(1, "home")
            self.assertGreater(len(set(town.next_turn.values())), 1)
            saved = dict(town.next_turn)
            rebuilt = Town(42, store)
            self.assertEqual(saved, rebuilt.next_turn)
            for n in range(2, 100):
                self.assertEqual(town.poll(n, "home"), rebuilt.poll(n, "home"))


class StoreContext:
    def __enter__(self):
        self.store = Store(":memory:")
        return self.store

    def __exit__(self, *args):
        self.store.close()


class TestWorkerIntegration(unittest.TestCase):
    def test_snapshots_commands_and_receipts_survive_restart(self):
        ctx = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as home:

            def start():
                incoming, outgoing, stop = ctx.Queue(64), ctx.Queue(16), ctx.Event()
                worker = ctx.Process(
                    target=worker_main,
                    args=(
                        {"home": home, "seed": 42, "interval": 0.1, "offline": True},
                        incoming,
                        outgoing,
                        stop,
                    ),
                )
                gateway = Gateway(incoming, outgoing, worker, "test-token", 0.1)
                worker.start()
                thread = threading.Thread(target=gateway.listen, daemon=True)
                thread.start()
                return worker, gateway, stop, thread

            worker, gateway, stop, thread = start()
            command = {
                "id": "test-letter-0001",
                "kind": "letter",
                "text": "A private letter from home.",
            }
            try:
                first = gateway.request("command", command)
                self.assertEqual(first["status"], "accepted")
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    records = gateway.request("commands")
                    if records and records[0]["status"] == "applied":
                        break
                    time.sleep(0.05)
                self.assertEqual(records[0]["status"], "applied")
                duplicate = gateway.request("command", command)
                self.assertEqual(duplicate["tick"], records[0]["tick"])
                snapshot = gateway.view()
                self.assertEqual(snapshot["tick"], snapshot["status"]["tick"])
                self.assertGreaterEqual(snapshot["status"]["grammar_rules"], 5)
                self.assertIsInstance(snapshot["status"]["grammar_last_rule"], str)
                self.assertNotIn(command["text"], json.dumps(snapshot))
                page = gateway.request("journal", {"limit": 2})
                self.assertLessEqual(len(page["entries"]), 2)
                self.assertNotIn(command["text"], json.dumps(page))
            finally:
                stop.set()
                worker.join(5)
                gateway.closed.set()
                thread.join(1)
                if worker.is_alive():
                    worker.terminate()
                    worker.join()
            worker, gateway, stop, thread = start()
            try:
                duplicate = gateway.request("command", command)
                self.assertEqual(duplicate["status"], "applied")
                self.assertEqual(duplicate["tick"], records[0]["tick"])
            finally:
                stop.set()
                worker.join(5)
                gateway.closed.set()
                thread.join(1)
                if worker.is_alive():
                    worker.terminate()
                    worker.join()
