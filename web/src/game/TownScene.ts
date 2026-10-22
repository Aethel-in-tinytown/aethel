/** Render immutable town observations with reserved movement and bounded effects.
 * Static scenery and lighting are cached textures; only actors and effect
 * positions change each frame. Presentation overrides never move backend actors.
 */
import Phaser from "phaser";
import { Atmosphere } from "./Atmosphere";
import { cosmeticSeed, seededRandom } from "../sim/prng";
import {
  advanceCrowd,
  createWalker,
  setDestination,
  type Walker,
} from "../sim/movement";
import { computeAssignments } from "../sim/actors";
import { pointId, slotFor } from "../sim/pathfinding";
import { CHARACTERS, MAP_H, MAP_W, PLACES } from "../sim/townLayout";
import type { Resident, Status } from "../sim/types";
import {
  ANCHOR_X,
  ANCHOR_Y,
  DIRECTIONS,
  drawCharacter,
  FRAME_H,
  FRAME_W,
  FRAMES_PER_DIR,
  frameIndex,
  type Direction,
} from "./pixel";
import { paintTown, PIXEL_FONT } from "./townArt";

const WALK_SPEED = 46;
const FRAME_TIME = 0.2;
const LABEL_FONT_SIZE = 16;
const LABEL_HEIGHT = 24;

interface Actor {
  walker: Walker;
  name: string;
  kind: string;
  x: number;
  y: number;
  dir: Direction;
  frame: number;
  frameT: number;
  route: Array<{ x: number; y: number }>;
  place: string;
  hidden: boolean;
  hideOnArrive: boolean;
  alpha: number;
  bobPhase: number;
  labelLift: number;
  bubble?: { text: string; until: number };
  sprite: Phaser.GameObjects.Image;
  label: Phaser.GameObjects.Image;
  bubbleBox?: Phaser.GameObjects.Image;
  zzz?: Phaser.GameObjects.Text[];
}

export interface SceneBridge {
  status: Status;
  residents: Resident[];
  dirty: boolean;
  seed: number;
  night: boolean;
  low: boolean;
  reduced: boolean;
}

export class TownScene extends Phaser.Scene {
  private bridge: SceneBridge;
  private actors = new Map<string, Actor>();
  private atmosphere?: Atmosphere;
  private random: () => number;
  private bubbleTimer = 0;

  constructor(bridge: SceneBridge) {
    super("town");
    this.bridge = bridge;
    this.random = seededRandom(bridge.seed ^ 123);
  }

  create() {
    const art = paintTown(this.bridge.seed);
    this.textures.addCanvas("town", art.canvas);
    this.add.image(0, 0, "town").setOrigin(0).setDepth(0);

    this.atmosphere = new Atmosphere(this, art, this.bridge);

    for (const [name, def] of Object.entries(CHARACTERS)) {
      const cv = document.createElement("canvas");
      cv.width = FRAME_W * DIRECTIONS.length * FRAMES_PER_DIR;
      cv.height = FRAME_H;
      const ctx = cv.getContext("2d")!;
      for (const dir of DIRECTIONS)
        for (let f = 0; f < FRAMES_PER_DIR; f++) {
          const i = frameIndex(dir, f);
          drawCharacter(
            ctx,
            i * FRAME_W + ANCHOR_X,
            ANCHOR_Y,
            def,
            dir,
            f,
            f > 0, // Frame zero rests; the other two frames alternate strides.
            0,
          );
        }
      const tex = this.textures.addCanvas(`char:${name}`, cv);
      for (let i = 0; i < DIRECTIONS.length * FRAMES_PER_DIR; i++)
        tex?.add(i, 0, i * FRAME_W, 0, FRAME_W, FRAME_H);
    }

    this.syncActors();
    this.events.once("shutdown", () => {
      for (const actor of this.actors.values())
        this.textures.remove(actor.label.texture.key);
      this.actors.clear();
      this.atmosphere?.dispose();
    });
  }

