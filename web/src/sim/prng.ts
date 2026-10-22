/** Small seeded cosmetic generator; never shares state with the Python organism. */
export function seededRandom(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

/** Hash decimal world seeds without losing precision through JavaScript numbers. */
export function cosmeticSeed(value: string): number {
  let hash = 2166136261;
  for (const character of value)
    hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);
  return hash >>> 0;
}
