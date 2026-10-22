"""Resolve the town database under the same lazy runtime home as the organism."""

import os


def base_dir():
    return os.environ.get("AETHEL_HOME", os.path.expanduser("~/workspace/aethel"))


def db_path():
    return os.path.join(base_dir(), "aethel.db")


LEGACY_TOWN_STATE = "town_state.json"
LEGACY_TOWN_JOURNAL = "town.jsonl"
LEGACY_AETHEL_STATE = "state.json"
LEGACY_AETHEL_JOURNAL = "journal.jsonl"
