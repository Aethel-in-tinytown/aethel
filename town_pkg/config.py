"""Town configuration: where the town keeps its own records.

v0.21: the town's diary and saved state live in the same aethel.db as
hers — one file for the whole world — under the 'town' stream. Paths are
lazy; AETHEL_HOME redirects everything (tests run in tempdirs).
"""
import os


def base_dir():
    return os.environ.get("AETHEL_HOME",
                          os.path.expanduser("~/workspace/aethel"))


def db_path():
    return os.path.join(base_dir(), "aethel.db")


# Legacy files, read once by store migration if they exist.
LEGACY_TOWN_STATE = "town_state.json"
LEGACY_TOWN_JOURNAL = "town.jsonl"
LEGACY_AETHEL_STATE = "state.json"
LEGACY_AETHEL_JOURNAL = "journal.jsonl"
