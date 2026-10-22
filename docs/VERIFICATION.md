# Release verification — v0.29

Checked locally on 2026-10-22 with Python 3.10, Node 24 and Playwright Chromium.
These results cover the self-hosted implementation, not an existing live service.

| Check | Result |
| --- | --- |
| Python regression and worker/API tests | 164 passed after integrating upstream grammar changes |
| Frontend domain tests | 31 passed |
| TypeScript, ESLint, Prettier | Passed |
| Python Ruff correctness and formatting | Passed |
| Standard-library HTTP + polling browser matrix | 8 passed; 2 WS-only scenarios skipped |
| Uvicorn + picows browser matrix | 10 passed |
| Uvicorn + websockets browser matrix | 10 passed |
| Wheel contents | Exact match to the current build's 19 web assets |
| Installed wheel outside the checkout | HTTP, gzip assets, picows streaming and bounded-run shutdown passed |
| Docker Compose configuration | Valid |
| Container image build | Not run: Docker daemon access denied in this environment |

Browser scenarios run at desktop 1440×1050 and mobile 390×844. They cover real
snapshots, owner check-ins/letters/temperament requests, journal filtering, light
and quality settings, offline recovery, unavailable WS fallback, reduced motion,
absence of WebGL, and recovery from a failed lazy illustration download. No app
page errors occurred. Final visual inspection also recorded zero console warnings
or errors and no horizontal overflow.

## Performance observations

The shell is about 32 KiB before compression (about 12 KiB gzip); Phaser is a
separate lazy chunk, about 1.4 MiB before compression (about 370 KiB gzip). Font
files are local and retain their upstream licenses. Hash-named assets have
immutable cache headers; text bundles are compressed during the build.

In this software-rendered headless environment, initial WebGL frame intervals
averaged approximately 75–84 ms. Choosing Canvas, simplifying atmospheric
compositing and pooling effects reduced the final sample to approximately 33–37 ms mean
(with a 33–50 ms 95th percentile across the recorded runs). Sampled JS heap remained at about 18.2 MB across the
short observation, versus approximately 26 MB in the initial WebGL run. This is
comparative evidence on this environment, not a guaranteed FPS or a long-term
memory-leak proof. GPU-equipped browsers and sustained multi-client loads require
separate measurements.

## Repeat the checks

Use the commands in the root README. To exercise the optional streaming engines:

```sh
cd web
AETHEL_E2E_HTTP=uvicorn AETHEL_E2E_WS=picows npm run test:e2e
AETHEL_E2E_HTTP=uvicorn AETHEL_E2E_WS=websockets npm run test:e2e
```

Install the Python web/fast extras first. `AETHEL_E2E_PYTHON` selects an explicit
Python executable. CI repeats the transport matrix, runs Python checks across
3.10/3.12/3.14, and keeps browser traces on failures. The cross-version CI matrix
has been configured; only the local Python version was executed here.

FastHttpPy 0.0.2 was installed and inspected. It lacks the native lifecycle and
routing capabilities required by this adapter, so its rejection and Uvicorn
fallback are deliberate and tested; no FastHttpPy throughput result is claimed.

## Readability and shutdown follow-up

Character nameplates now use 16 px base text (previously 11 px), compensate for
small canvases, and stagger overlapping names. The header is shorter and the town
has more width on desktop and mobile. The follow-up desktop/mobile browser run
passed eight scenarios, with two WS-only scenarios skipped in polling mode.

New process-group signal regressions send repeated SIGINT as a terminal does,
exercise a snapshot larger than the IPC pipe buffer, verify SQLite integrity and
restart continuity, and keep clients connected through both websocket engines
while shutting down. The supervisor owns Ctrl+C, signal handlers do not acquire
multiprocessing locks, pending requests are released, and the snapshot reader
continues draining until the worker has exited.

## PR review follow-up

Reproduced the clean-install failure with npm 10.9.4: Vite's optional esbuild peer
was absent from the lockfile. Regenerated the lockfile with that npm version,
adding the nested esbuild 0.28.2 packages without changing existing dependency
versions. Full `npm ci` installs now pass with npm 10.9.4 and 11.12.1; the polling
CI job uses npm 10 so this compatibility remains checked.

Transport tests now replace the adapter's `importlib` reference instead of
mutating stdlib `importlib.import_module`, which mock also uses to resolve patch
targets. The full suite on local Python 3.10 passes with optional transports
(164 passed) and in a clean standard-library environment (163 passed, one optional
streaming test skipped). Python 3.12/3.14 remain covered by the configured CI
matrix; those interpreters were not run locally. The dream-fragment test now
requires actual truncation of a long fixture at a word boundary and separately
checks that short text remains intact. Container instructions explicitly describe
the unauthenticated read surface and loopback port bindings.
