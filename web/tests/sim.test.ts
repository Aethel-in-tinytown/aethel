import { describe, expect, it } from "vitest";
import { computeAssignments } from "../src/sim/actors";
import { asClause, hearts, percent, timeStamp } from "../src/sim/format";
import {
  BUILDINGS,
  dayFromTick,
  MAP_H_TILES,
  MAP_W_TILES,
  normalizePlace,
  PLACES,
  WALKABLE,
} from "../src/sim/townLayout";
import { DEMO_DATA } from "../src/sim/demoSnapshot";
import { tickDemo } from "../src/sim/provider";
import { seededRandom } from "../src/sim/prng";
import type { Status } from "../src/sim/types";

describe("town layout", () => {
  it("walk grid has the right shape", () => {
    expect(WALKABLE).toHaveLength(MAP_H_TILES);
    expect(WALKABLE[0]).toHaveLength(MAP_W_TILES);
  });

  it("no building sits on the main streets", () => {
    for (const b of BUILDINGS)
      for (let x = b.x; x < b.x + b.w; x++)
        for (let y = b.y; y < b.y + b.h; y++)
          expect(WALKABLE[y]?.[x] ?? false).toBe(false);
  });

  it("every building stays inside the map", () => {
    for (const b of BUILDINGS) {
      expect(b.x + b.w).toBeLessThanOrEqual(MAP_W_TILES);
      expect(b.y + b.h).toBeLessThanOrEqual(MAP_H_TILES);
    }
  });

  it("every place has a walkable tile within reach", () => {
    for (const p of Object.values(PLACES)) {
      const tx = Math.floor(p.x / 32);
      const ty = Math.floor(p.y / 32);
      let near = false;
      for (let dy = -3; dy <= 3 && !near; dy++)
        for (let dx = -3; dx <= 3 && !near; dx++)
          if (WALKABLE[ty + dy]?.[tx + dx]) near = true;
      expect(near, `place ${p.key}`).toBe(true);
    }
  });
});

describe("normalizePlace", () => {
  it("maps wikipedia onto the library", () => {
    expect(normalizePlace("wikipedia")).toBe("library");
  });
  it("passes known places through, lower-cased", () => {
    expect(normalizePlace("Tavern")).toBe("tavern");
    expect(normalizePlace("classic")).toBe("classic");
  });
  it("handles nullish input", () => {
    expect(normalizePlace(undefined)).toBe("");
    expect(normalizePlace(null)).toBe("");
  });
});

describe("dayFromTick", () => {
  it("starts at day 1", () => expect(dayFromTick(0)).toBe(1));
  it("rolls over after 2880 ticks", () => {
    expect(dayFromTick(2879)).toBe(1);
    expect(dayFromTick(2880)).toBe(2);
  });
  it("matches the original page (tick 13977 → day 5)", () => {
    expect(dayFromTick(13977)).toBe(5);
  });
});

describe("format", () => {
  it("clamps percentages", () => {
    expect(percent(0.53)).toBe(53);
    expect(percent(2)).toBe(100);
    expect(percent(-1)).toBe(0);
    expect(percent(undefined)).toBe(0);
  });
  it("renders longing as hearts", () => {
    expect(hearts(0)).toBe(0);
    expect(hearts(1)).toBe(5);
    expect(hearts(0.5)).toBe(3);
  });
  it("strips trailing punctuation for clauses", () => {
    expect(asClause("Reading. ")).toBe("Reading");
    expect(asClause("Dreaming — a voice…")).toBe("Dreaming — a voice");
    expect(asClause(undefined)).toBe("about");
  });
  it("formats timestamps as HH:MM", () => {
    expect(timeStamp("2026-10-21T12:36:38+00:00")).toMatch(/^\d{1,2}:\d{2}/);
  });
});

describe("computeAssignments", () => {
  const base = DEMO_DATA.status;
  const residents = DEMO_DATA.town.residents;

  it("sends Aethel home when asleep", () => {
    const a = computeAssignments({ ...base, asleep: true }, residents);
    expect(a[0]).toMatchObject({ name: "Aethel", place: "home" });
  });

  it("maps Aethel's location through place aliases when awake", () => {
    const awake: Status = { ...base, asleep: false, location: "wikipedia" };
    const a = computeAssignments(awake, residents);
    expect(a[0].place).toBe("library");
  });

  it("keeps resident locations authoritative while Aethel sleeps", () => {
    const assignments = computeAssignments(
      { ...base, asleep: true },
      residents,
    );
    for (const resident of residents) {
      const actor = assignments.find((a) => a.name === resident.name)!;
      expect(actor.place).toBe(normalizePlace(resident.location));
      expect(actor.hide).toBe(false);
    }
  });
});

describe("offline simulation", () => {
  it("advances the tick and appends a journal entry", () => {
    const rand = seededRandom(42);
    const next = tickDemo(DEMO_DATA, rand);
    expect(next.status.tick).toBe(DEMO_DATA.status.tick + 1);
    expect(next.journal.length).toBe(DEMO_DATA.journal.length + 1);
    expect(next.journal[next.journal.length - 1].text.length).toBeGreaterThan(
      0,
    );
  });

  it("keeps vitals within 0..1", () => {
    let data = DEMO_DATA;
    const rand = seededRandom(7);
    for (let i = 0; i < 200; i++) data = tickDemo(data, rand);
    const v = data.status.vitals;
    for (const k of [
      "satiety",
      "hydration",
      "oxygen",
      "vitality",
      "excitement",
      "sleep_pressure",
    ] as const) {
      expect(v[k]).toBeGreaterThanOrEqual(0);
      expect(v[k]).toBeLessThanOrEqual(1);
    }
  });

  it("marks dream entries as dreams when asleep", () => {
    const asleepData = {
      ...DEMO_DATA,
      status: { ...DEMO_DATA.status, asleep: true },
    };
    const rand = () => 0.5;
    const next = tickDemo(asleepData, rand);
    expect(next.journal[next.journal.length - 1].event).toBe("dream");
  });
});

describe("demo snapshot", () => {
  it("references only known character sprites", async () => {
    const { CHARACTERS } = await import("../src/sim/townLayout");
    for (const r of DEMO_DATA.town.residents)
      expect(CHARACTERS[r.name], r.name).toBeDefined();
    expect(CHARACTERS.Aethel).toBeDefined();
  });
});
