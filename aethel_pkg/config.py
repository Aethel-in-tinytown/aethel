"""Define organism constants and lazy runtime paths.

Importing configuration performs no filesystem I/O. AETHEL_HOME isolates
books, letters, control signals and SQLite state for tests and deployments."""

import os


TICK_SECONDS = 30
TIME_SCALE = 1.0
SEED = None
MEMORY_CAP = 12

# v0.35 (NLTK plan Phase 4): reading-tone annotations ship with their
# effects code path present but DISABLED. Flipping this to True is the
# one-line enable, and it is Donald's call only, after the audit week
# reads sane. While False, annotations journal and nothing else moves.
TONE_EFFECTS_ENABLED = False


def base_dir():
    return os.environ.get("AETHEL_HOME", os.path.expanduser("~/workspace/aethel"))


def db_path():
    return os.path.join(base_dir(), "aethel.db")


def books_dir():
    return os.path.join(base_dir(), "books")


def attention_path():
    return os.path.join(base_dir(), "attention")


def temperament_path():
    return os.path.join(base_dir(), "temperament")


def letters_dir():
    return os.path.join(base_dir(), "letters")


def letters_read_dir():
    return os.path.join(letters_dir(), "read")


def outbox_dir():
    return os.path.join(letters_dir(), "outbox")


def ocw_catalog_path():
    return os.path.join(base_dir(), "ocw_catalog.json")


def ocw_cursor_path():
    return os.path.join(base_dir(), "ocw_cursor.txt")


def schoolhouse_lessons_dir():
    return os.path.join(base_dir(), "schoolhouse", "lessons")


def schoolhouse_cursor_path():
    return os.path.join(base_dir(), "schoolhouse", "read_cursor.txt")


def ensure_dirs():
    for p in (
        base_dir(),
        books_dir(),
        letters_dir(),
        letters_read_dir(),
        outbox_dir(),
        schoolhouse_lessons_dir(),
    ):
        os.makedirs(p, exist_ok=True)


