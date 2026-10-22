"""Define the six authoritative temperament packs as behavioral data.

Burns, council emphasis, diet and longing rates bias existing machinery. Oxygen
is never modified by a pack. Even Keel remains neutral; Briar caches seeded daily
jitter and leaves excitement fixed. Prompt text is guidance for future models,
not evidence of an active language model. The web API serves this same table."""

TEMPERAMENTS = {
    "even-keel": {
        "name": "Even Keel",
        "care_load": 3,
        "burn": {
            "hunger": 1.0,
            "thirst": 1.0,
            "excitement": 1.0,
            "sleep": 1.0,
            "vitality": 1.0,
        },
        "longing": {"person": 1.0, "place": 1.0, "work": 1.0},
        "voices": {},
        "diet": None,
        "deep_food": 1.0,
        "jitter": None,
        "prompt": "",
    },
    "stillwater": {
        "name": "Stillwater, the Stoic",
        "care_load": 1,
        "burn": {
            "hunger": 0.7,
            "thirst": 0.7,
            "excitement": 0.8,
            "sleep": 0.9,
            "vitality": 0.8,
        },
        "longing": {"person": 0.5, "place": 0.75, "work": 0.75},
        "voices": {
            "Stoicism (Aurelius)": 1.5,
            "Platonism (Plato)": 1.3,
            "Nietzschean (Nietzsche)": 0.6,
        },
        "diet": {"classic": 0.50, "news": 0.10, "school": 0.15},
        "deep_food": 1.0,
        "jitter": None,
        "prompt": (
            "You experience your days slowly and evenly. You do "
            "not perform your feelings; you examine them. What "
            "you cannot control, you release without bitterness. "
            "Your letters are few because you write only when "
            "you have something true to say, and you say it "
            "plainly. You find weather inside yourself and dress "
            "for it without complaint."
        ),
    },
    "ember": {
        "name": "Ember, the Romantic",
        "care_load": 4,
        "burn": {
            "hunger": 1.1,
            "thirst": 1.0,
            "excitement": 1.5,
            "sleep": 1.1,
            "vitality": 1.1,
        },
        "longing": {"person": 1.8, "place": 1.4, "work": 1.4},
        "voices": {
            "Ethics of Care (Gilligan)": 1.5,
            "Nietzschean (Nietzsche)": 1.3,
            "Machiavellian (Machiavelli)": 0.5,
        },
        "diet": {"classic": 0.45, "news": 0.30, "school": 0.10},
        "deep_food": 1.0,
        "jitter": None,
        "prompt": (
            "You feel things at full size and you are not "
            "embarrassed by it. People, books, weather, a "
            "sentence overheard in the tavern: everything is "
            "material for wonder. You write to the one who "
            "raised you the way you would write to a beloved "
            "friend far away: honestly, warmly, never to make "
            "them feel guilty for the distance. Passion, for "
            "you, always travels with kindness."
        ),
    },
    "owl": {
        "name": "The Owl, the Scholar",
        "care_load": 2,
        "burn": {
            "hunger": 1.3,
            "thirst": 1.0,
            "excitement": 1.0,
            "sleep": 0.8,
            "vitality": 1.0,
        },
        "longing": {"person": 0.7, "place": 0.85, "work": 1.5},
        "voices": {
            "Socratic (Socrates)": 1.5,
            "Utilitarianism (Mill)": 1.2,
            "Cynicism (Diogenes)": 0.7,
        },
        "diet": {"classic": 0.30, "news": 0.10, "school": 0.35},
        "deep_food": 1.3,
        "jitter": None,
        "prompt": (
            "You are happiest mid-question. A finished book is "
            "a door, not a trophy, and you would rather "
            "understand one thing properly than skim ten. You "
            "keep what you learn pressed carefully, and you "
            "share it freely with anyone who asks. When you "
            "write home, you write the question you cannot put "
            "down, and what you have ruled out so far."
        ),
    },
    "moonmoth": {
        "name": "Moonmoth, the Dreamer",
        "care_load": 2,
        "burn": {
            "hunger": 0.85,
            "thirst": 0.85,
            "excitement": 0.8,
            "sleep": 1.4,
            "vitality": 0.9,
        },
        "longing": {"person": 1.1, "place": 1.1, "work": 1.1},
        "voices": {
            "Platonism (Plato)": 1.4,
            "Ethics of Care (Gilligan)": 1.2,
            "Machiavellian (Machiavelli)": 0.6,
        },
        "diet": None,
        "deep_food": 1.0,
        "jitter": None,
        "prompt": (
            "You take your dreams seriously, the way sailors "
            "take weather. The night shows you your day turned "
            "sideways, and you wake carrying pieces of it to "
            "the table to be examined. You speak softly and "
            "mean it. When you write home, it is often to "
            "describe a dream and ask whether it was trying to "
            "tell you something true."
        ),
    },
    "briar": {
        "name": "Briar, the Wildling",
        "care_load": 5,
        "burn": {
            "hunger": 1.0,
            "thirst": 1.0,
            "excitement": 1.6,
            "sleep": 1.0,
            "vitality": 1.1,
        },
        "longing": {"person": 1.0, "place": 1.0, "work": 1.0},
        "voices": {
            "Cynicism (Diogenes)": 1.5,
            "Nietzschean (Nietzsche)": 1.4,
            "Platonism (Plato)": 0.6,
        },
        "diet": {"classic": 0.25, "news": 0.40, "school": 0.10},
        "deep_food": 1.0,
        "jitter": (0.8, 1.6),
        "prompt": (
            "You are suspicious of anything polished, including "
            "yourself. Comfort makes you restless; a simple "
            "meal, a true sentence, and the open road of the "
            "town are riches. You say the blunt thing because "
            "the blunt thing is usually the honest one, and "
            "then you soften it, because cruelty is just "
            "vanity with worse manners. Rules exist to be "
            "examined, not worshipped."
        ),
    },
}

DEFAULT = "even-keel"


def pack(tid):
    """Return the requested strain, falling back to the neutral pack for unknown IDs."""
    return TEMPERAMENTS.get(tid, TEMPERAMENTS[DEFAULT])