  /** Reconcile identities and targets; unchanged destinations retain their routes. */
  private syncActors() {
    const assignments = computeAssignments(
      this.bridge.status,
      this.bridge.residents,
    );

    for (const a of assignments) {
      const place = PLACES[a.place] ? a.place : "classic";
      let actor = this.actors.get(a.name);
      if (!actor) {
        const spot = PLACES[place];
        actor = {
          walker: createWalker(
            a.name,
            slotFor(
              a.name,
              place,
              [a.name],
              spot,
              new Set(
                [...this.actors.values()].map((other) => pointId(other.walker)),
              ),
            ),
            this.bridge.seed,
          ),
          name: a.name,
          kind: a.kind,
          x: spot.x,
          y: spot.y,
          dir: "down",
          frame: 0,
          frameT: 0,
          route: [],
          place,
          hidden: a.hide,
          hideOnArrive: a.hide,
          alpha: a.hide ? 0 : 1,
          bobPhase: this.random() * 6,
          labelLift: 0,
          sprite: this.add
            .image(
              spot.x,
              spot.y,
              `char:${CHARACTERS[a.name] ? a.name : "John"}`,
              0,
            )
            .setOrigin(0.5, ANCHOR_Y / FRAME_H)
            .setDepth(10)
            .setAlpha(a.hide ? 0 : 1),
          label: this.makeLabel(a.name, a.kind === "aethel"),
        };
        this.actors.set(a.name, actor);
      }
      actor.hideOnArrive = a.hide;
      if (!a.hide && actor.hidden) actor.hidden = false;
      actor.place = place;
    }

    const reserved = new Set<number>();
    for (const actor of [...this.actors.values()].sort((a, b) =>
      a.name.localeCompare(b.name),
    )) {
      const spot = slotFor(
        actor.name,
        actor.place,
        [actor.name],
        PLACES[actor.place],
        reserved,
      );
      reserved.add(pointId(spot));
      setDestination(actor.walker, spot);
    }

    for (const name of [...this.actors.keys()])
      if (!assignments.find((a) => a.name === name)) {
        const actor = this.actors.get(name)!;
        actor.sprite.destroy();
        const labelTexture = actor.label.texture.key;
        actor.label.destroy();
        this.textures.remove(labelTexture);
        actor.bubbleBox?.destroy();
        actor.zzz?.forEach((z) => z.destroy());
        this.actors.delete(name);
      }
  }

  /** Rasterize names once so frame updates never allocate text canvases. */
  private makeLabel(name: string, isAethel: boolean): Phaser.GameObjects.Image {
    const text = isAethel ? "Aethel ♥" : name;
    const cv = document.createElement("canvas");
    const mctx = cv.getContext("2d")!;
    mctx.font = `${isAethel ? "bold " : ""}${LABEL_FONT_SIZE}px ${PIXEL_FONT}`;
    const w = Math.ceil(mctx.measureText(text).width) + 12;
    cv.width = w;
    cv.height = LABEL_HEIGHT;
    const ctx = cv.getContext("2d")!;
    ctx.fillStyle = isAethel ? "rgba(120,40,64,0.85)" : "rgba(50,32,18,0.7)";
    ctx.fillRect(0, 0, w, LABEL_HEIGHT);
    ctx.fillStyle = isAethel ? "#ffd7e2" : "#fbefd8";
    ctx.font = `${isAethel ? "bold " : ""}${LABEL_FONT_SIZE}px ${PIXEL_FONT}`;
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    ctx.fillText(text, w / 2, LABEL_HEIGHT / 2);
    const key = `label:${cosmeticSeed(name)}`;
    this.textures.addCanvas(key, cv);
    return this.add
      .image(0, 0, key)
      .setOrigin(0.5, 0.5)
      .setDepth(1000)
      .setAlpha(0);
  }

  private makeBubble(text: string): Phaser.GameObjects.Image {
    const cv = document.createElement("canvas");
    cv.width = 26;
    cv.height = 22;
    const ctx = cv.getContext("2d")!;
    ctx.fillStyle = "#fffaf0";
    ctx.fillRect(0, 0, 26, 18);
    ctx.fillRect(10, 18, 6, 4);
    ctx.fillStyle = "#4a321d";
    ctx.fillRect(0, 0, 26, 2);
    ctx.fillRect(0, 16, 26, 2);
    ctx.fillRect(0, 0, 2, 18);
    ctx.fillRect(24, 0, 2, 18);
    ctx.fillStyle = text === "♥" ? "#d9577a" : "#4a321d";
    ctx.font = `bold 12px ${PIXEL_FONT}`;
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    ctx.fillText(text, 13, 9);
    const key = `bubble:${text}`;
    if (!this.textures.exists(key)) this.textures.addCanvas(key, cv);
    return this.add.image(0, 0, key).setOrigin(0.5, 0.5).setDepth(1001);
  }