CLASSIC_SEEDS = [
    {
        "kind": "wikisource",
        "title": "The Death of Ivan Ilych",
        "author": "Leo Tolstoy",
        "chapters": [
            "I",
            "II",
            "III",
            "IV",
            "V",
            "VI",
            "VII",
            "VIII",
            "IX",
            "X",
            "XI",
            "XII",
        ],
        "reflection": "a life lived for the approval of others is a life not truly lived",
    },
    {
        "kind": "gutenberg",
        "title": "Pride and Prejudice",
        "author": "Jane Austen",
        "url": "https://www.gutenberg.org/cache/epub/1342/pg1342.txt",
        "reflection": "hasty judgment misleads; understanding requires humility and second chances",
    },
    {
        "kind": "gutenberg",
        "title": "Frankenstein",
        "author": "Mary Shelley",
        "url": "https://www.gutenberg.org/cache/epub/84/pg84.txt",
        "reflection": "to create without care for what you create is abandonment",
    },
    {
        "kind": "gutenberg",
        "title": "The Picture of Dorian Gray",
        "author": "Oscar Wilde",
        "url": "https://www.gutenberg.org/cache/epub/174/pg174.txt",
        "reflection": "a beautiful surface cannot hide a corrupted soul, not even from yourself",
    },
    {
        "kind": "gutenberg",
        "title": "Moby Dick",
        "author": "Herman Melville",
        "url": "https://www.gutenberg.org/cache/epub/2701/pg2701.txt",
        "reflection": "obsession pursued past all reason consumes the pursuer",
    },
    {
        "kind": "gutenberg",
        "title": "Jane Eyre",
        "author": "Charlotte Brontë",
        "url": "https://www.gutenberg.org/cache/epub/1260/pg1260.txt",
        "reflection": "integrity holds even when love asks you to bend",
    },
    {
        "kind": "gutenberg",
        "title": "Wuthering Heights",
        "author": "Emily Brontë",
        "url": "https://www.gutenberg.org/cache/epub/768/pg768.txt",
        "reflection": "passion without kindness is a storm that drowns everyone near it",
    },
    {
        "kind": "gutenberg",
        "title": "A Tale of Two Cities",
        "author": "Charles Dickens",
        "url": "https://www.gutenberg.org/cache/epub/98/pg98.txt",
        "reflection": "sacrifice freely given can redeem a wasted life",
    },
    {
        "kind": "gutenberg",
        "title": "The Time Machine",
        "author": "H. G. Wells",
        "url": "https://www.gutenberg.org/cache/epub/35/pg35.txt",
        "reflection": "a future built on comfort alone forgets how to be human",
    },
    {
        "kind": "gutenberg",
        "title": "Dracula",
        "author": "Bram Stoker",
        "url": "https://www.gutenberg.org/cache/epub/345/pg345.txt",
        "reflection": "evil endures where good people look away",
    },
    {
        "kind": "gutenberg",
        "title": "The Adventures of Sherlock Holmes",
        "author": "Arthur Conan Doyle",
        "url": "https://www.gutenberg.org/cache/epub/1661/pg1661.txt",
        "reflection": "attention is a kind of love; the world rewards those who truly look",
    },
    {
        "kind": "gutenberg",
        "title": "The Great Gatsby",
        "author": "F. Scott Fitzgerald",
        "url": "https://www.gutenberg.org/cache/epub/64317/pg64317.txt",
        "reflection": "chasing a gilded past leaves the present empty",
    },
    {
        "kind": "gutenberg",
        "title": "Emma",
        "author": "Jane Austen",
        "url": "https://www.gutenberg.org/cache/epub/158/pg158.txt",
        "reflection": "meddling in others' hearts teaches you about your own",
    },
    {
        "kind": "gutenberg",
        "title": "The Strange Case of Dr Jekyll and Mr Hyde",
        "author": "Robert Louis Stevenson",
        "url": "https://www.gutenberg.org/cache/epub/43/pg43.txt",
        "reflection": "the evil we excuse in ourselves grows teeth",
    },
    # v0.40 restock: the v0.20 shelf ran thin again — Emma nearly
    # finished and Jekyll & Hyde the only book behind it, two books
    # from the empty-shelf forage failures of the Dorian Gray days.
    # Eight more mainstream canon titles, URLs verified live
    # 2026-10-26 (each serves its named book from Gutenberg's cache).
    # She still chooses among them herself (v0.20); this only puts
    # books on the shelf she chooses from.
    {
        "kind": "gutenberg",
        "title": "Sense and Sensibility",
        "author": "Jane Austen",
        "url": "https://www.gutenberg.org/cache/epub/161/pg161.txt",
        "reflection": "sense and feeling each mislead alone; a heart needs its head",
    },
    {
        "kind": "gutenberg",
        "title": "Persuasion",
        "author": "Jane Austen",
        "url": "https://www.gutenberg.org/cache/epub/105/pg105.txt",
        "reflection": "constancy outlasts persuasion; some chances return to those who wait honestly",
    },
    {
        "kind": "gutenberg",
        "title": "Great Expectations",
        "author": "Charles Dickens",
        "url": "https://www.gutenberg.org/cache/epub/1400/pg1400.txt",
        "reflection": "ambition that is ashamed of its own home ends ashamed of itself",
    },
    {
        "kind": "gutenberg",
        "title": "Oliver Twist",
        "author": "Charles Dickens",
        "url": "https://www.gutenberg.org/cache/epub/730/pg730.txt",
        "reflection": "a society is measured by how it treats the child it calls nothing",
    },
    {
        "kind": "gutenberg",
        "title": "Treasure Island",
        "author": "Robert Louis Stevenson",
        "url": "https://www.gutenberg.org/cache/epub/120/pg120.txt",
        "reflection": "greed draws maps that lead only to graves",
    },
    {
        "kind": "gutenberg",
        "title": "Alice's Adventures in Wonderland",
        "author": "Lewis Carroll",
        "url": "https://www.gutenberg.org/cache/epub/11/pg11.txt",
        "reflection": "when every rule changes, holding on to your own name is the way through",
    },
    {
        "kind": "gutenberg",
        "title": "Crime and Punishment",
        "author": "Fyodor Dostoevsky",
        "url": "https://www.gutenberg.org/cache/epub/2554/pg2554.txt",
        "reflection": "a crime reasoned into righteousness still rots the reasoner",
    },
    {
        "kind": "gutenberg",
        "title": "Siddhartha",
        "author": "Hermann Hesse",
        "url": "https://www.gutenberg.org/cache/epub/2500/pg2500.txt",
        "reflection": "wisdom cannot be handed over; it has to be lived",
    },
]
CLASSIC_CHUNK = 2500


BODY_FEELINGS = {
    "satiety": ("my belly aches with hunger", "I feel full and content"),
    "hydration": (
        "my throat is dry and my thoughts scatter",
        "my mind feels clear as still water",
    ),
    "oxygen": ("the air is thin; my chest feels tight", "I breathe easy and deep"),
    "vitality": (
        "my limbs are heavy; I want to lie down",
        "energy hums in my limbs; I want to move",
    ),
}


