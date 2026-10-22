"""The world interface: everything Aethel may ask of a world.

She navigates *through* a world; she never sees its implementation.
The town implements this contract. Dependency inversion: she depends on
the abstraction, never on the town — her source code contains no town.
"""
from abc import ABC, abstractmethod


class World(ABC):
    @abstractmethod
    def poll(self, n, observer_location):
        """Advance the world if its own rhythm says so.

        Returns {"moves": [{"name", "location"}], "present": [names]} —
        who went where, and who is now at the observer's location.
        What she *feels* about that is her business, not the world's."""

    @abstractmethod
    def describe(self, place):
        """The place's name as she would speak it ('the Library')."""

    @abstractmethod
    def random_place_name(self):
        """A place name for dreams and verses."""
