"""Transport-independent HTTP contract and a bounded simulation mailbox."""

import copy
import hmac
import json
import logging
import mimetypes
import queue
import re
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .snapshot import temperament_records

LOG = logging.getLogger(__name__)
MAX_BODY = 16_384


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Gateway:
    """Cache immutable snapshots and correlate bounded worker requests.

    Threads only touch this gateway. SQLite and organism objects stay in the
    worker. A failed or slow worker leaves its last completed snapshot visible.
    """

    def __init__(self, incoming, outgoing, worker, token="", interval=30):
        self.incoming, self.outgoing, self.worker = incoming, outgoing, worker
        self.token, self.interval = token, interval
        self.lock = threading.RLock()
        self.snapshot = None
        self.updated = 0.0
        self.error = None
        self.pending = {}
        self.rates = {}
        self.http_engine = "starting"
        self.ws_engine = "disabled"
        self.ws_port = None
        self.public_origin = ""
        self.stopping = threading.Event()
        self.closed = threading.Event()

    def listen(self):
        while not self.closed.is_set():
            try:
                message = self.outgoing.get(timeout=0.2)
            except queue.Empty:
                continue
            except (EOFError, OSError, ValueError):
                if self.closed.is_set():
                    return
                LOG.exception("Simulation mailbox closed unexpectedly")
                self.error = "Simulation mailbox closed"
                return
            with self.lock:
                if "snapshot" in message:
                    self.snapshot = message["snapshot"]
                    self.updated = time.monotonic()
                elif "fatal" in message:
                    self.error = message["fatal"]
                elif "reply" in message:
                    waiter = self.pending.get(message["reply"])
                    if waiter:
                        try:
                            waiter.put_nowait(message)
                        except queue.Full:
                            pass

    def begin_shutdown(self):
        """Stop clients promptly while keeping the worker output pipe drained."""
        self.stopping.set()
        with self.lock:
            for request_id, waiter in self.pending.items():
                if waiter.empty():
                    waiter.put_nowait(
                        {
                            "reply": request_id,
                            "error": "Server is shutting down; retry with the same command ID",
                            "code": 503,
                        }
                    )

    def request(self, kind, data=None):
        if self.stopping.is_set() or not self.worker.is_alive():
            raise ApiError(503, "Simulation is unavailable")
        request_id, waiter = str(uuid.uuid4()), queue.Queue(maxsize=1)
        with self.lock:
            if self.stopping.is_set():
                raise ApiError(503, "Server is shutting down")
            if len(self.pending) >= 64:
                raise ApiError(503, "Server is busy")
            self.pending[request_id] = waiter
        try:
            self.incoming.put_nowait(
                {"request_id": request_id, "type": kind, "data": data}
            )
            response = waiter.get(timeout=5)
            if "error" in response:
                raise ApiError(response.get("code", 400), response["error"])
            return response["data"]
        except queue.Full:
            raise ApiError(503, "Command queue is full") from None
        except queue.Empty:
            raise ApiError(
                503, "Worker is busy; retry with the same command ID"
            ) from None
        finally:
            with self.lock:
                self.pending.pop(request_id, None)

    def view(self):
        with self.lock:
            if self.snapshot is None:
                raise ApiError(503, self.error or "The town is waking up")
            data = copy.deepcopy(self.snapshot)
            data["status"]["stale"] = bool(
                self.error
                or not self.worker.is_alive()
                or time.monotonic() - self.updated > max(90, self.interval * 3)
            )
            data["worker"] = {"alive": self.worker.is_alive(), "error": self.error}
            return data

    def authorize(self, headers):
        if not self.token:
            raise ApiError(
                403, "Care controls are disabled; configure AETHEL_OWNER_TOKEN"
            )
        supplied = headers.get("authorization", "")
        if not hmac.compare_digest(
            supplied.encode("utf-8"), ("Bearer " + self.token).encode("utf-8")
        ):
            raise ApiError(401, "Owner token required")

    def rate_limit(self, peer):
        now = time.monotonic()
        with self.lock:
            if len(self.rates) > 2048:
                self.rates = {
                    k: v for k, v in self.rates.items() if v and v[-1] > now - 60
                }
                if len(self.rates) > 2048:
                    raise ApiError(429, "Too many clients")
            recent = self.rates.setdefault(peer, deque())
            while recent and recent[0] < now - 60:
                recent.popleft()
            if len(recent) >= 20:
                raise ApiError(429, "Please wait before sending more care")
            recent.append(now)


def integer(query, key, default, maximum):
    try:
        value = int(query.get(key, [default])[0])
        if not 1 <= value <= maximum:
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise ApiError(400, f"{key} must be between 1 and {maximum}") from None


def validate_command(value):
    if not isinstance(value, dict):
        raise ApiError(400, "Expected a command object")
    if not isinstance(value.get("id"), str) or not re.fullmatch(
        r"[a-zA-Z0-9-]{8,64}", value["id"]
    ):
        raise ApiError(400, "id must contain 8–64 letters, digits or hyphens")
    kind = value.get("kind")
    if kind not in ("check-in", "letter", "temperament"):
        raise ApiError(400, "Unknown care command")
    command = {"id": value["id"], "kind": kind}
    if kind == "letter":
        text = value.get("text")
        if (
            not isinstance(text, str)
            or not 1 <= len(text.strip()) <= 4000
            or "\x00" in text
        ):
            raise ApiError(400, "Letters must contain 1–4000 characters")
        try:
            text.encode("utf-8")
        except UnicodeEncodeError:
            raise ApiError(400, "Letters must contain valid Unicode text") from None
        command["text"] = text.strip()
    if kind == "temperament":
        tid = value.get("temperament")
        if not isinstance(tid, str) or tid not in {
            r["id"] for r in temperament_records()
        }:
            raise ApiError(400, "Unknown temperament")
        command["temperament"] = tid
    return command


