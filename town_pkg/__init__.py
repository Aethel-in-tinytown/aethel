"""The town program: places, residents, and their movement.

Aethel navigates through this world; she is not part of it. She sees it
only through the World interface (aethel_pkg.world). This package never
imports her.

Note: Town is not imported here — town.py imports the World contract
from aethel_pkg, so re-exporting it from this __init__ would risk a
circular import depending on order. Import town_pkg.town explicitly.
"""
