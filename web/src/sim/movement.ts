/** Independent timers and atomic tile reservations prevent overlapping moves.
 *
 * Each update reserves both ends of active edges. Older waiters go first, and
 * blocked actors replan around occupants. A stuck actor yields into a free side
 * tile after two seconds; it keeps its authoritative destination throughout.
 */
import {
  findRoute,
  neighbors,
  pointId,
  tilePoint,
  type Point,
} from "./pathfinding";
import { seededRandom } from "./prng";
export interface Walker extends Point {
  name: string;
  destination: Point;
  route: Point[];
  wait: number;
  delay: number;
  edge?: { start: Point; end: Point; progress: number };
  random: () => number;
}
function seedFor(name: string) {
  let seed = 2166136261;
  for (const c of name) seed = Math.imul(seed ^ c.charCodeAt(0), 16777619);
  return seed >>> 0;
}
export function gammaWait(random: () => number, mean = 0.6): number {
  return (
    (-mean / 2) *
    (Math.log(Math.max(random(), 1e-12)) + Math.log(Math.max(random(), 1e-12)))
  );
}
export function createWalker(name: string, point: Point, seed = 7): Walker {
  const random = seededRandom(seedFor(name) ^ seed);
  return {
    name,
    ...point,
    destination: point,
    route: [],
    wait: 0,
    delay: gammaWait(random),
    random,
  };
}
export function setDestination(walker: Walker, destination: Point) {
  if (pointId(walker.destination) === pointId(destination)) return;
  walker.destination = destination;
  walker.route = [];
  walker.wait = 0;
  walker.delay = gammaWait(walker.random);
}
export function advanceCrowd(walkers: Walker[], dt: number, speed = 46): void {
  const occupied = new Map<number, Walker>();
  for (const walker of walkers) {
    occupied.set(pointId(walker.edge?.start ?? walker), walker);
    if (walker.edge) occupied.set(pointId(walker.edge.end), walker);
  }
  for (const walker of [...walkers].sort(
    (a, b) => b.wait - a.wait || a.name.localeCompare(b.name),
  )) {
    if (walker.edge) {
      const edge = walker.edge;
      edge.progress = Math.min(1, edge.progress + (dt * speed) / 32);
      walker.x = edge.start.x + (edge.end.x - edge.start.x) * edge.progress;
      walker.y = edge.start.y + (edge.end.y - edge.start.y) * edge.progress;
      if (edge.progress === 1) {
        occupied.delete(pointId(edge.start));
        walker.edge = undefined;
      }
      continue;
    }
    walker.delay = Math.max(0, walker.delay - dt);
    if (walker.delay) continue;
    if (pointId(walker) === pointId(walker.destination)) {
      walker.route = [];
      walker.wait = 0;
      continue;
    }
    const blocked = new Set(
      [...occupied].filter(([, owner]) => owner !== walker).map(([id]) => id),
    );
    if (!walker.route.length || walker.wait > 0.5)
      walker.route = findRoute(
        walker.x,
        walker.y,
        walker.destination.x,
        walker.destination.y,
        blocked,
      );
    let next: Point | undefined = walker.route[0];
    if (next && occupied.has(pointId(next))) next = undefined;
    if (!next) {
      walker.wait += dt;
      if (walker.wait > 2) {
        const free = neighbors(pointId(walker)).filter(
          (id) => !occupied.has(id),
        );
        if (free.length) {
          next = tilePoint(free[Math.floor(walker.random() * free.length)]);
          walker.route = [];
        }
      }
    } else walker.route.shift();
    if (next) {
      occupied.set(pointId(next), walker);
      walker.edge = {
        start: { x: walker.x, y: walker.y },
        end: next,
        progress: 0,
      };
      walker.wait = 0;
    }
  }
}
