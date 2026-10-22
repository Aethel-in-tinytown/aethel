/** Spatial noise keeps terrain coherent and stable when decorative props change. */
export function noise(x: number, y: number, seed = 7): number {
  let n = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ seed;
  n = Math.imul(n ^ (n >>> 13), 1274126177);
  return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
}
export function terrainShade(x: number, y: number, seed = 7): number {
  const cellX = Math.floor(x / 5),
    cellY = Math.floor(y / 5);
  const smooth = (value: number) => value * value * (3 - 2 * value);
  const fx = smooth(x / 5 - cellX),
    fy = smooth(y / 5 - cellY);
  const a = noise(cellX, cellY, seed),
    b = noise(cellX + 1, cellY, seed);
  const c = noise(cellX, cellY + 1, seed),
    d = noise(cellX + 1, cellY + 1, seed);
  return (a + (b - a) * fx) * (1 - fy) + (c + (d - c) * fx) * fy;
}
