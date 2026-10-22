/** Rasterize directional pixel portraits with an idle pose and two distinct strides. */
import type { CharacterDef } from "../sim/townLayout";

export type Direction = "down" | "up" | "left" | "right";
export const DIRECTIONS: Direction[] = ["down", "up", "left", "right"];

export const FRAME_W = 40;
export const FRAME_H = 64;
export const ANCHOR_X = FRAME_W / 2;
export const ANCHOR_Y = FRAME_H - 4;

/** Anchor every frame at the feet so changing direction never shifts its position. */
export function drawCharacter(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  c: CharacterDef,
  dir: Direction,
  frame: number,
  walking: boolean,
  bob: number,
): number {
  const cx = Math.round(x);
  const cy = Math.round(y);
  const px = (dx: number, dy: number, w: number, h: number, color: string) => {
    ctx.fillStyle = color;
    ctx.fillRect(cx + dx * 2, cy + dy * 2, w * 2, h * 2);
  };

  ctx.fillStyle = "rgba(40,25,10,0.28)";
  ctx.beginPath();
  ctx.ellipse(cx, cy, 11, 4, 0, 0, Math.PI * 2);
  ctx.fill();

  const lift = walking ? 0 : bob;
  const tall = c.tall ? -2 : 0;
  const step = walking ? (frame % 2 === 0 ? 1 : -1) : 0;
  const side = dir === "left" || dir === "right";
  const flip = dir === "left" ? -1 : 1;
  const fx = (v: number, w: number) => (flip === 1 ? v : -v - w);

  if (c.dress) {
    px(-3, -3, 2, 3 - (step > 0 ? 1 : 0), "#5a3d2e");
    px(1, -3, 2, 3 - (step < 0 ? 1 : 0), "#5a3d2e");
  } else if (side) {
    px(fx(-2 + step, 2), -5, 2, 5, c.bottom);
    px(fx(0 - step, 2), -5, 2, 5, c.bottom);
    px(fx(-2 + step, 3), -1, 3, 1, "#3a2a20");
  } else {
    px(-3, -5, 2, 5 - (step > 0 ? 1 : 0), c.bottom);
    px(1, -5, 2, 5 - (step < 0 ? 1 : 0), c.bottom);
    px(-3, -1 - (step > 0 ? 1 : 0), 2, 1, "#3a2a20");
    px(1, -1 - (step < 0 ? 1 : 0), 2, 1, "#3a2a20");
  }

  const bodyLift = lift;
  const top = -14 + tall + bodyLift;

  if (c.dress) {
    px(-5, top, 10, 9 - tall, c.top);
    px(-6, -6 + bodyLift, 12, 3, c.top);
    px(-6, -4 + bodyLift, 12, 1, c.topDark);
  } else {
    px(-5, top, 10, 9 - tall, c.top);
    px(-5, -6 + bodyLift, 10, 1, c.topDark);
    if (c.hood && dir !== "up") {
      px(-1, top + 2, 1, 4, "#e8e2d0");
      px(1, top + 2, 1, 4, "#e8e2d0");
    }
  }

  if (c.top === "#ec93ad")
    for (let i = 0; i < 3; i++) px(-3 + i * 2, top + 3, 1, 4, c.topDark);
  if (c.shawl) {
    px(-6, top, 12, 4, c.shawl);
    px(-5, top + 4, 3, 2, c.shawl);
    px(2, top + 4, 3, 2, c.shawl);
  }

  const arm = walking ? step : 0;
  if (side) {
    px(fx(-1 + arm, 2), top + 2, 2, 6, c.topDark);
    px(fx(-1 + arm, 2), top + 8, 2, 1, c.skin);
  } else {
    px(-7, top + 1 + (arm > 0 ? 1 : 0), 2, 7, c.topDark);
    px(5, top + 1 + (arm < 0 ? 1 : 0), 2, 7, c.topDark);
    px(-7, top + 8 + (arm > 0 ? 1 : 0), 2, 1, c.skin);
    px(5, top + 8 + (arm < 0 ? 1 : 0), 2, 1, c.skin);
  }

  const head = top - 8;
  px(-4, head, 8, 8, c.skin);
  const hair = c.hair;

  if (dir === "up") {
    px(-5, head - 1, 10, 8, hair);
    if (c.hairStyle === "long") px(-5, head + 7, 10, 6, hair);
    if (c.hairStyle === "wavy") {
      px(-5, head + 7, 10, 3, hair);
      px(-4, head + 10, 8, 1, hair);
    }
  } else {
    px(-5, head - 1, 10, 3, hair);
    if (c.hairStyle === "messy") {
      px(-5, head - 2, 2, 1, hair);
      px(-1, head - 2, 2, 1, hair);
      px(3, head - 2, 2, 1, hair);
      px(-4, head + 2, 2, 1, hair);
    }
    if (side) {
      px(fx(-5, 4), head, 4, 5, hair);
      if (c.hairStyle === "long") px(fx(-5, 3), head + 5, 3, 7, hair);
      if (c.hairStyle === "wavy") px(fx(-5, 3), head + 5, 3, 4, hair);
      px(fx(2, 1), head + 4, 1, 1, "#2a1a12");
      px(fx(2, 1), head + 6, 1, 1, "#d98a7a");
    } else {
      px(-5, head + 2, 1, 3, hair);
      px(4, head + 2, 1, 3, hair);
      if (c.hairStyle === "long") {
        px(-6, head + 2, 2, 11, hair);
        px(4, head + 2, 2, 11, hair);
      }
      if (c.hairStyle === "wavy") {
        px(-6, head + 2, 2, 7, hair);
        px(4, head + 2, 2, 7, hair);
        px(-7, head + 5, 1, 2, hair);
        px(6, head + 5, 1, 2, hair);
      }
      if (dir === "down") {
        px(-2, head + 4, 1, 1, "#2a1a12");
        px(1, head + 4, 1, 1, "#2a1a12");
        px(-3, head + 5, 1, 1, "#eaa08e");
        px(2, head + 5, 1, 1, "#eaa08e");
        if (c.stubble) px(-2, head + 6, 4, 1, "#b38c6c");
      }
    }
  }

  if (c.hairStyle === "bun") px(-2, head - 4, 4, 3, hair);
  if (c.cap) {
    px(-5, head - 2, 10, 3, c.cap);
    if (dir === "down") px(-5, head + 1, 10, 1, "#3e3122");
    else if (side) px(fx(3, 3), head + 1, 3, 1, "#3e3122");
  }

  return cy + (head - 1) * 2;
}

export const FRAMES_PER_DIR = 3; // Idle plus alternating left and right strides.

/** Keep all direction/stride combinations inside the generated sprite sheet. */
export function frameIndex(dir: Direction, frame: number): number {
  return DIRECTIONS.indexOf(dir) * FRAMES_PER_DIR + (frame % FRAMES_PER_DIR);
}