  /** Advance reservations first, then draw interpolated actors and atmosphere. */
  update(time: number, deltaMs: number) {
    const dt = Math.min(0.1, deltaMs / 1000);
    const now = time;
    const t = time / 1000;

    if (this.bridge.dirty) {
      this.bridge.dirty = false;
      this.syncActors();
    }

    const actors = [...this.actors.values()];

    advanceCrowd(
      actors.map((a) => a.walker),
      dt,
      WALK_SPEED,
    );
    for (const a of actors) {
      const dx = a.walker.x - a.x,
        dy = a.walker.y - a.y;
      a.x = a.walker.x;
      a.y = a.walker.y;
      a.route = a.walker.edge ? [a.walker.edge.end] : a.walker.route;
      if (Math.hypot(dx, dy) > 0.001) {
        a.dir =
          Math.abs(dx) > Math.abs(dy)
            ? dx > 0
              ? "right"
              : "left"
            : dy > 0
              ? "down"
              : "up";
        a.frameT += dt;
        if (a.frameT > FRAME_TIME) {
          a.frameT = 0;
          a.frame++;
        }
      }
      if (!a.route.length && a.hideOnArrive)
        a.alpha = Math.max(0, a.alpha - dt * 1.5);
      else if (!a.hidden) a.alpha = Math.min(1, a.alpha + dt * 2);
      // Hidden actors must also update their sprites; filtering them leaves ghosts.
      a.sprite.setAlpha(a.alpha);
      a.label.setAlpha(a.alpha);
      if (a.alpha <= 0 && a.hideOnArrive) {
        a.hidden = true;
        a.bubbleBox?.setAlpha(0);
        a.zzz?.forEach((z) => z.setAlpha(0));
      }
    }

    this.bubbleTimer += dt;
    if (this.bubbleTimer > 4) {
      this.bubbleTimer = 0;
      const idle = actors.filter(
        (a) => !a.route.length && !a.hidden && !a.bubble,
      );
      for (const a of idle) {
        if (idle.filter((o) => o !== a && o.place === a.place).length) {
          if (this.random() < 0.12) {
            a.bubble = {
              text: (
                a.name === "Aethel" ? this.random() < 0.5 : this.random() < 0.2
              )
                ? "♥"
                : "...",
              until: now + 2800,
            };
            break;
          }
        }
      }
    }

    const visible = actors
      .filter((a) => a.alpha > 0.01)
      .sort((a, b) => a.y - b.y);
    // Compensate for a shrinking canvas without letting nameplates dominate it.
    const renderScale = this.scale.displaySize.width / MAP_W;
    const labelScale = Math.min(
      2,
      Math.max(1, 10 / (LABEL_FONT_SIZE * Math.max(0.01, renderScale))),
    );
    const labels: {
      left: number;
      top: number;
      right: number;
      bottom: number;
    }[] = [];
    for (const a of visible) {
      const walking = a.route.length > 0;
      const asleepPose =
        a.name === "Aethel" && this.bridge.status.asleep && !walking;
      const dir: Direction = asleepPose ? "up" : a.dir;
      const frame = walking ? 1 + (a.frame % (FRAMES_PER_DIR - 1)) : 0;
      a.sprite
        .setPosition(Math.round(a.x), Math.round(a.y))
        .setFrame(frameIndex(dir, frame))
        .setAlpha(a.alpha)
        .setDepth(10 + a.y / MAP_H);

      if (!walking && !asleepPose && !this.bridge.reduced)
        a.sprite.y += Math.sin(t * 2 + a.bobPhase) > 0 ? -0.5 : 0;

      a.label.setScale(labelScale);
      const width = a.label.displayWidth,
        height = a.label.displayHeight;
      const labelX = Phaser.Math.Clamp(
        a.x,
        width / 2 + 2,
        MAP_W - width / 2 - 2,
      );
      let labelY = a.y - 56 - (walking ? 0 : a.labelLift);
      // Taller labels need separate rows when neighbors share a doorstep.
      while (
        labels.some(
          (box) =>
            labelX + width / 2 + 3 > box.left &&
            labelX - width / 2 - 3 < box.right &&
            labelY + height / 2 + 3 > box.top &&
            labelY - height / 2 - 3 < box.bottom,
        )
      ) {
        labelY -= height + 4;
      }
      labelY = Math.max(height / 2 + 2, labelY);
      labels.push({
        left: labelX - width / 2,
        right: labelX + width / 2,
        top: labelY - height / 2,
        bottom: labelY + height / 2,
      });
      a.label
        .setPosition(Math.round(labelX), Math.round(labelY))
        .setAlpha(a.alpha);

      if (a.bubble && now > a.bubble.until) {
        a.bubble = undefined;
        a.bubbleBox?.destroy();
        a.bubbleBox = undefined;
      }
      if (a.bubble) {
        if (!a.bubbleBox) a.bubbleBox = this.makeBubble(a.bubble.text);
        a.bubbleBox
          .setTexture(`bubble:${a.bubble.text}`)
          .setPosition(Math.round(a.x), Math.round(labelY - 20))
          .setAlpha(a.alpha);
      } else a.bubbleBox?.setAlpha(0);

      if (asleepPose) {
        if (!a.zzz)
          a.zzz = [0, 1, 2].map(() =>
            this.add
              .text(0, 0, "Z", {
                fontFamily: PIXEL_FONT,
                fontSize: "13px",
                fontStyle: "bold",
                color: "#f6e9ff",
              })
              .setOrigin(0.5)
              .setDepth(1002),
          );
        a.zzz.forEach((z, i) => {
          const cycle = (t * 0.5 + i / 3) % 1;
          z.setPosition(
            a.x + 14 + cycle * 16,
            labelY - 10 - cycle * 34,
          ).setAlpha(Math.sin(cycle * Math.PI) * a.alpha);
        });
      } else if (a.zzz) {
        a.zzz.forEach((z) => z.destroy());
        a.zzz = undefined;
      }
    }

    this.atmosphere?.update(t, dt);
  }
}
