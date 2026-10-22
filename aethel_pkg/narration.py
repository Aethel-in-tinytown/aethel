"""Translate meals and vital signs into first-person phrases using world names."""

from .config import BODY_FEELINGS


def narrate_meal(meal, describe):
    """Describe a reading outing using place names supplied by the world."""
    t = meal["title"]
    src = meal["source"]
    if src == "wikipedia":
        return (
            f"I walk to {describe(src)}. Dust motes hang in the light. "
            f"I pull '{t}' from an endless shelf and read standing in the aisle."
        )
    if src == "hackernews":
        return (
            f"I push through the door of {describe(src)}. It's loud and crowded, "
            f"everyone shouting the news at once. I catch one thread: '{t}'."
        )
    if src == "classic":
        return (
            f"I visit {describe(src)}. It smells of paper and time. The shopkeeper "
            f"nods — I've been here before. I settle into the armchair with "
            f"'{t}' and read."
        )
    if src == "newsroom":
        return (
            f"I step into {describe(src)}. Wires hum along every wall, every "
            f"paper in the world shouting at once. I catch one headline: '{t}'."
        )
    if src == "university":
        return (
            f"I walk to {describe(src)}. The doors stand open — no one asks "
            f"my name. I take notes on '{t}'."
        )
    if src == "schoolhouse":
        return (
            f"I skip to {describe(src)} with my satchel. Today we're "
            f"learning '{t}'. I sound out the words carefully."
        )
    if src == "nightschool":
        return (
            f"In the evening I visit {describe(src)}, where grown-ups learn "
            f"after work. Tonight: '{t}'."
        )
    return (
        f"No outing today. I open {describe('memory')} and re-taste "
        f"something I saved: '{t}'."
    )


def narrate_council(action, verdict, score):
    return (
        f"I carry '{action[:60]}' before the Council. Nine voices rise "
        f"around the stone table — they do not always agree — confer in "
        f"low voices, and rule: {verdict} ({score:.2f})."
    )


def narrate_body(vitals):
    """Describe the strongest bodily sensation at the current vital levels."""

    if vitals.get("excitement", 0) > 0.6:
        return "a bright fizzing under my ribs, like I want to run somewhere with this"
    low = min(("satiety", "hydration", "oxygen", "vitality"), key=lambda k: vitals[k])
    feeling = BODY_FEELINGS[low][0] if vitals[low] < 0.5 else BODY_FEELINGS[low][1]
    return feeling
