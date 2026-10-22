"""Build bounded public views inside the simulation's owning process.

Snapshots contain no SQLite handles, command credentials, incoming letters,
or mutable organism objects. All transports serialize this same contract.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from aethel_pkg import config
from aethel_pkg.temperament import TEMPERAMENTS
from town_pkg.places import PLACES
from . import VERSION


def temperament_records():
    """Expose behavioral constants from their authoritative Python table."""
    return [{"id": key, **record} for key, record in TEMPERAMENTS.items()]


def journal_page(store, limit=30, before=None, event=None):
    """Use monotonic database IDs for stable newest-first pagination."""
    clauses, params = (
        [
            "stream = ?",
            "event IN ('experience','dream','initiation','mood_named','letter_received')",
        ],
        ["aethel"],
    )
    if before is not None:
        clauses.append("id < ?")
        params.append(before)
    if event:
        clauses.append("event = ?")
        params.append(event)
    rows = store.db.execute(
        "SELECT id,tick,ts,event,data FROM journal WHERE "
        + " AND ".join(clauses)
        + " ORDER BY id DESC LIMIT ?",
        [*params, limit],
    ).fetchall()
    entries = [
        {
            "id": row[0],
            "n": row[1],
            "t": row[2],
            "event": row[3],
            "text": json.loads(row[4]).get("text", ""),
        }
        for row in rows
    ]
    # Incoming letter contents are private even when the organism quotes them.
    for entry in entries:
        if (
            entry["event"] == "letter_received"
            or "letter slides under my door" in entry["text"]
        ):
            entry["text"] = "A letter arrived from home."
    return {
        "entries": entries,
        "next_cursor": rows[-1][0] if len(rows) == limit else None,
    }


def build_snapshot(organism, town, store, revision):
    """Read state only after a completed tick; never join independent saves."""
    state = store.load_blob("state") or {}
    vitals = {
        **organism.vitals,
        "longing": organism.longing,
        "mood": organism.mood,
        "awareness": organism.awareness,
        "sleep_pressure": organism.sleep_pressure,
    }
    reading = next((b["title"] for b in organism.reading_list if not b["done"]), "")
    recent = journal_page(store)
    activity = next(
        (e["text"] for e in recent["entries"] if e["text"]), "A quiet moment in town."
    )
    letters = []
    for path in sorted(Path(config.outbox_dir()).glob("*.txt"), reverse=True)[:50]:
        if path.is_symlink():
            continue
        with path.open(encoding="utf-8") as letter:
            text = letter.read(20000)
        letters.append(
            {
                "id": path.name,
                "to": "you",
                "subject": path.stem.replace("_", " "),
                "text": text.partition("\n\n")[2] or text,
            }
        )
    return {
        "revision": revision,
        "world_seed": str(organism.seed),
        "tick": organism.tick_count,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "status": {
            "tick": organism.tick_count,
            "version": "v" + VERSION,
            "language": organism.language.metadata,
            "alive": True,
            "stale": False,
            "vitals": vitals,
            "location": organism.location,
            "location_pretty": town.describe(organism.location),
            "activity": activity,
            "asleep": organism.asleep_for > 0,
            "meals_eaten": organism.meals_eaten,
            "concepts": len(organism.concepts),
            "reading": reading,
            "temperament": organism.temperament,
            "temperament_pending": organism.temperament_pending,
            "mood_name": organism.mood_name,
            "top_want": state.get("top_want"),
            "grammar_rules": state.get("grammar_rules", 0),
            "grammar_last_rule": state.get("grammar_last_rule"),
        },
        "journal": recent["entries"],
        "journal_cursor": recent["next_cursor"],
        "town": {
            "places": [{"key": k, "name": v} for k, v in PLACES.items()],
            "residents": [
                {
                    "name": d.name,
                    "location": d.location,
                    "location_pretty": town.describe(d.location),
                    "kind": "parent"
                    if getattr(d, "kind", "") == "parent"
                    else "denizen",
                    "next_move_tick": town.next_turn.get(d.name),
                }
                for d in town.denizens
            ],
        },
        "letters": letters,
    }
