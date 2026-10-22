/** Grid navigation never crosses an unwalkable tile, including on failure. */
import { MAP_H_TILES, MAP_W_TILES, TILE, WALKABLE } from "./townLayout";
export interface Point {
  x: number;
  y: number;
}
export const tileId = (x: number, y: number) => y * MAP_W_TILES + x;
export const pointId = (p: Point) =>
  tileId(Math.floor(p.x / TILE), Math.floor(p.y / TILE));
export const tilePoint = (id: number): Point => ({
  x: (id % MAP_W_TILES) * TILE + TILE / 2,
  y: Math.floor(id / MAP_W_TILES) * TILE + 20,
});
export function neighbors(id: number): number[] {
  const x = id % MAP_W_TILES,
    y = Math.floor(id / MAP_W_TILES);
  return [
    [x + 1, y],
    [x - 1, y],
    [x, y + 1],
    [x, y - 1],
  ]
    .filter(
      ([nx, ny]) =>
        nx >= 0 &&
        nx < MAP_W_TILES &&
        ny >= 0 &&
        ny < MAP_H_TILES &&
        WALKABLE[ny]?.[nx],
    )
    .map(([nx, ny]) => tileId(nx, ny));
}
export function nearestWalkable(tx: number, ty: number): [number, number] {
  let best: [number, number] = [-1, -1],
    distance = Infinity;
  for (let y = 0; y < MAP_H_TILES; y++)
    for (let x = 0; x < MAP_W_TILES; x++) {
      const d = Math.abs(x - tx) + Math.abs(y - ty);
      if (WALKABLE[y][x] && d < distance) {
        best = [x, y];
        distance = d;
      }
    }
  return best;
}
export function findRoute(
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  blocked = new Set<number>(),
): Point[] {
  const [sx, sy] = nearestWalkable(
    Math.floor(x0 / TILE),
    Math.floor(y0 / TILE),
  );
  const [ex, ey] = nearestWalkable(
    Math.floor(x1 / TILE),
    Math.floor(y1 / TILE),
  );
  const start = tileId(sx, sy),
    end = tileId(ex, ey);
  const queue = [start],
    previous = new Map<number, number>([[start, -1]]);
  for (let head = 0; head < queue.length; head++) {
    const current = queue[head];
    if (current === end) break;
    for (const next of neighbors(current))
      if (!previous.has(next) && (!blocked.has(next) || next === start)) {
        previous.set(next, current);
        queue.push(next);
      }
  }
  if (!previous.has(end)) return [];
  const route: Point[] = [];
  for (let id = end; id !== start; id = previous.get(id)!)
    route.push(tilePoint(id));
  return route.reverse();
}
export const SLOT_OFFSETS = [0, 34, -34, 68, -68, 17, -17, 51];
/** Leave one continuous lane free; stand only on reachable sidewalk tiles. */
export function slotFor(
  name: string,
  _placeKey: string,
  occupants: string[],
  place: Point,
  reserved = new Set<number>(),
) {
  const sorted = [...occupants].sort((a, b) =>
    a === "Aethel" ? -1 : b === "Aethel" ? 1 : a.localeCompare(b),
  );
  const index = Math.max(0, sorted.indexOf(name));
  const candidates: { id: number; cost: number }[] = [];
  for (let y = 0; y < MAP_H_TILES; y++)
    for (let x = 0; x < MAP_W_TILES; x++) {
      if (!WALKABLE[y][x] || y === 11 || y === 21 || x === 11 || x === 28)
        continue;
      const id = tileId(x, y),
        p = tilePoint(id);
      candidates.push({
        id,
        cost: Math.abs(p.x - place.x) + Math.abs(p.y - place.y) * 1.6,
      });
    }
  candidates.sort((a, b) => a.cost - b.cost || a.id - b.id);
  const available = candidates.filter((c) => !reserved.has(c.id));
  const chosen = available[index % available.length];
  return { ...tilePoint(chosen.id), labelLift: index % 2 ? 13 : 0 };
}
