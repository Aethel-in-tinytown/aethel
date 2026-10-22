"""Aethel — a homeostatic organism navigating through a town.

Two programs, one heartbeat:

    aethel_pkg    HER. Mind, body, needs, dreams, expression, foraging.
                  She depends only on the World interface (world.py) —
                  her source code contains no town.
    town_pkg      THE TOWN. Places, residents, their movement, its own
                  diary (town.jsonl) and state (town_state.json).
                  Implements World; never imports her.

    aethel_pkg/main.py is the composition root: the only place that
    knows both. It builds the town, builds her against its interface,
    and runs the heartbeat.

Sandbox (structural, unchanged): stdlib only; the only network operations
are HTTP GET to public read-only sources (forage.py); the only writes are
to ~/workspace/aethel/.

Note: main is not imported here — the composition root imports town_pkg,
so importing it from this package's __init__ would close a circular
import. Import aethel_pkg.main explicitly.
"""
from .organism import Aethel

__all__ = ["Aethel"]