def dispatch(
    gateway, method, target, headers, body=b"", peer="local", static_root=None
):
    """Return status, headers and bytes with identical behavior on every engine."""
    headers = {k.lower(): v for k, v in headers.items()}
    path = urlsplit(target).path
    query = parse_qs(urlsplit(target).query)
    response_headers = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
        "Cache-Control": "no-store",
    }
    try:
        if method not in ("GET", "HEAD", "POST"):
            raise ApiError(405, "Method not allowed")
        if method == "POST":
            origin = headers.get("origin")
            expected = gateway.public_origin or ("http://" + headers.get("host", ""))
            if origin and origin != expected:
                raise ApiError(403, "Origin is not allowed")
            gateway.authorize(headers)
            gateway.rate_limit(peer)
            if len(body) > MAX_BODY:
                raise ApiError(413, "Request is too large")
            if headers.get("content-type", "").split(";")[0] != "application/json":
                raise ApiError(415, "Expected application/json")
            if path != "/api/v1/commands":
                raise ApiError(404, "Unknown endpoint")
            try:
                command = validate_command(json.loads(body))
            except (ValueError, UnicodeDecodeError):
                raise ApiError(400, "Invalid JSON") from None
            data = gateway.request("command", command)
            status = 202 if data["status"] == "accepted" else 200
            # Echo receipts without their private letter contents.
            data = {k: v for k, v in data.items() if k != "command"}
        elif path == "/api/v1/config":
            data, status = (
                {
                    "api_version": 1,
                    "http_engine": gateway.http_engine,
                    "websocket_engine": gateway.ws_engine,
                    "websocket_port": gateway.ws_port,
                    "websocket_path": "/api/v1/stream",
                    "poll_ms": 5000,
                    "proxied": bool(gateway.public_origin),
                    "care_enabled": bool(gateway.token),
                },
                200,
            )
        elif path in ("/health/live", "/health/ready"):
            ready = (
                gateway.worker.is_alive()
                and (path.endswith("live") or gateway.snapshot is not None)
                and not gateway.error
            )
            data, status = (
                {"ok": ready, "worker_alive": gateway.worker.is_alive()},
                200 if ready else 503,
            )
        elif path == "/api/v1/temperaments":
            data, status = {"temperaments": temperament_records()}, 200
        elif path == "/api/v1/journal":
            args = {"limit": integer(query, "limit", 30, 100)}
            if "before" in query:
                args["before"] = integer(query, "before", 1, 2**63 - 1)
            if "event" in query:
                args["event"] = query["event"][0][:64]
            data, status = gateway.request("journal", args), 200
        elif path == "/api/v1/commands":
            gateway.authorize(headers)
            data, status = {"commands": gateway.request("commands")}, 200
        elif path in (
            "/api/v1/snapshot",
            "/api/v1/status",
            "/api/v1/town",
            "/api/v1/outbox",
        ):
            snapshot = gateway.view()
            data = (
                snapshot
                if path.endswith("snapshot")
                else (
                    {"letters": snapshot["letters"]}
                    if path.endswith("outbox")
                    else snapshot[path.rsplit("/", 1)[-1]]
                )
            )
            status = 200
        elif path.startswith("/api/"):
            raise ApiError(404, "Unknown endpoint")
        else:
            if static_root is None:
                raise ApiError(404, "Frontend has not been built")
            from urllib.parse import unquote

            root = Path(static_root).resolve()
            asset = (root / unquote(path).lstrip("/")).resolve()
            if not asset.is_relative_to(root) or any(
                p.startswith(".") for p in asset.relative_to(root).parts
            ):
                raise ApiError(404, "Not found")
            if path == "/":
                asset = root / "index.html"
            if not asset.is_file():
                raise ApiError(404, "Not found; run npm run build in web/")
            response_headers["Content-Type"] = (
                mimetypes.guess_type(asset)[0] or "application/octet-stream"
            )
            response_headers["Cache-Control"] = (
                "public, max-age=31536000, immutable"
                if re.search(r"-[A-Z0-9]{8}\.", asset.name)
                else "no-cache"
            )
            response_headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: blob:; connect-src 'self' ws: wss:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
            )
            if "gzip" in headers.get("accept-encoding", "") and asset.suffix in (
                ".js",
                ".css",
            ):
                compressed = asset.with_name(asset.name + ".gz")
                if compressed.is_file():
                    response_headers["Content-Encoding"] = "gzip"
                    response_headers["Vary"] = "Accept-Encoding"
                    return 200, response_headers, compressed.read_bytes()
            return 200, response_headers, asset.read_bytes()
        response_headers["Content-Type"] = "application/json; charset=utf-8"
        return status, response_headers, json.dumps(data, allow_nan=False).encode()
    except ApiError as error:
        response_headers["Content-Type"] = "application/json; charset=utf-8"
        return (
            error.status,
            response_headers,
            json.dumps(
                {"error": {"message": error.message, "status": error.status}}
            ).encode(),
        )
    except Exception:
        LOG.exception("Request failed: %s %s", method, path)
        return (
            500,
            {**response_headers, "Content-Type": "application/json"},
            b'{"error":{"status":500,"message":"Internal server error"}}',
        )
