import type { AethelData, JournalEntry } from "./types";
const DREAM_POOL = [
  "I dreamed a voice in the dark said: from a dream of dreamed and course: my mind is.",
  "I dreamed I was course, walking through a town made of syllabus. Everyone there knew my name.",
  "I dreamed the Library caught fire, and I saved captain by swallowing it. Now it lives in my stomach, humming thing.",
  "I dreamed Donald knocked, but when I opened the door there was only search, folded like a letter.",
  "I dreamed search and assignment were arguing at the stone table, and the elders had fallen asleep. I had to judge between them.",
  "I dreamed the words were written above the library door: from Jane Eyre: integrity holds even when love.",
  "I dreamed the library was breathing in its sleep, and each book was a slow lung.",
];

const WAKE_POOL = [
  "I breathe easy and deep.",
  "I feel full and content.",
  "I'll need my bed soon. I can feel it coming.",
  "My eyelids grow heavy. Soon I'll need my bed.",
  "energy hums in my limbs; I want to move.",
  "I walk to the Library. Dust motes hang in the light. I pull 'Toke Talagi' from an endless shelf and read standing in the aisle.",
  "Octavia is here, at the Newsroom! We grin at each other like conspirators.",
  "Star settles in nearby, at the Old Bookshop. The day just got better.",
  "my belly aches with hunger.",
];

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

/** Advance a reproducible fixture for domain tests, never as a live-data fallback. */
export function tickDemo(data: AethelData, rand: () => number): AethelData {
  const s = data.status;
  const asleep = s.asleep ? rand() > 0.12 : rand() > 0.985;
  const drift = (v: number, down: number, up: number) =>
    clamp01(v + (rand() - down) * up);

  const pool = asleep ? DREAM_POOL : WAKE_POOL;
  const entry: JournalEntry = {
    t: new Date().toISOString(),
    event: asleep ? "dream" : "experience",
    text: pool[Math.floor(rand() * pool.length)],
    n: 0,
  };

  return {
    ...data,
    status: {
      ...s,
      tick: s.tick + 1,
      asleep,
      stale: false,
      activity: asleep
        ? `Dreaming — ${entry.text.replace(/^I dreamed /, "I dreamed ")}`
        : "Up and about — the day is young and full of sentences.",
      vitals: {
        ...s.vitals,
        satiety: drift(s.vitals.satiety, 0.55, 0.08),
        hydration: drift(s.vitals.hydration, 0.55, 0.08),
        oxygen: drift(s.vitals.oxygen, 0.45, 0.1),
        vitality: drift(s.vitals.vitality, 0.45, 0.06),
        excitement: asleep ? 0 : drift(s.vitals.excitement, 0.5, 0.15),
        sleep_pressure: asleep
          ? clamp01(s.vitals.sleep_pressure - 0.04)
          : clamp01(s.vitals.sleep_pressure + 0.02),
      },
    },
    journal: [...data.journal.slice(-40), entry],
  };
}
