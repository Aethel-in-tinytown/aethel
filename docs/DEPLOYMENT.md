# Self-hosting

Build the frontend before launching Python. The default HTTP bind is loopback;
use `--host 0.0.0.0` only when the deployment requires it. Keep one organism process
per `AETHEL_HOME`. Deployments are self-hosted; this repository does not change any
existing public Aethel service.

## Engines and settings

| Setting | Default / purpose |
| --- | --- |
| `AETHEL_HOME` | `~/workspace/aethel`; database, books, incoming/outgoing letters |
| `AETHEL_SEED` | Fixed default; overridden by `--seed`; continuing homes restore RNG state |
| `AETHEL_OWNER_TOKEN` | Empty disables care; use a long random value |
| `AETHEL_PUBLIC_ORIGIN` | Public HTTPS origin for proxy origin checks and same-origin WS routing |
| `--port`, `--ws-port` | HTTP 8080; WS defaults to HTTP port + 1 |
| `--http-engine` | `auto`, `uvicorn`, `stdlib`, `fasthttppy` |
| `--ws-engine` | `auto`, `picows`, `websockets`, `none` |
| `--web-root` | Override built frontend directory |
| `--offline` | Supply deterministic local reading material; avoid external fetches |
| `--time-scale` | Positive heartbeat speed multiplier; does not alter tick-based metabolism |
| `--ticks` | Stop the integrated service after this many completed heartbeats; zero is unbounded |

Install `.[web,fast]` for Uvicorn, websockets and picows. `.[experimental-http]`
installs FastHttpPy solely for compatibility evaluation. Its published 0.0.2
wrapper cannot meet the shared routing/lifecycle contract and returns unmanaged
native response pointers; auto mode rejects it without instantiation. An explicit
`--http-engine fasthttppy` fails clearly. No unsupported fast engine is silently
reported as active. Do not select a server based on unrelated echo benchmarks.

With no optional Python packages, built assets and HTTP APIs still work through
the standard-library server and browser polling. For higher spectator traffic,
use Uvicorn and a reverse proxy. Explicit unavailable engines fail rather than
silently choosing another engine. Native import/ABI failures in auto mode produce
a diagnostic and proceed to a conventional fallback.

## Containers

```sh
export AETHEL_OWNER_TOKEN='replace-with-a-long-random-value'
docker compose up --build -d
docker compose logs -f
```

The multistage image builds assets with Node, runs Python as UID 10001, and stores
state in the `aethel-data` volume. Ports bind to host loopback. `docker compose down`
retains the volume; do not delete it when upgrading. Pass `--offline` as the service
command for a local installation without public reading sources.

## HTTPS reverse proxy

Expose a single HTTPS origin and set `AETHEL_PUBLIC_ORIGIN=https://town.example.com`.
Forward `/api/v1/stream` with an Upgrade-capable proxy to port 8081 and all other
paths to port 8080. For example, inside an nginx TLS server block:

```nginx
location /api/v1/stream {
    proxy_pass http://127.0.0.1:8081;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 75s;
}
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
}
```

The browser then uses `wss://town.example.com/api/v1/stream`, with no companion
port in its public URL. Terminate TLS at the proxy. Keep owner credentials out of
URLs, static assets and logs. Backend rate limits use the direct socket peer; the
server deliberately does not trust arbitrary forwarded IP headers.

## Operations and troubleshooting

Use `/health/ready` for startup/worker health and `/api/v1/config` to inspect selected
engines. After a worker failure the gateway keeps the last snapshot visible with
`stale: true`; inspect logs and restart to resume durable state. Graceful shutdown
allows five seconds for the worker, then terminates it if a source fetch is still
blocked. Its current database transaction rolls back and pending care replays.
Terminal Ctrl+C is owned by the supervisor; the worker ignores terminal SIGINT
and finishes its current tick when possible. Repeated interrupts do not enter
multiprocessing locks, and output queues remain drained until the worker exits.

Back up SQLite using its online backup API, or stop the service before copying the
database together with its WAL state and runtime letters. Never hand-edit an active
state blob. Deploy code/assets together, preserve the data volume, and restart the
single service. Health checks do not prove external reading sources are available.

For UI development, `npm run dev` serves port 8082 and proxies to Python on 8080
and WS on 8081. Override `AETHEL_DEV_BACKEND` and `AETHEL_DEV_WS_PORT` if necessary.
