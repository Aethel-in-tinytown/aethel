import { describe, expect, it } from "vitest";
import {
  findRoute,
  nearestWalkable,
  pointId,
  slotFor,
  tilePoint,
} from "../src/sim/pathfinding";
import { PLACES, TILE, WALKABLE } from "../src/sim/townLayout";
import {
  advanceCrowd,
  createWalker,
  gammaWait,
  setDestination,
} from "../src/sim/movement";
import { seededRandom } from "../src/sim/prng";

describe("walkable navigation", () => {
  it("snaps building interiors and far-out coordinates onto the grid", () => {
    for (const pair of [
      [4, 5],
      [-100, 50],
      [5, 10],
    ]) {
      const [x, y] = nearestWalkable(pair[0], pair[1]);
      expect(WALKABLE[y][x]).toBe(true);
    }
  });
  it("connects every pair of places using adjacent walkable tiles", () => {
    for (const start of Object.values(PLACES))
      for (const end of Object.values(PLACES)) {
        const route = findRoute(start.x, start.y, end.x, end.y);
        if (pointId(start) !== pointId(end))
          expect(route.length).toBeGreaterThan(0);
        for (let i = 0; i < route.length; i++) {
          const p = route[i];
          expect(WALKABLE[Math.floor(p.y / TILE)][Math.floor(p.x / TILE)]).toBe(
            true,
          );
          if (i)
            expect(
              Math.abs(route[i - 1].x - p.x) + Math.abs(route[i - 1].y - p.y),
            ).toBe(TILE);
        }
      }
  });
  it("fails explicitly when a destination is blocked", () => {
    const a = PLACES.library,
      b = PLACES.hackernews;
    expect(findRoute(a.x, a.y, b.x, b.y, new Set([pointId(b)]))).toEqual([]);
  });
  it("allocates distinct walkable parking slots without filling the transit lane", () => {
    const reserved = new Set<number>();
    for (let i = 0; i < 8; i++) {
      const slot = slotFor(
        `actor${i}`,
        "classic",
        [`actor${i}`],
        PLACES.classic,
        reserved,
      );
      expect(reserved.has(pointId(slot))).toBe(false);
      reserved.add(pointId(slot));
      expect(Math.floor(slot.y / TILE)).not.toBe(11);
    }
  });
});
describe("independent movement", () => {
  it("gamma delays are reproducible with the intended mean", () => {
    const rng = seededRandom(42),
      values = Array.from({ length: 10000 }, () => gammaWait(rng));
    expect(values.reduce((a, b) => a + b, 0) / values.length).toBeCloseTo(
      0.6,
      1,
    );
    expect(new Set(values).size).toBe(10000);
  });
  it("allows opposing traffic and crowded arrivals without overlapping reservations", () => {
    const walkers = Array.from({ length: 8 }, (_, i) =>
      createWalker(`actor${i}`, tilePoint(10 * 40 + 2 + i)),
    );
    for (let i = 0; i < walkers.length; i++)
      setDestination(walkers[i], tilePoint(10 * 40 + 20 + (7 - i)));
    for (let frame = 0; frame < 12000; frame++) {
      advanceCrowd(walkers, 0.05);
      const reserved = new Set<number>();
      for (const walker of walkers)
        for (const id of new Set([
          pointId(walker.edge?.start ?? walker),
          ...(walker.edge ? [pointId(walker.edge.end)] : []),
        ])) {
          expect(reserved.has(id)).toBe(false);
          reserved.add(id);
        }
    }
    for (const w of walkers) expect(pointId(w)).toBe(pointId(w.destination));
  });
  it("does not restart unchanged destinations", () => {
    const w = createWalker("Aethel", tilePoint(402));
    setDestination(w, tilePoint(420));
    advanceCrowd([w], 1);
    const edge = w.edge;
    setDestination(w, tilePoint(420));
    expect(w.edge).toBe(edge);
  });
});
