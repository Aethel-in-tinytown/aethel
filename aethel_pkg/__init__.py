"""Export the deterministic organism without importing its composition root.

The core uses the standard library. Optional web transports live in aethel_web;
the town implements World and is injected by the launcher."""

from .organism import Aethel

__all__ = ["Aethel"]
