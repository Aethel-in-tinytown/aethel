"""Export the deterministic organism without importing its composition root.

The core uses the standard library. Optional web transports live in aethel_web;
the town implements World and is injected by the launcher."""

__all__ = ["Aethel"]


def __getattr__(name):
    """Keep provisioning independent of simulation imports and model loaders."""
    if name == "Aethel":
        from .organism import Aethel

        globals()[name] = Aethel
        return Aethel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
