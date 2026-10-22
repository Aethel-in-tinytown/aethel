# Web API v1

HTTP and WebSocket transports share a single completed-tick snapshot. The browser
uses the current origin; configuration is loaded at runtime, not baked into a build.
All JSON responses use `application/json` and `Cache-Control: no-store`.

## Routes

| Method / path | Response |
| --- | --- |
| `GET /api/v1/config` | Engine names, WS port/path, proxy flag, care availability, polling interval |
| `GET /api/v1/snapshot` | Complete public view described below |
| `GET /api/v1/status` | Snapshot's `status` object |
| `GET /api/v1/town` | Places and residents, including scheduled next-turn ticks |
| `GET /api/v1/journal?limit=30&before=ID&event=dream` | Newest-first entries and `next_cursor` |
| `GET /api/v1/outbox` | `{ "letters": [...] }`, newest filenames first, at most 50 |
| `GET /api/v1/temperaments` | `{ "temperaments": [...] }` from Python's authoritative table |
| `POST /api/v1/commands` | Owner-only care receipt |
| `GET /api/v1/commands` | Owner-only latest 100 receipts, including submitted command data |
| `GET /health/live` | Worker liveness |
| `GET /health/ready` | Worker alive with an initial published snapshot |
| `WS /api/v1/stream` | Public snapshots as JSON text messages |

Journal `limit` is 1–100. `before` is an exclusive positive database ID. Entries
contain stable `id`, ISO timestamp `t`, tick `n`, `event`, and `text`. A null cursor
means the page ended. The main snapshot includes the latest 30 entries and cursor.
Incoming letter events and their direct spoken quotation are redacted from this
public journal; owner command receipts retain the original incoming text. Aethel's
later learning and outgoing writing may reflect what she has read.

## Snapshot

```json
{
  "revision": 42,
  "world_seed": "2927493121",
  "tick": 42,
  "published_at": "2026-10-22T20:00:00+00:00",
  "worker": { "alive": true, "error": null },
  "status": {
    "tick": 42, "version": "v0.29.0", "alive": true, "stale": false,
    "language": { "backend": "heuristic", "pipeline_revision": 1,
      "nltk_version": null, "resources": {} },
    "location": "wikipedia", "location_pretty": "the Library",
    "activity": "I settle into a book.", "asleep": false,
    "vitals": {
      "satiety": 0.9, "hydration": 0.8, "oxygen": 0.9,
      "vitality": 0.8, "excitement": 0.3, "longing": 0.2,
      "mood": 0.7, "sleep_pressure": 0.4, "awareness": 0.1
    },
    "meals_eaten": 8, "concepts": 20, "reading": "Frankenstein",
    "temperament": "even-keel", "temperament_pending": null,
    "mood_name": "quiet", "top_want": null,
    "grammar_rules": 5, "grammar_last_rule": "pos-adverb"
  },
  "town": { "places": [], "residents": [] },
  "journal": [], "journal_cursor": null, "letters": []
}
```

`status.language` is additive backend metadata; NLTK lives also include the pinned
package version and a resource-name-to-SHA-256 map. See [language compatibility](LANGUAGE.md).

Residents contain `name`, canonical `location`, `location_pretty`, `kind`
(`denizen` or `parent`), and `next_move_tick`. Letters have a stable filename `id`,
`to`, `subject`, and `text`. `wikipedia` maps to the renderer's Library; `memory`
is an internal pantry state, represented at home by the renderer.

`world_seed` is a decimal string to preserve full seed precision in JavaScript.
Scenery derives a separate cosmetic seed from it. A revision advances on completed ticks. Clients ignore lower revisions and retain
the last valid view on errors. `stale` becomes true on worker failure or after
three heartbeat intervals (at least 90 seconds) without a publication. Wall-clock
timestamps are presentation metadata, not simulation inputs.

## Owner commands

Send `Authorization: Bearer <owner-token>` and `Content-Type: application/json`.
The token is configured through `AETHEL_OWNER_TOKEN`; there are no user accounts.
Browser origins must match the HTTP origin or `AETHEL_PUBLIC_ORIGIN`.

```json
{ "id": "a-unique-request-0001", "kind": "check-in" }
```

```json
{ "id": "a-unique-request-0002", "kind": "letter", "text": "Hello from home." }
```

```json
{ "id": "a-unique-request-0003", "kind": "temperament", "temperament": "stillwater" }
```

IDs contain 8–64 ASCII letters, digits or hyphens; generate a UUID for each new
intent and reuse it on retries. A conflicting payload with an existing ID returns
409. Letters contain 1–4000 nonblank characters; request bodies are limited to
16 KiB. Care allows 20 authenticated POSTs per source IP per minute and at most
64 pending commands. Reverse-proxied clients share the proxy's rate bucket.

A 202 receipt means `accepted` and durably queued. `applied` means the organism
processed the signal at a completed heartbeat, with its `tick` recorded. A
**temperament receipt records processing of the request**, not immediate activation:
`status.temperament_pending` remains set until the next waking. At most one
check-in and one temperament request are delivered per tick; letters retain stable
filenames. Idempotency receipts persist across server restarts.

A worker exception rolls back its heartbeat and stops the worker; pending commands
remain available for replay after restart. The server keeps serving its last view
with failed health status. Requests waiting on a busy worker time out after five
seconds; retry commands using their original IDs.

Errors use `{ "error": { "status": 400, "message": "..." } }`. Common statuses:
400 validation, 401 token missing/invalid, 403 care disabled/origin rejected,
409 reused ID, 413 size limit, 415 content type, 429 rate limit, 503 worker busy.

## Streaming and fallback

WebSockets are public, read-only, and accept the same allowed browser origin.
They send complete snapshots on connection and revision/staleness changes; care
always uses authenticated HTTP. Frames are bounded, protocol heartbeats run every
20 seconds, and a send stalled for five seconds disconnects that spectator.

The browser bootstraps over HTTP, reconnects WS with capped jittered backoff, and
polls every five seconds while WS is unavailable. A periodic HTTP check continues
every 30 seconds while streaming. Neither mode creates an independent UI life.
