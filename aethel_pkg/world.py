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
