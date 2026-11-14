"""Specify the world operations visible to the organism.

Concrete towns provide observations and names without leaking their internal
resident model or statistical diagnostics into the organism."""

from abc import ABC, abstractmethod


class World(ABC):
    @abstractmethod
    def poll(self, n, observer_location):
        """Advance due resident turns and return moves plus names visible at the observer location."""

    @abstractmethod
    def describe(self, place):
        """Return the world-facing display name of a place."""

    @abstractmethod
    def random_place_name(self):
        """Draw a place name from the world’s persisted random stream."""

    def weather(self, n):
        """Return the world's weather at tick n, or None (v0.65).

        Deliberately not abstract: a world with no sky (test stubs,
        older towns) answers None and the organism simply never
        notices weather, exactly as she lived before v0.65."""
        return None
