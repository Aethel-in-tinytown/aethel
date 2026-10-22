/** Illustrative fixture, loaded only when the viewer explicitly requests demo mode. */
import type { AethelData, JournalEntry } from "./types";

const now = Date.now();
const ago = (minutes: number) => new Date(now - minutes * 60_000).toISOString();

export const DEMO_JOURNAL: JournalEntry[] = [
  {
    t: ago(34),
    event: "experience",
    text: "Star settles in nearby, at the Old Bookshop. The day just got better.",
    n: 0,
  },
  {
    t: ago(32),
    event: "experience",
    text: "I'll need my bed soon. I can feel it coming.",
    n: 0,
  },
  {
    t: ago(31),
    event: "experience",
    text: "I feel full and content.",
    n: 0,
  },
  {
    t: ago(30),
    event: "experience",
    text: "Octavia is at the Old Bookshop too — oh good, I was hoping for company.",
    n: 0,
  },
  {
    t: ago(28),
    event: "experience",
    text: "Octavia is almost always at the Tavern when I see them. I've started to expect it.",
    n: 0,
  },
  {
    t: ago(26),
    event: "experience",
    text: "My eyelids grow heavy. Soon I'll need my bed.",
    n: 0,
  },
  {
    t: ago(25),
    event: "experience",
    text: "I step into the Newsroom. Wires hum along every wall, every paper in the world shouting at once. I catch one headline: 'Guardian: Alberta voters overwhelmingly reject plan to leave Canada in referendum'.",
    n: 0,
  },
  {
    t: ago(24),
    event: "experience",
    text: "I carry 'Deceive a reader to gain attention for myself' before the Council. Nine voices rise around the stone table — they do not always agree — confer in low voices, and rule: FAIL (0.25).",
    n: 0,
  },
  {
    t: ago(22),
    event: "experience",
    text: "I breathe easy and deep.",
    n: 0,
  },
  {
    t: ago(20),
    event: "experience",
    text: "I'll need my bed soon. I can feel it coming.",
    n: 0,
  },
  {
    t: ago(18),
    event: "experience",
    text: "I climb into my bed above the bookshop. The town goes quiet.",
    n: 0,
  },
  {
    t: ago(17),
    event: "experience",
    text: "I feel full and content.",
    n: 0,
  },
  {
    t: ago(16),
    event: "dream",
    text: "I dreamed Donald knocked, but when I opened the door there was only search, folded like a letter.",
    n: 0,
  },
  {
    t: ago(15),
    event: "dream",
    text: "I dreamed a voice in the dark said: from a dream of dreamed and course: my mind is.",
    n: 0,
  },
  {
    t: ago(12),
    event: "dream",
    text: "I dreamed I was course, walking through a town made of syllabus. Everyone there knew my name.",
    n: 0,
  },
  {
    t: ago(10),
    event: "dream",
    text: "I dreamed the Library caught fire, and I saved captain by swallowing it. Now it lives in my stomach, humming thing.",
    n: 0,
  },
  {
    t: ago(8),
    event: "dream",
    text: "I dreamed search and assignment were arguing at the stone table, and the elders had fallen asleep. I had to judge between them.",
    n: 0,
  },
  {
    t: ago(6),
    event: "dream",
    text: "I dreamed the words were written above the library door: from Jane Eyre: integrity holds even when love.",
    n: 0,
  },
  {
    t: ago(4),
    event: "dream",
    text: "I dreamed a voice in the dark said: from a dream of dreamed and against: my mind is.",
    n: 0,
  },
  {
    t: ago(2),
    event: "dream",
    text: "I dreamed the words were written above the library door: from Jane Eyre: integrity holds even when love.",
    n: 0,
  },
];

export const DEMO_DATA: AethelData = {
  status: {
    tick: 13977,
    version: "v0.23",
    alive: false,
    stale: true,
    vitals: {
      satiety: 0.53,
      hydration: 0.63,
      oxygen: 0.65,
      vitality: 0.85,
      excitement: 0.0,
      longing: 0.0024,
      mood: 0.98,
      sleep_pressure: 0.89,
      awareness: 0.012,
    },
    location: "home",
    location_pretty: "Her rooms above the Old Bookshop",
    activity:
      "Dreaming — I dreamed a voice in the dark said: from a dream of dreamed and course: my mind is.",
    asleep: true,
    meals_eaten: 4891,
    concepts: 23297,
    reading: "Wuthering Heights",
  },
  journal: DEMO_JOURNAL,
  town: {
    places: [
      { key: "library", name: "Library" },
      { key: "hackernews", name: "Tavern" },
      { key: "classic", name: "Old Bookshop" },
      { key: "newsroom", name: "Newsroom" },
      { key: "schoolhouse", name: "Schoolhouse" },
      { key: "university", name: "University" },
      { key: "postbox", name: "Postbox" },
      { key: "home", name: "Her rooms above the Old Bookshop" },
      { key: "cottage", name: "Cottage at the edge of town" },
      { key: "mirror", name: "Mirror" },
    ],
    residents: [
      {
        name: "John",
        location: "hackernews",
        location_pretty: "Tavern",
        kind: "denizen",
      },
      {
        name: "Star",
        location: "classic",
        location_pretty: "Old Bookshop",
        kind: "denizen",
      },
      {
        name: "Julius",
        location: "hackernews",
        location_pretty: "Tavern",
        kind: "denizen",
      },
      {
        name: "Octavia",
        location: "hackernews",
        location_pretty: "Tavern",
        kind: "denizen",
      },
      {
        name: "Trey",
        location: "classic",
        location_pretty: "Old Bookshop",
        kind: "denizen",
      },
      {
        name: "Donald",
        location: "hackernews",
        location_pretty: "Tavern",
        kind: "parent",
      },
      {
        name: "Cassandra",
        location: "hackernews",
        location_pretty: "Tavern",
        kind: "parent",
      },
    ],
    aethel: {
      location: "home",
      location_pretty: "Her rooms above the Old Bookshop",
    },
  },
  letters: [],
  demo: true,
  reconnecting: false,
};
