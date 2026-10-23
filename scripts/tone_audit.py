"""Tone audit (v0.35, NLTK plan Phase 4): VADER over her real reading.

Reads Aethel's LIVE database READ-ONLY (sqlite URI mode=ro — this is
reporting over her actual life, never a test instantiation, and it
writes nothing to her store). The sample is passages she actually
read and kept (state blob's kept_passages) plus what sits in her
memory, annotated with the pinned lexicon through aethel_pkg.tone —
the same code path that annotates her live reading.

Sanity flags are a human/agent judgment layer over the mechanical
scores: the script emits the annotations and a mechanical pre-flag
(thin evidence, context-only sign); the judgment column is filled
by hand after reading each excerpt and is marked as judgment in
the report. VADER was built for tweets; whether its read of her
19th-century prose is sane is exactly what the audit week decides.

Usage: python3 scripts/tone_audit.py [--db PATH] [--out PATH]
"""

import argparse
import json
import sqlite3
from pathlib import Path

from aethel_pkg import tone


def load_sample(db_path):
    uri = f"file:{db_path}?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    try:
        row = db.execute(
            "SELECT value FROM kv WHERE stream='aethel' AND key='state'"
        ).fetchone()
    finally:
        db.close()
    state = json.loads(row[0])
    kept = sorted(state.get("kept_passages", []), key=lambda k: k.get("tick", 0))
    # Evenly spaced across her kept reading, capped at 20, plus memory.
    if len(kept) > 20:
        step = len(kept) / 20
        kept = [kept[int(i * step)] for i in range(20)]
    sample = [
        {"source": k.get("source"), "title": k.get("title"),
         "tick": k.get("tick"), "text": k.get("text", "")}
        for k in kept
    ]
    seen = {s["text"][:80] for s in sample}
    for m in state.get("memory", []):
        if m.get("text", "")[:80] not in seen:
            sample.append(
                {"source": m.get("source"), "title": m.get("title"),
                 "tick": None, "text": m.get("text", "")}
            )
    return state.get("tick_count"), sample


def excerpt(text, limit=220):
    flat = " ".join(text.split())
    return (flat[:limit] + "…") if len(flat) > limit else flat


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    home = Path.home() / "workspace"
    parser.add_argument("--db", type=Path, default=home / "aethel/aethel.db")
    parser.add_argument(
        "--data-dir", type=Path, default=home / "aethel/nltk_data"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=home
        / "goals/aethel-ai-organism-experiment/files/tone-audit-2026-10-23.md",
    )
    args = parser.parse_args(argv)

    analyzer = tone.load_analyzer(args.data_dir)
    tick, sample = load_sample(args.db)

    lines = [
        "# Tone audit — pre-audit over her existing reading (2026-10-23)",
        "",
        f"Her journal stood at tick {tick} when this was read (read-only). "
        f"Sample: {len(sample)} passages she actually read — her kept "
        "passages (evenly spaced across the whole set) plus her current "
        "memory. Annotations are mechanical: pinned vader_lexicon, "
        "NLTK 3.9.2 VADER, via aethel_pkg.tone.annotate — the same code "
        "that now annotates her live reading in v0.35.",
        "",
        "The sanity column is agent judgment, added after reading each "
        "excerpt, and marked as judgment. The audit week's human review "
        "happens on this file after she has also lived a week with "
        "annotations.",
        "",
        "| # | Source | Tick | Compound | Top + | Top − | Excerpt | Sanity (judgment) |",
        "|---|--------|------|----------|-------|-------|---------|-------------------|",
    ]
    for i, item in enumerate(sample, 1):
        ann = tone.annotate(item["text"], analyzer)
        lines.append(
            "| {i} | {src} | {tick} | {c:+.4f} | {tp} | {tn} | {ex} | |".format(
                i=i,
                src=item["source"] or "?",
                tick=item["tick"] if item["tick"] is not None else "—",
                c=ann["compound"],
                tp=ann["strongest_positive_word"] or "—",
                tn=ann["strongest_negative_word"] or "—",
                ex=excerpt(item["text"]).replace("|", "/"),
            )
        )
        item["annotation"] = ann
    lines += ["", "## Summary", "", "_(filled after the judgment pass)_", ""]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out} ({len(sample)} passages, tick {tick})")
    for item in sample:
        ann = item["annotation"]
        print(
            f"{ann['compound']:+.3f} pos={ann['pos']:.2f} neg={ann['neg']:.2f} "
            f"+{ann['strongest_positive_word']} -{ann['strongest_negative_word']} "
            f":: {excerpt(item['text'], 90)}"
        )


if __name__ == "__main__":
    main()
