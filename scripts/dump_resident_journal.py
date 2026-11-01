"""Read-only dump of the residents' lives and journals (v0.50, D10).

Donald's ruling: he should be able to read the residents' days during
Phase 2 without waiting for the Phase 3 spectator switcher. This script
opens the LIVE database read-only (sqlite URI mode=ro, the tone_audit
precedent; it writes nothing) and prints, per roster resident: job,
workplace, residence, work window, current location, all five vitals
plus mood, and the most recent journal lines from their own stream.

Usage: python3 scripts/dump_resident_journal.py [--lines N] [--name Trey]
The database path follows the town's own rule (AETHEL_HOME or
~/workspace/aethel), via town_pkg.config.db_path().
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]

from town_pkg import config as town_config  # noqa: E402
from town_pkg.places import PLACES  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lines", type=int, default=12)
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    db = sqlite3.connect(f"file:{town_config.db_path()}?mode=ro", uri=True)
    row = db.execute(
        "SELECT value FROM kv WHERE stream = 'town' AND key = 'state'"
    ).fetchone()
    if not row:
        print("No town state found.")
        return 1
    blob = json.loads(row[0])
    denizens = {d["name"]: d for d in blob.get("denizens", [])}
    for name, d in denizens.items():
        if args.name and name != args.name:
            continue
        mind = d.get("mind") or {}
        mv = mind.get("vitals") or {}
        vitals = dict(d.get("vitals") or {})
        vitals.update(mv)
        start, end = d.get("work_start"), d.get("work_end")
        window = (
            f"{start // 120:02d}:00-{end // 120:02d}:00" if start is not None else "no shift"
        )
        print(f"== {name} — {d.get('job') or 'no job'}")
        print(f"   workplace: {PLACES.get(d.get('workplace'), d.get('workplace'))}"
              f"   residence: {d.get('residence')}"
              f"   window: {window}")
        print(f"   at: {PLACES.get(d.get('location'), d.get('location'))}"
              f"   vitals: " + ", ".join(f"{k}={v:.2f}" for k, v in sorted(vitals.items()))
              + (f"   mood: {mind.get('mood', 0.0):.2f} ({mind.get('mood_band', 'mid')})" if mind else "   (no mind)"))
        stream = "resident:" + name.lower()
        rows = db.execute(
            "SELECT tick, event, data FROM journal WHERE stream = ? ORDER BY id DESC LIMIT ?",
            (stream, args.lines),
        ).fetchall()
        for tick, event, data in reversed(rows):
            payload = json.loads(data)
            print(f"   [{tick}] {event}: {payload.get('line', '')}")
        if not rows:
            print("   (no journal lines yet)")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
