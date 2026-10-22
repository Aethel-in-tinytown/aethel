# Aethel

A homeostatic digital organism living in a small simulated town. She reads, sleeps,
dreams, weighs impulses with a philosophical council, and writes letters home.
The live pixel town follows her actual Python state, with independently timed
residents, a journal, a postbox, and warm nighttime lighting.

Aethel is a performance, not a person. Her mind is heuristic software, not a
language model or a conscious being.

## Build and run

Requirements: Python 3.10+ and Node.js 22+ (Node 24 recommended).

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[web,fast]'
cd web
npm ci
npm run build
cd ..
AETHEL_HOME=/tmp/aethel-dev PYTHONHASHSEED=0 python aethel_live.py --serve
```

Open **http://127.0.0.1:8080**. WebSockets use port 8081 unless configured otherwise.
Use a dedicated persistent `AETHEL_HOME` for a continuing life; restarting resumes
that directory's SQLite state. The default is `~/workspace/aethel`.

To enable care, set `AETHEL_OWNER_TOKEN` before starting the server and enter it in
“Unlock care.” Use a long random token; it stays in the browser tab's memory.
Without a configured token, the app remains a public spectator.

```sh
# Explicit offline food for local exploration; this still runs the real organism.
AETHEL_HOME=/tmp/aethel-offline python aethel_live.py --serve --offline --time-scale 10

# Dependency-free HTTP and polling, using the same built frontend and API.
python aethel_live.py --serve --http-engine stdlib --ws-engine none

# Headless, bounded run; no web packages needed.
AETHEL_HOME=/tmp/aethel-headless python aethel_live.py --offline --seed 42 --ticks 10 --time-scale 100
```

HTTP auto mode checks FastHttpPy compatibility, then uses Uvicorn or standard-library
HTTP. The published FastHttpPy 0.0.2 wrapper lacks required lifecycle/routing APIs
and is deliberately rejected before it can trigger an implicit Go build. WebSockets
prefer picows, fall back to `websockets`, and finally to HTTP polling. The selected
engines appear in startup logs and `/api/v1/config`. See [deployment](docs/DEPLOYMENT.md).

## Optional English language analysis

The default remains standard-library heuristics. For contextual POS tags,
POS-aware lemmas, sentence extraction, and whole-token recall:

```sh
python3 -m pip install '.[nlp]'
python3 -m aethel_pkg.language_resources --download
python3 aethel_live.py --language-backend nltk   # also works with --serve
```

Omitting the flag resumes the saved backend; existing saves use heuristics.
Models are pinned and verified before ticking, with no runtime downloads or
fallback. Activation preserves historical surface counts and goal progress while
adding a lemma/alias index. NLTK lives can take different paths and use more CPU
and memory. See [installation, offline provisioning, compatibility and measured
behavior](docs/LANGUAGE.md).

## Development and checks

Start Python with `--serve` after the first frontend build. In another terminal:

```sh
cd web
npm run dev                  # http://127.0.0.1:8082; HTTP/WS proxy to Python
npm run typecheck
npm run lint
npm run format:check
npm test
npm run build
npx playwright install chromium
npm run test:e2e              # isolated offline organism; desktop + mobile
```

```sh
PYTHONHASHSEED=0 python3 -m unittest discover -s tests -q
ruff format --check setup.py aethel_live.py aethel_pkg town_pkg aethel_web tests
```

Use `npm run format` for frontend formatting. Optional Python tooling is available
with `pip install -e '.[dev]'`. Do not point tests or experiments at live state.
`?demo=1` explicitly shows a bundled illustrative snapshot; outages never silently
switch to a simulated replacement.

## Organization

- `aethel_pkg/`: organism, needs, heuristic council, seeded RNG, SQLite store.
- `town_pkg/`: residents, places, Markov choices, persisted independent schedules.
- `aethel_web/`: process supervision, snapshot projection, owner commands, transports.
- `web/`: Preact panels, Phaser town, procedural art, navigation, Vitest/Playwright.
- `tests/`: isolated Python regression and server integration tests.
- `docs/`: [API](docs/API.md), [architecture](docs/ARCHITECTURE.md),
  [rendering](docs/RENDERING.md), [deployment](docs/DEPLOYMENT.md),
  [asset provenance](docs/ASSETS.md), and [release verification](docs/VERIFICATION.md).

Same seed and world inputs produce the same life. Persisted RNG streams, resident
schedules, and save/rebuild tests protect restart fidelity. External forage uses
read-only HTTP; all organism writes remain under `AETHEL_HOME`.

Build history is recorded in [CHANGELOG.md](CHANGELOG.md). The original
`Aethel_Town.zip` is retained as the supplied source archive.

To build a distributable wheel, run the frontend build first, then
`python -m pip wheel --no-deps --wheel-dir dist .`. The wheel includes the compiled
web assets and font notices, so its `aethel --serve` command works outside the
checkout.
