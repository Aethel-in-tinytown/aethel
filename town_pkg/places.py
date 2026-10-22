"""The town's geography. Owned by the town — Aethel only ever hears
place *names* through the World interface, never this map."""
PLACES = {
    "wikipedia": "the Library",      # vast, quiet, endless shelves
    "hackernews": "the Tavern",      # loud, crowded, everyone shouting news
    "classic": "the Old Bookshop",   # smells of paper and time
    "memory": "my own pantry",       # re-tasting what she saved
    "newsroom": "the Newsroom",      # wires from every paper in the world
    "university": "the University",  # MIT OpenCourseWare — doors stand open
    "schoolhouse": "the little Schoolhouse",  # Khan Academy — her childhood
    "nightschool": "the Night School",  # Saylor Academy — doors not yet open
    "postbox": "the wooden postbox at the end of the lane",  # where she leaves things for others
    "home": "my rooms above the Old Bookshop",  # where she lives
    "cottage": "the little cottage at the edge of town",  # Donald and Cassandra's home
}

# Places denizens may wander (physical parts of town, not inner rooms).
DENIZEN_PLACES = ["wikipedia", "hackernews", "classic", "newsroom",
                  "university", "schoolhouse", "postbox"]

