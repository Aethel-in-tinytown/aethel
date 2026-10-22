import { expect, it } from "vitest";
import { parseSnapshot } from "../src/sim/protocol";
import { DEMO_DATA } from "../src/sim/demoSnapshot";
import { noise, terrainShade } from "../src/sim/scenery";
import { DIRECTIONS, FRAMES_PER_DIR, frameIndex } from "../src/game/pixel";
it("rejects malformed payloads before they reach the render loop", () => {
  const snapshot = {
    ...DEMO_DATA,
    revision: 1,
    world_seed: "7",
    journal: [],
    letters: [],
  };
  expect(parseSnapshot(snapshot).demo).toBe(false);
  for (const invalid of [
    null,
    {},
    { ...snapshot, revision: NaN },
    {
      ...snapshot,
      status: {
        ...snapshot.status,
        vitals: { ...snapshot.status.vitals, oxygen: Infinity },
      },
    },
    { ...snapshot, town: { residents: [null] } },
  ])
    expect(() => parseSnapshot(invalid)).toThrow();
});
it("generates coherent, reproducible terrain with independent seeds", () => {
  expect(noise(5, 7, 42)).toBe(noise(5, 7, 42));
  expect(noise(5, 7, 42)).not.toBe(noise(5, 7, 43));
  expect(Math.abs(terrainShade(4, 5) - terrainShade(4.01, 5))).toBeLessThan(
    0.01,
  );
  for (let i = 0; i < 100; i++)
    expect(terrainShade(i, i + 3)).toBeGreaterThanOrEqual(0);
});
it("maps idle and both strides to valid direction frames", () => {
  const indices = new Set(
    DIRECTIONS.flatMap((d) => [0, 1, 2].map((f) => frameIndex(d, f))),
  );
  expect(indices.size).toBe(DIRECTIONS.length * FRAMES_PER_DIR);
  expect(Math.max(...indices)).toBe(DIRECTIONS.length * FRAMES_PER_DIR - 1);
});
