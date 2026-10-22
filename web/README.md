# Aethel web app

Preact panels and a Phaser pixel town, backed by the Python organism. See the
[root README](../README.md) for the complete build and launch sequence.

```sh
npm ci
npm run build       # fingerprinted, precompressed dist/ and Python package assets
npm run dev         # http://127.0.0.1:8082; proxies to Python on 8080/8081
npm run typecheck
npm run lint
npm run format:check
npm test
npm run test:e2e     # isolated Python server; desktop + mobile browser scenarios
```

Run `npx playwright install chromium` before the first browser test. Python serves
the production build at port 8080; the development proxy requires that backend
running. `AETHEL_DEV_BACKEND` and `AETHEL_DEV_WS_PORT` override development targets.

Live data is configured at runtime through `/api/v1/config`. `?demo=1` explicitly
loads an illustrative snapshot. A network outage always retains the last real
state and retries; it never replaces the organism with an independent UI life.

- `src/sim/`: typed protocol, data hook, scenery noise and pure movement/navigation.
- `src/game/`: cached procedural art, sprites, scene lifecycle and bounded effects.
- `src/ui/`: accessible spectator panels, care controls, filters and presentation.
- `tests/`, `e2e/`: domain tests and real-browser integration scenarios.

The canonical [API](../docs/API.md), [rendering](../docs/RENDERING.md), and
[deployment](../docs/DEPLOYMENT.md) guides live in the repository's `docs/` directory.
