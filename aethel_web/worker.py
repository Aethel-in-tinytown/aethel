"""Own the organism and SQLite in one worker process.

Commands are persisted before acknowledgment. Receipts and organism saves commit
in one transaction, so replay after a restart cannot apply a completed command
again. File signals use stable names and are recreated for uncommitted commands.
"""

import json
import logging
import os
import queue
import signal
from pathlib import Path

from aethel_pkg import config
from aethel_pkg.journal import get_store
from aethel_pkg.language_resources import LanguageError
from aethel_pkg.organism import Aethel
from town_pkg.town import Town
from .snapshot import build_snapshot, journal_page

LOG = logging.getLogger(__name__)


def configure_offline():
    """An explicit offline world supplies deterministic food without network I/O."""
    import aethel_pkg.forage as forage
    import aethel_pkg.organism as organism

    meal = {
        "source": "wikipedia",
        "title": "The little town",
        "text": "Books teach patience, care, curiosity and kindness. " * 60,
    }
    for module in (forage, organism):
        module.forage = lambda rng=None: dict(meal)
        module.forage_news = lambda rng=None: dict(meal)
        module.forage_ocw_university = lambda rng=None: dict(meal)
        module.http_get_json = lambda *args, **kwargs: {
            "extract": meal["text"],
            "title": meal["title"],
        }
        module.gutenberg_text = lambda *args: meal["text"]
        module.wikisource_chapter = lambda *args: meal["text"]


def ensure_commands(store):
    """Indexed receipts grow on disk, never as an ever-larger in-memory snapshot."""
    store.db.execute(
        "CREATE TABLE IF NOT EXISTS care_commands ("
        "id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL, tick INTEGER)"
    )
    store.db.execute("CREATE INDEX IF NOT EXISTS care_pending ON care_commands(status)")
    store.db.commit()


def command_records(store, pending=False):
    query = "SELECT id,payload,status,tick FROM care_commands"
    query += (
        " WHERE status = 'accepted' ORDER BY rowid LIMIT 64"
        if pending
        else " ORDER BY rowid DESC LIMIT 100"
    )
    rows = store.db.execute(query).fetchall()
    records = [
        {"id": row[0], "command": json.loads(row[1]), "status": row[2], "tick": row[3]}
        for row in rows
    ]
    return {r["id"]: r for r in records}


def existing_command(store, command_id):
    row = store.db.execute(
        "SELECT payload,status,tick FROM care_commands WHERE id=?", (command_id,)
    ).fetchone()
    return (
        {
            "id": command_id,
            "command": json.loads(row[0]),
            "status": row[1],
            "tick": row[2],
        }
        if row
        else None
    )


def stage_signals(records):
    """Only pending commands generate signals; requests never write runtime files."""
    staged = []
    kinds = set()
    for record in records.values():
        if record["status"] != "accepted":
            continue
        command = record["command"]
        kind = command["kind"]
        if kind in kinds and kind != "letter":
            continue
        kinds.add(kind)
        staged.append(command["id"])
        if kind == "check-in":
            Path(config.attention_path()).touch()
        elif kind == "letter":
            name = "web-" + command["id"] + ".txt"
            # An interrupted tick may already have archived this stable filename.
            archived = Path(config.letters_read_dir()) / name
            if archived.exists():
                archived.unlink()
            Path(config.letters_dir(), name).write_text(
                command["text"], encoding="utf-8"
            )
        elif kind == "temperament":
            Path(config.temperament_path()).write_text(
                command["temperament"], encoding="utf-8"
            )

    return staged


def worker_main(options, incoming, outgoing, stop):
    """Publish complete snapshots; answer owner/journal queries between ticks."""
    # The supervisor owns terminal interrupts; finish a tick before honoring stop.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    logging.basicConfig(level=logging.INFO)
    os.environ["AETHEL_HOME"] = options["home"]
    config.ensure_dirs()
    if options.get("offline"):
        configure_offline()
    store = get_store()
    town = Town(seed=options["seed"], store=store)
    try:
        organism = Aethel(
            world=town,
            parents=town.parent_names(),
            seed=options["seed"],
            language_backend=options.get("language_backend"),
        )
    except LanguageError as exc:
        outgoing.put({"fatal": str(exc)})
        stop.set()
        store.close()
        raise
    revision = organism.tick_count
    ensure_commands(store)
    records = command_records(store, pending=True)
    try:
        with store.transaction():
            organism.save()
            town.save()
        outgoing.put(
            {
                "snapshot": build_snapshot(organism, town, store, revision),
            }
        )
        import time

        next_tick = time.monotonic()
        beats = 0
        while not stop.is_set():
            # Wake promptly for commands even when the heartbeat is thirty seconds.
            try:
                request = incoming.get(
                    timeout=max(0.01, min(0.2, next_tick - time.monotonic()))
                )
                if request["type"] == "command":
                    command = request["data"]
                    previous = existing_command(store, command["id"])
                    if previous and previous["command"] != command:
                        outgoing.put(
                            {
                                "reply": request["request_id"],
                                "error": "Command ID already used",
                                "code": 409,
                            }
                        )
                    else:
                        if not previous:
                            count = store.db.execute(
                                "SELECT count(*) FROM care_commands WHERE status='accepted'"
                            ).fetchone()[0]
                            if count >= 64:
                                outgoing.put(
                                    {
                                        "reply": request["request_id"],
                                        "error": "Care queue is full",
                                        "code": 503,
                                    }
                                )
                                continue
                            with store.transaction():
                                store.db.execute(
                                    "INSERT INTO care_commands(id,payload,status) VALUES (?,?,'accepted')",
                                    (command["id"], json.dumps(command)),
                                )
                            previous = existing_command(store, command["id"])
                        outgoing.put({"reply": request["request_id"], "data": previous})
                elif request["type"] == "journal":
                    outgoing.put(
                        {
                            "reply": request["request_id"],
                            "data": journal_page(store, **request["data"]),
                        }
                    )
                elif request["type"] == "commands":
                    outgoing.put(
                        {
                            "reply": request["request_id"],
                            "data": list(
                                reversed(list(command_records(store).values()))
                            ),
                        }
                    )
            except queue.Empty:
                pass
            if time.monotonic() < next_tick:
                continue
            records = command_records(store, pending=True)
            staged = stage_signals(records)
            with store.transaction():
                organism.tick()
                for command_id in staged:
                    store.db.execute(
                        "UPDATE care_commands SET status='applied',tick=? WHERE id=?",
                        (organism.tick_count, command_id),
                    )
            revision += 1
            beats += 1
            outgoing.put(
                {
                    "snapshot": build_snapshot(organism, town, store, revision),
                }
            )
            if options.get("ticks") and beats >= options["ticks"]:
                stop.set()
                break
            next_tick = time.monotonic() + options["interval"]
    except Exception:
        LOG.exception("Simulation worker failed")
        outgoing.put({"fatal": "Simulation worker failed; inspect server logs"})
        raise
    finally:
        store.close()