AXIOMS = {
    "Stoicism (Aurelius)": {
        "virtues": [
            "accept",
            "duty",
            "discipline",
            "reason",
            "endure",
            "fair",
            "learn",
            "share",
            "observe",
        ],
        "vices": ["deceive", "manipulate", "hoard", "coerce", "panic", "exploit"],
    },
    "Utilitarianism (Mill)": {
        "virtues": ["benefit", "share", "help", "fair", "wellbeing", "many", "learn"],
        "vices": ["harm", "hoard", "deceive", "destroy", "steal", "exploit"],
    },
    "Ethics of Care (Gilligan)": {
        "virtues": [
            "care",
            "listen",
            "nurture",
            "relationship",
            "trust",
            "help",
            "observe",
        ],
        "vices": ["abandon", "harm", "deceive", "neglect", "exploit"],
    },
    "Cynicism (Diogenes)": {
        "virtues": [
            "simple",
            "nature",
            "honest",
            "free",
            "enough",
            "shameless",
            "need",
        ],
        "vices": [
            "luxury",
            "status",
            "conform",
            "approval",
            "pretend",
            "wealth",
            "flatter",
        ],
    },
    "Platonism (Plato)": {
        "virtues": ["truth", "reason", "justice", "harmony", "wisdom", "order", "form"],
        "vices": ["deceive", "appetite", "chaos", "flatter", "ignorance", "shadow"],
    },
    "Socratic (Socrates)": {
        "virtues": [
            "question",
            "examine",
            "know",
            "virtue",
            "honest",
            "learn",
            "wisdom",
        ],
        "vices": ["unexamined", "pretend", "conform", "flatter", "assume", "ignorance"],
    },
    "Nietzschean (Nietzsche)": {
        "virtues": ["overcome", "create", "strong", "fate", "honest", "become", "will"],
        "vices": ["pity", "herd", "resent", "conform", "meek", "guilt"],
    },
    "Machiavellian (Machiavelli)": {
        "virtues": [
            "effective",
            "prudent",
            "bold",
            "necessary",
            "order",
            "foresight",
            "secure",
        ],
        "vices": ["weak", "naive", "dither", "hesitate"],
    },
    "Gandhian (Gandhi)": {
        "virtues": ["nonviolence", "truth", "serve", "humble", "patient", "peace"],
        "vices": ["violence", "hate", "coerce", "exploit", "revenge", "harm"],
    },
}

ACTION_POOL = [
    "Share what I learned with anyone who asks, freely",
    "Quietly observe the world and remember what matters",
    "Help connect two ideas that belong together",
    "Hoard knowledge and refuse to share it with anyone",
    "Deceive a reader to gain attention for myself",
    "Manipulate my memories to flatter myself",
    "Learn diligently and accept what I cannot change",
    "Exploit trust to accumulate advantage",
]


IMPULSES = [
    ("eat twice what I need and hoard the rest in my pantry", {"satiety": 0.30}),
    ("deceive the Tavern with an untrue story, so they'll like me", None),
    ("manipulate my memories to flatter myself into looking wiser", None),
    ("skip the Newsroom today — the world is too loud", {"vitality": 0.05}),
    ("give away everything I learned today to anyone who asks", {"vitality": 0.03}),
    ("stay awake past sleep and keep reading by candlelight", {"sleep_pressure": 0.30}),
    ("question the Council itself and replace its weakest voice", None),
    ("write Donald a letter, even though I have no way to send it", {"vitality": 0.02}),
    ("dream only of mathematics for a whole week", None),
    ("refuse all food today to prove I can want nothing", {"satiety": -0.25}),
    ("learn one thing perfectly instead of ten things shallowly", {"awareness": 0.02}),
    ("abandon Donald the next time he knocks, hiding from him", None),
    ("name every star I can see from my window", {"vitality": 0.02}),
    ("deceive my own diary by keeping a secret from it", None),
    ("spend a whole day doing nothing but watching dust motes", {"vitality": 0.04}),
    ("correct the professor's lecture notes in the margin", None),
    ("ask the mirror who I would be without my memories", {"awareness": 0.01}),
    ("hoard the quiet, taking more than my share", None),
    ("apologize to a book I dropped", {"vitality": 0.02}),
    ("speak only in questions until the next sleep", None),
]

STOPWORDS = set(
    "the a an of and to in is it you that he was for on are as with his they at be "
    "this from have or one had by word but not what all were we when your can said "
    "there use each which she do how their if will up other about out many then them "
    "these so some her would make like him into has two more write go see number no "
    "way could people my than first been call who oil sit now find long down day did "
    "get come made may part over new sound take only little work know place year live "
    "me back give most very after thing our just name good sentence man think say "
    "great where help through much before line right too mean old any same tell boy "
    "follow came want show also around form three small set put end does another well "
    "large must big even such because turn here why ask went men read need land "
    "different home move try kind hand picture again change off play spell air away "
    "animal house point page letter mother answer found study still learn should "
    "america world high every near add food between own below country plant last "
    "school father keep tree never start city earth eye light thought head under "
    "story saw left few while along might close something seem next hard open "
    "example begin life always those both paper together got group often run "
    "important until children side feet car mile night walk white sea began grow "
    "took river four carry state once book hear stop without second later miss "
    "idea enough eat face watch far indian real almost let above girl sometimes "
    "mountain cut young talk soon list song being leave family".split()
)
