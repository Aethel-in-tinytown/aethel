"""HTTP and WebSocket adapters; optional imports never affect headless use."""

import asyncio
import importlib
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .gateway import MAX_BODY, ApiError, dispatch

LOG = logging.getLogger(__name__)


def select_engine(requested, candidates):
    """Fall back only for auto selection; operator choices must be honored."""
    if requested != "auto":
        candidates = [
            (name, module) for name, module in candidates if name == requested
        ]
        if not candidates:
            raise RuntimeError("Unknown engine: " + requested)
    for name, module in candidates:
        try:
            return name, importlib.import_module(module) if module else None
        except (ImportError, OSError) as error:
            LOG.info("%s unavailable: %s", name, error)
            if requested != "auto":
                raise RuntimeError(name + " is not available") from error
    raise RuntimeError("No usable transport engine")


def stdlib_http(gateway, root, host, port):
    """A development/small-host fallback with bounded input and socket timeouts."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def handle_request(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400)
                return
            if size < 0 or size > MAX_BODY:
                self.send_error(413)
                self.close_connection = True
                return
            if self.headers.get("Transfer-Encoding"):
                self.send_error(400)
                self.close_connection = True
                return
            body = self.rfile.read(size) if self.command == "POST" else b""
            code, headers, payload = dispatch(
                gateway,
                self.command,
                self.path,
                dict(self.headers),
                body,
                self.client_address[0],
                root,
            )
            self.send_response(code)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        do_GET = do_HEAD = do_POST = do_OPTIONS = handle_request

        def log_message(self, fmt, *args):
            LOG.info("http %s", fmt % args)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server.serve_forever, server.shutdown


def asgi_http(gateway, root, host, port, module):
    """Use Uvicorn's optimized HTTP implementation without owning the organism."""

    async def app(scope, receive, send):
        if scope["type"] != "http":
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_BODY or not message.get("more_body"):
                break
        headers = {k.decode("latin1"): v.decode("latin1") for k, v in scope["headers"]}
        target = scope["path"] + (
            "?" + scope["query_string"].decode() if scope["query_string"] else ""
        )
        code, response_headers, payload = await asyncio.to_thread(
            dispatch,
            gateway,
            scope["method"],
            target,
            headers,
            bytes(body),
            scope.get("client", ("local",))[0],
            root,
        )
        await send(
            {
                "type": "http.response.start",
                "status": code,
                "headers": [
                    (k.lower().encode(), v.encode())
                    for k, v in response_headers.items()
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"" if scope["method"] == "HEAD" else payload,
            }
        )

    server = module.Server(
        module.Config(app, host=host, port=port, lifespan="off", access_log=False)
    )
    return server.run, lambda: setattr(server, "should_exit", True)


def fast_http(gateway, root, host, port, module):
    """Adapt the native Go callback interface with explicit capability checks.

    Native builds differ. Missing response-header support must reject this engine
    rather than silently losing authentication/error/cache behavior.
    """
    # The published 0.0.2 wrapper frees response buffers immediately and has no
    # catch-all dispatcher or shutdown hook. Inspect its class before instantiation:
    # constructing it otherwise attempts an implicit Go build on the host.
    required = ("Any", "Stop")
    missing = [name for name in required if not hasattr(module.FastHttp, name)]
    if missing:
        raise RuntimeError(
            "FastHttpPy lacks required native lifecycle APIs: " + ", ".join(missing)
        )
    raise RuntimeError("Unrecognized FastHttpPy ABI; use the verified Uvicorn adapter")


def make_http(gateway, root, host, port, requested):
    candidates = [
        ("fasthttppy", "fasthttppy"),
        ("uvicorn", "uvicorn"),
        ("stdlib", None),
    ]
    while candidates:
        name, module = select_engine(requested, candidates)
        try:
            if name == "fasthttppy":
                server = fast_http(gateway, root, host, port, module)
            elif name == "uvicorn":
                server = asgi_http(gateway, root, host, port, module)
            else:
                server = stdlib_http(gateway, root, host, port)
            gateway.http_engine = name
            return server
        except (RuntimeError, AttributeError) as error:
            if requested != "auto":
                raise
            LOG.warning("%s incompatible: %s; selecting fallback", name, error)
            candidates = [(n, m) for n, m in candidates if n != name]


def websocket_thread(gateway, host, port, requested):
    """Serve public snapshots only, with bounded buffers and slow-client timeouts."""
    if requested == "none":
        return lambda: None
    try:
        name, module = select_engine(
            requested,
            [
                ("picows", "picows.websockets.asyncio.server"),
                ("websockets", "websockets.asyncio.server"),
            ],
        )
    except RuntimeError:
        if requested != "auto":
            raise
        LOG.info("WebSockets unavailable; HTTP polling enabled")
        return lambda: None
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    errors = []
    shutdown = None

    async def handle(connection):
        request = connection.request
        if request.path != "/api/v1/stream":
            await connection.close(1008, "Unknown endpoint")
            return
        origin = request.headers.get("Origin")
        allowed = gateway.public_origin or (
            "http://"
            + request.headers.get("Host", "").rsplit(":", 1)[0]
            + ":"
            + str(gateway.http_port)
        )
        if origin and origin != allowed:
            await connection.close(1008, "Origin rejected")
            return
        last = None
        try:
            while not gateway.stopping.is_set() and not gateway.closed.is_set():
                try:
                    snapshot = gateway.view()
                    identity = (snapshot["revision"], snapshot["status"]["stale"])
                    if identity != last:
                        await asyncio.wait_for(
                            connection.send(json.dumps(snapshot)), timeout=5
                        )
                        last = identity
                except ApiError:
                    pass
                await asyncio.sleep(0.2)
        except Exception:
            # Disconnects are normal; a bounded send protects other spectators.
            return

    async def main():
        nonlocal shutdown
        shutdown = asyncio.Event()
        try:
            async with module.serve(
                handle,
                host,
                port,
                max_size=MAX_BODY,
                max_queue=4,
                write_limit=65536,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=2,
            ):
                gateway.ws_engine, gateway.ws_port = name, port
                ready.set()
                await shutdown.wait()
        except Exception as error:
            errors.append(error)
            ready.set()

    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
        loop.close()

    thread = threading.Thread(target=run, name="aethel-websocket", daemon=True)
    thread.start()
    ready.wait(5)
    if errors or not ready.is_set():
        if requested != "auto":
            raise RuntimeError("WebSocket startup failed") from (
                errors[0] if errors else None
            )
        LOG.warning("WebSockets failed to start; HTTP polling enabled: %s", errors)

    def close():
        if shutdown is not None and loop.is_running():
            loop.call_soon_threadsafe(shutdown.set)
            thread.join(timeout=4)

    return close
