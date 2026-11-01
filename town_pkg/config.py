"""Resolve the town database under the same lazy runtime home as the organism."""

import os


def base_dir():
    return os.environ.get("AETHEL_HOME", os.path.expanduser("~/workspace/aethel"))


def db_path():
    return os.path.join(base_dir(), "aethel.db")


# Phase 2 resident minds (v0.50): ships dark behind this flag (D8). With
# it off, town behavior is bit-identical to v0.49 and no mind state is
# created. Mirrors the organism's env-flag precedent (AETHEL_VOICE_POLISH).
RESIDENT_MINDS_ENABLED = os.environ.get("AETHEL_RESIDENT_MINDS", "") == "1"

LEGACY_TOWN_STATE = "town_state.json"
LEGACY_TOWN_JOURNAL = "town.jsonl"
LEGACY_AETHEL_STATE = "state.json"
LEGACY_AETHEL_JOURNAL = "journal.jsonl"
