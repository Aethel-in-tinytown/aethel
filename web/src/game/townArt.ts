/** Paint seeded terrain, architecture and small details into a single cached texture. */
import {
  BENCHES,
  BUILDINGS,
  LAMPS,
  MAP_H,
  MAP_H_TILES,
  MAP_W,
  MAP_W_TILES,
  TILE,
  TREES,
  WALKABLE,
  type BuildingDef,
} from "../sim/townLayout";
import { terrainShade, noise } from "../sim/scenery";
import { seededRandom } from "../sim/prng";

export const PIXEL_FONT = `'Pixelify Sans', monospace`;

export interface WindowGlow {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface TownArt {
  canvas: HTMLCanvasElement;

  windows: WindowGlow[];

  chimneys: Array<{ x: number; y: number }>;

  lamps: Array<{ x: number; y: number }>;
}

function drawSign(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
) {
  ctx.font = `bold 11px ${PIXEL_FONT}`;
  const w = Math.ceil(ctx.measureText(text).width) + 12;
  ctx.fillStyle = "#5a3e25";
  ctx.fillRect(x + 4, y + 14, 3, 10);
  ctx.fillRect(x + w - 7, y + 14, 3, 10);
  ctx.fillStyle = "#4a321d";
  ctx.fillRect(x - 1, y + 1, w + 2, 16);
  ctx.fillStyle = "#c79a5f";
  ctx.fillRect(x, y, w, 15);
  ctx.fillStyle = "#b0844c";
  ctx.fillRect(x, y + 12, w, 3);
  ctx.fillStyle = "#3b2614";
  ctx.textBaseline = "middle";
  ctx.fillText(text, x + 6, y + 7.5);
}

function drawTree(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  rand: () => number,
) {
  ctx.fillStyle = "rgba(40,25,10,0.25)";
  ctx.beginPath();
  ctx.ellipse(x + 16, y + 30, 20, 7, 0, 0, Math.PI * 2);
  ctx.fill();

  const palette =
    ((x / TILE) * 3 + (y / TILE) * 7) % 5 < 1.2
      ? ["#5c2a3c", "#a8475f", "#c95f78", "#e58aa0"]
      : ["#1f3a2a", "#2f6a43", "#3f8452", "#68a865"];

  ctx.fillStyle = "#2a1c14";
  ctx.fillRect(x + 10, y + 10, 12, 22);
  ctx.fillStyle = "#6e4a2e";
  ctx.fillRect(x + 12, y + 10, 8, 20);
  ctx.fillStyle = "#8a6040";
  ctx.fillRect(x + 13, y + 12, 2, 16);

  const blob = (bx: number, by: number, r: number, color: string) => {
    ctx.fillStyle = color;
    ctx.fillRect(bx - r, by - r / 2, r * 2, r);
    ctx.fillRect(bx - r / 2, by - r, r, r * 2);
    ctx.fillRect(bx - r * 0.8, by - r * 0.8, r * 1.6, r * 1.6);
  };
  blob(x + 16, y, 23, palette[0]);
  blob(x + 16, y, 21, palette[1]);
  blob(x + 13, y - 4, 15, palette[2]);
  for (let i = 0; i < 9; i++) {
    ctx.fillStyle = i % 3 ? palette[3] : palette[0];
    ctx.fillRect(
      x - 2 + Math.floor(rand() * 16) * 2,
      y - 16 + Math.floor(rand() * 14) * 2,
      4,
      3,
    );
  }
}

/** Derive windows and chimney anchors while drawing the building only once. */
function drawBuilding(
  ctx: CanvasRenderingContext2D,
  b: BuildingDef,
  rand: () => number,
  windows: WindowGlow[],
  chimneys: Array<{ x: number; y: number }>,
) {
  const x = b.x * TILE;
  const y = b.y * TILE;
  const w = b.w * TILE;
  const h = b.h * TILE;
  const roofH = Math.round(h * (b.storeys ? 0.36 : 0.45));

  ctx.fillStyle = "rgba(40,25,10,0.25)";
  ctx.fillRect(x + 8, y + h - 4, w, 10);
  ctx.fillStyle = "#231a20";
  ctx.fillRect(x - 2, y + roofH - 2, w + 4, h - roofH + 4);
  ctx.fillStyle = b.wall;
  ctx.fillRect(x, y + roofH, w, h - roofH);

  if (b.timber) {
    ctx.fillStyle = "#5a3a26";
    for (let tx = x; tx <= x + w - 4; tx += 32)
      ctx.fillRect(tx, y + roofH, 4, h - roofH);
    ctx.fillRect(x + w - 4, y + roofH, 4, h - roofH);
    ctx.fillRect(x, y + roofH, w, 4);
    if (b.storeys) ctx.fillRect(x, y + roofH + 40, w, 4);
  } else {
    ctx.fillStyle = "rgba(255,250,235,0.35)";
    for (let tx = x + 6; tx < x + w - 6; tx += 40)
      ctx.fillRect(tx, y + roofH + 2, 6, h - roofH - 10);
  }

  ctx.fillStyle = "#7d7486";
  ctx.fillRect(x, y + h - 8, w, 8);
  ctx.fillStyle = "#5f5868";
  for (let tx = x; tx < x + w; tx += 10) ctx.fillRect(tx, y + h - 8, 1, 8);

  if (b.chimney !== undefined) {
    const chx = x + b.chimney * TILE + 6;
    const chy = y - 10;
    ctx.fillStyle = "#231a20";
    ctx.fillRect(chx - 4, chy - 2, 22, roofH + 2);
    ctx.fillStyle = "#9a929c";
    ctx.fillRect(chx - 2, chy, 18, roofH);
    ctx.fillStyle = "#7a7280";
    for (let cy = chy + 4; cy < chy + roofH; cy += 6)
      ctx.fillRect(chx - 2, cy, 18, 1);
    ctx.fillStyle = "#3a3038";
    ctx.fillRect(chx + 2, chy, 10, 3);
    chimneys.push({ x: chx + 7, y: chy });
  }

  ctx.fillStyle = "#231a20";
  for (let i = -2; i < roofH + 2; i += 2) {
    const inset = Math.max(0, 14 - i);
    ctx.fillRect(x - 10 + inset, y + i, w + 20 - inset * 2, 2);
  }
  for (let i = 0; i < roofH; i += 6) {
    const inset = Math.max(0, 12 - i);
    const rx = x - 8 + inset;
    const rw = w + 16 - inset * 2;
    ctx.fillStyle = b.roof;
    ctx.fillRect(rx, y + i, rw, 6);
    ctx.fillStyle = b.roofDark;
    ctx.fillRect(rx, y + i + 5, rw, 1);
    for (let tx = rx + ((i / 6) % 2 ? 4 : 0); tx < rx + rw; tx += 8)
      ctx.fillRect(tx, y + i, 1, 6);
  }
  ctx.fillStyle = b.roofDark;
  ctx.fillRect(x - 8, y + roofH - 4, w + 16, 4);
  ctx.fillStyle = "rgba(255,240,210,0.18)";
  ctx.fillRect(x + 6, y + 2, w - 12, 2);

  const drawWindowRow = (wy: number) => {
    const count = Math.max(2, Math.floor(b.w / 2));
    for (let i = 0; i < count; i++) {
      const wx = x + ((i + 0.5) * w) / count - 8;
      if (Math.abs(wx + 8 - (x + w / 2)) < 18 && wy > y + h - 60) continue;
      ctx.fillStyle = "#5a3e25";
      ctx.fillRect(wx - 2, wy - 2, 20, 22);
      ctx.fillStyle = "#f0b85a";
      ctx.fillRect(wx, wy, 16, 18);
      ctx.fillStyle = "#ffe4a0";
      ctx.fillRect(wx + 2, wy + 2, 5, 6);
      ctx.fillStyle = "#5a3e25";
      ctx.fillRect(wx + 7, wy, 2, 18);
      ctx.fillRect(wx, wy + 8, 16, 2);
      ctx.fillStyle = "#c46b4a";
      ctx.fillRect(wx - 2, wy + 20, 20, 4);
      ctx.fillStyle = "#e0849a";
      ctx.fillRect(wx, wy + 18, 4, 3);
      ctx.fillRect(wx + 10, wy + 18, 4, 3);
      windows.push({ x: wx, y: wy, w: 16, h: 18 });
    }
  };
  if (b.storeys) drawWindowRow(y + roofH + 10);
  drawWindowRow(y + h - 46);

  const dx = x + w / 2 - 12;
  const dy = y + h - 40;
  ctx.fillStyle = "#4a321d";
  ctx.fillRect(dx - 2, dy - 2, 28, 42);
  ctx.fillStyle = "#7a5030";
  ctx.fillRect(dx, dy, 24, 40);
  ctx.fillStyle = "#6a4428";
  ctx.fillRect(dx + 11, dy, 2, 40);
  ctx.fillStyle = "#e0b35a";
  ctx.fillRect(dx + 17, dy + 20, 3, 3);

  if (b.ivy)
    for (let i = 0; i < 46; i++) {
      const ix =
        rand() > 0.5
          ? x + Math.floor(rand() * 10) * 2
          : x + w - 20 + Math.floor(rand() * 10) * 2;
      const iy = y + roofH + Math.floor(rand() * ((h - roofH) / 2)) * 2;
      ctx.fillStyle = rand() > 0.4 ? "#4f7f3a" : "#3a6630";
      ctx.fillRect(ix, iy, 4, 4);
    }

  drawSign(ctx, b.label, b.x + b.w >= 39 ? x - 8 : x + w / 2 + 16, y + h - 4);
}

/** Independent coordinate noise keeps decoration changes from reshuffling terrain. */
export function paintTown(seed = 7): TownArt {
  const canvas = document.createElement("canvas");
  canvas.width = MAP_W;
  canvas.height = MAP_H;
  const ctx = canvas.getContext("2d")!;
  const rand = seededRandom(seed);
  const windows: WindowGlow[] = [];
  const chimneys: Array<{ x: number; y: number }> = [];

  const overlapsBuilding = (tx: number, ty: number) =>
    BUILDINGS.some(
      (b) => tx >= b.x && tx < b.x + b.w && ty >= b.y && ty < b.y + b.h,
    );

  for (let ty = 0; ty < MAP_H_TILES; ty++)
    for (let tx = 0; tx < MAP_W_TILES; tx++) {
      const shade = terrainShade(tx, ty, seed);
      ctx.fillStyle =
        shade < 0.35 ? "#75964f" : shade < 0.6 ? "#83a55d" : "#91ad65";
      ctx.fillRect(tx * TILE, ty * TILE, TILE, TILE);
      for (let i = 0; i < 4; i++) {
        const gx = tx * TILE + Math.floor(rand() * 14) * 2;
        const gy = ty * TILE + Math.floor(rand() * 14) * 2;
        ctx.fillStyle = "#5e8745";
        ctx.fillRect(gx, gy + 2, 2, 4);
        ctx.fillRect(gx + 4, gy + 2, 2, 4);
        ctx.fillStyle = "#8db86a";
        ctx.fillRect(gx + 2, gy, 2, 6);
      }
    }

  for (let ty = 0; ty < MAP_H_TILES; ty++)
    for (let tx = 0; tx < MAP_W_TILES; tx++) {
      if (!WALKABLE[ty][tx]) continue;
      ctx.fillStyle = "#4b4a63";
      ctx.fillRect(tx * TILE, ty * TILE, TILE, TILE);
      for (let row = 0; row < 4; row++)
        for (let col = -1; col < 4; col++) {
          const cx =
            tx * TILE + col * 10 + (row % 2 ? 5 : 0) + ((tx + row) % 2);
          const cy = ty * TILE + row * 8;
          const r = rand();
          ctx.fillStyle =
            r > 0.66 ? "#7b7896" : r > 0.33 ? "#6c6a88" : "#626080";
          ctx.fillRect(
            Math.max(tx * TILE, cx + 1),
            cy + 1,
            Math.min(8, tx * TILE + TILE - cx - 1),
            6,
          );
          ctx.fillStyle = "#8a87a3";
          ctx.fillRect(Math.max(tx * TILE, cx + 2), cy + 1, 3, 1);
        }
      ctx.fillStyle = "#3a3950";
      if (!WALKABLE[ty - 1]?.[tx]) {
        ctx.fillRect(tx * TILE, ty * TILE, TILE, 3);
        ctx.fillStyle = "#c9a96a";
        ctx.fillRect(tx * TILE, ty * TILE - 3, TILE, 3);
        ctx.fillStyle = "#3a3950";
      }
      if (!WALKABLE[ty + 1]?.[tx]) {
        ctx.fillRect(tx * TILE, ty * TILE + TILE - 3, TILE, 3);
        ctx.fillStyle = "#c9a96a";
        ctx.fillRect(tx * TILE, ty * TILE + TILE, TILE, 3);
        ctx.fillStyle = "#3a3950";
      }
      if (!WALKABLE[ty]?.[tx - 1]) ctx.fillRect(tx * TILE, ty * TILE, 2, TILE);
      if (!WALKABLE[ty]?.[tx + 1])
        ctx.fillRect(tx * TILE + TILE - 2, ty * TILE, 2, TILE);
    }

  const petals = ["#f4e3a1", "#f1a7b8", "#ffffff", "#e9846b", "#f6c75c"];
  for (let i = 0; i < 160; i++) {
    const tx = Math.floor(rand() * MAP_W_TILES);
    const ty = Math.floor(rand() * MAP_H_TILES);
    if (
      WALKABLE[ty][tx] ||
      overlapsBuilding(tx, ty) ||
      terrainShade(tx, ty, seed + 19) < 0.35
    )
      continue;
    const fx = tx * TILE + Math.floor(rand() * 12) * 2 + 4;
    const fy = ty * TILE + Math.floor(rand() * 12) * 2 + 4;
    ctx.fillStyle = "#4f7a35";
    ctx.fillRect(fx + 2, fy + 4, 2, 4);
    ctx.fillStyle = petals[Math.floor(rand() * petals.length)];
    ctx.fillRect(fx, fy, 6, 4);
    ctx.fillRect(fx + 2, fy - 2, 2, 8);
    ctx.fillStyle = "#e0a93b";
    ctx.fillRect(fx + 2, fy, 2, 2);
  }

  ctx.fillStyle = "#4e7a3a";
  ctx.fillRect(992, 416, 256, 12);
  ctx.fillRect(992, 416, 12, 160);
  ctx.fillRect(1236, 416, 12, 160);
  ctx.fillStyle = "#5f8f45";
  ctx.fillRect(992, 416, 256, 6);
  ctx.fillStyle = "#cdb98f";
  ctx.fillRect(1056, 464, 128, 56);
  ctx.fillStyle = "#b9a57b";
  for (let i = 0; i < 30; i++)
    ctx.fillRect(
      1056 + Math.floor(rand() * 60) * 2,
      464 + Math.floor(rand() * 26) * 2,
      2,
      2,
    );
  ctx.fillStyle = "#6b4a2b";
  ctx.fillRect(1108, 442, 24, 40);
  ctx.fillRect(1114, 482, 4, 10);
  ctx.fillRect(1122, 482, 4, 10);
  ctx.fillRect(1110, 490, 20, 3);
  ctx.fillStyle = "#c9d7d3";
  ctx.fillRect(1112, 446, 16, 32);
  ctx.fillStyle = "#eef4f0";
  ctx.fillRect(1114, 448, 4, 14);
  ctx.fillRect(1120, 450, 2, 6);

  for (const [bx, by] of [
    [37.5, 15.5],
    [37.5, 17.5],
  ] as const) {
    ctx.fillStyle = "#3f6b2f";
    ctx.fillRect(bx * TILE, by * TILE, 22, 16);
    ctx.fillStyle = "#e57c93";
    ctx.fillRect(bx * TILE + 4, by * TILE + 2, 4, 4);
    ctx.fillRect(bx * TILE + 14, by * TILE + 6, 4, 4);
    ctx.fillRect(bx * TILE + 8, by * TILE + 10, 4, 4);
  }

  ctx.fillStyle = "#8a6440";
  for (let tx = 35; tx < 40; tx++)
    if (tx !== 37 && tx !== 38) {
      ctx.fillRect(tx * TILE + 4, 290, 4, 20);
      ctx.fillRect(tx * TILE + 20, 290, 4, 20);
      ctx.fillRect(tx * TILE, 296, 32, 4);
    }
  ctx.fillRect(1122, 128, 4, 160);

  for (const b of BUILDINGS) drawBuilding(ctx, b, rand, windows, chimneys);

  // Doorstep details share the scenery seed without consuming the terrain stream.
  for (const building of BUILDINGS) {
    const bx = building.x * TILE,
      by = (building.y + building.h) * TILE;
    ctx.fillStyle = "rgba(40,32,38,.15)";
    ctx.fillRect(bx + 12, by - 4, building.w * TILE - 18, 7);
    const offset =
      noise(building.x, building.y, seed) > 0.5 ? 12 : building.w * TILE - 22;
    ctx.fillStyle = "#a8684d";
    ctx.fillRect(bx + offset, by - 11, 10, 10);
    ctx.fillStyle = "#53754b";
    ctx.fillRect(bx + offset - 2, by - 17, 14, 8);
    ctx.fillStyle = "#e5bb84";
    ctx.fillRect(bx + offset + 2, by - 19, 4, 4);
  }

  ctx.fillStyle = "#6b4a2b";
  ctx.fillRect(792, 474, 6, 22);
  ctx.fillStyle = "#9c6a3c";
  ctx.fillRect(784, 456, 22, 20);
  ctx.fillStyle = "#7a5030";
  ctx.fillRect(784, 456, 22, 4);
  ctx.fillRect(788, 465, 14, 3);
  ctx.fillStyle = "#c94b3a";
  ctx.fillRect(806, 458, 3, 10);
  ctx.fillRect(809, 458, 5, 4);
  drawSign(ctx, "Postbox", 742.4, 496);
  drawSign(ctx, "Mirror", 1068.8, 630);

  for (const [bx, by] of BENCHES) {
    const x = bx * TILE;
    const y = by * TILE;
    ctx.fillStyle = "#6b4a2b";
    ctx.fillRect(x, y + 10, 4, 10);
    ctx.fillRect(x + 36, y + 10, 4, 10);
    ctx.fillStyle = "#9c6a3c";
    ctx.fillRect(x - 2, y, 44, 5);
    ctx.fillRect(x - 2, y + 8, 44, 5);
  }

  for (const [tx, ty] of TREES) drawTree(ctx, tx * TILE, ty * TILE, rand);

  const lamps: Array<{ x: number; y: number }> = [];
  for (const [lx, ly] of LAMPS) {
    const x = lx * TILE;
    const y = ly * TILE;
    ctx.fillStyle = "rgba(233,184,96,0.28)";
    ctx.beginPath();
    ctx.ellipse(x + 1, y, 22, 8, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#1f1a22";
    ctx.fillRect(x - 1, y - 40, 5, 40);
    ctx.fillRect(x - 5, y - 4, 13, 4);
    ctx.fillRect(x - 6, y - 58, 15, 14);
    ctx.fillStyle = "#3b3340";
    ctx.fillRect(x, y - 40, 3, 36);
    ctx.fillStyle = "#ffd98a";
    ctx.fillRect(x - 4, y - 55, 11, 9);
    ctx.fillStyle = "#fff3c4";
    ctx.fillRect(x - 2, y - 53, 4, 4);
    lamps.push({ x: x + 1, y: y - 50 });
  }

  return { canvas, windows, chimneys, lamps };
}
