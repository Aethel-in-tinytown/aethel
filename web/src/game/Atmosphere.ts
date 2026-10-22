/** Cached lighting and bounded particles, independent from actor reconciliation. */
import Phaser from "phaser";
import { MAP_H, MAP_W } from "../sim/townLayout";
import { seededRandom } from "../sim/prng";
import type { TownArt } from "./townArt";
interface Settings {
  night: boolean;
  low: boolean;
  reduced: boolean;
  seed: number;
}
interface Drifter {
  image: Phaser.GameObjects.Image;
  phase: number;
  speed: number;
}
interface Smoke {
  image: Phaser.GameObjects.Image;
  age: number;
  velocity: number;
}

export class Atmosphere {
  private amount = 0;
  private smokeClock = 0;
  private random: () => number;
  private smoke: Smoke[] = [];
  private pool: Phaser.GameObjects.Image[] = [];
  private stars: Drifter[] = [];
  private fireflies: Drifter[] = [];
  private lights: Phaser.GameObjects.Image[] = [];
  private windows: Phaser.GameObjects.Image[] = [];
  private grade: Phaser.GameObjects.Image;
  private warmth: Phaser.GameObjects.Rectangle;

  constructor(
    private scene: Phaser.Scene,
    private art: TownArt,
    private settings: Settings,
  ) {
    this.random = seededRandom(settings.seed ^ 99);
    this.texture("ambient-dot", 2, 2, (ctx) => {
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, 2, 2);
    });
    this.texture("ambient-puff", 8, 8, (ctx) => {
      ctx.fillStyle = "#ebe4d7";
      ctx.fillRect(0, 0, 8, 8);
    });
    this.texture("ambient-glow", 140, 140, (ctx) => {
      const gradient = ctx.createRadialGradient(70, 70, 2, 70, 70, 70);
      gradient.addColorStop(0, "#ffc86eff");
      gradient.addColorStop(1, "#ffc86e00");
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, 140, 140);
    });
    this.texture("ambient-grade", MAP_W, MAP_H, (ctx) => {
      const sky = ctx.createLinearGradient(0, 0, MAP_W * 0.6, MAP_H);
      sky.addColorStop(0, "#161a40");
      sky.addColorStop(0.5, "#243357");
      sky.addColorStop(1, "#392e4b");
      ctx.fillStyle = sky;
      ctx.fillRect(0, 0, MAP_W, MAP_H);
      const vignette = ctx.createRadialGradient(
        MAP_W / 2,
        MAP_H / 2,
        MAP_H * 0.2,
        MAP_W / 2,
        MAP_H / 2,
        MAP_W * 0.65,
      );
      vignette.addColorStop(0, "#00000000");
      vignette.addColorStop(1, "#0c1027aa");
      ctx.fillStyle = vignette;
      ctx.fillRect(0, 0, MAP_W, MAP_H);
    });
    this.warmth = scene.add
      .rectangle(0, 0, MAP_W, MAP_H, 0xffc46e)
      .setOrigin(0)
      .setDepth(1)
      .setAlpha(0.08);
    this.grade = scene.add
      .image(0, 0, "ambient-grade")
      .setOrigin(0)
      .setDepth(500)
      .setAlpha(0);
    for (const lamp of art.lamps)
      this.lights.push(this.glow(lamp.x, lamp.y, "ambient-glow"));
    for (const window of art.windows)
      this.windows.push(
        this.glow(
          window.x + window.w / 2,
          window.y + window.h / 2,
          "ambient-puff",
        )
          .setDisplaySize(window.w, window.h)
          .setTint(0xffbe5a),
      );
    for (let i = 0; i < 70; i++)
      this.stars.push({
        image: this.glow(
          this.random() * MAP_W,
          this.random() * MAP_H,
          "ambient-dot",
        ).setTint(0xfffadc),
        phase: this.random() * 6,
        speed: 0,
      });
    for (let i = 0; i < 40; i++)
      this.fireflies.push({
        image: this.glow(
          this.random() * MAP_W,
          this.random() * MAP_H,
          "ambient-dot",
        ),
        phase: this.random() * 6,
        speed: 0.2 + this.random() * 0.5,
      });
  }

  private texture(
    key: string,
    width: number,
    height: number,
    paint: (ctx: CanvasRenderingContext2D) => void,
  ) {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    paint(canvas.getContext("2d")!);
    this.scene.textures.addCanvas(key, canvas);
  }
  private glow(x: number, y: number, texture: string) {
    return this.scene.add
      .image(x, y, texture)
      .setBlendMode(Phaser.BlendModes.ADD)
      .setDepth(600)
      .setAlpha(0);
  }

  /** Reuse cached gradients and smoke sprites; quality changes never rebuild art. */
  update(time: number, dt: number) {
    const { low, reduced, night } = this.settings;
    this.amount += ((night ? 1 : 0) - this.amount) * Math.min(1, dt * 0.6);
    this.grade.setAlpha(0.48 * this.amount);
    this.warmth.setAlpha(0.08 * (1 - this.amount));
    for (const light of this.lights) light.setAlpha(0.5 * this.amount);
    for (const window of this.windows) window.setAlpha(0.45 * this.amount);
    for (const star of this.stars)
      star.image.setAlpha(
        (reduced ? 0.5 : 0.5 + 0.5 * Math.sin(time * 1.5 + star.phase)) *
          this.amount *
          0.65,
      );
    for (const fly of this.fireflies) {
      if (low || reduced) {
        fly.image.setAlpha(0);
        continue;
      }
      fly.image.x +=
        Math.sin(time * 0.3 + fly.phase) * 6 * dt + 4 * dt * fly.speed;
      fly.image.y -= 5 * dt * fly.speed;
      if (fly.image.y < -4) fly.image.y = MAP_H + 4;
      if (fly.image.x > MAP_W + 4) fly.image.x = -4;
      fly.image
        .setTint(this.amount > 0.5 ? 0xdcff96 : 0xffecaa)
        .setAlpha(
          (0.25 + 0.25 * Math.sin(time * 2 + fly.phase)) *
            (this.amount > 0.5 ? 1.2 : 1),
        );
    }
    this.smokeClock += dt;
    if (!reduced && this.smokeClock > (low ? 1.4 : 0.35)) {
      this.smokeClock = 0;
      for (const chimney of this.art.chimneys) {
        if (this.smoke.length >= 64) break;
        if (this.random() > 0.6) continue;
        const image = (
          this.pool.pop() ?? this.scene.add.image(0, 0, "ambient-puff")
        )
          .setPosition(chimney.x, chimney.y)
          .setDepth(2)
          .setAlpha(0.45)
          .setDisplaySize(8, 8);
        this.smoke.push({ image, age: 0, velocity: 4 + this.random() * 6 });
      }
    }
    for (let i = this.smoke.length - 1; i >= 0; i--) {
      const puff = this.smoke[i];
      puff.age += dt;
      puff.image.y -= 12 * dt;
      puff.image.x += puff.velocity * dt;
      if (puff.age > 3.2 || reduced) {
        puff.image.setAlpha(0);
        this.pool.push(puff.image);
        this.smoke.splice(i, 1);
      } else {
        const size = 4 + puff.age * 4;
        puff.image
          .setDisplaySize(size, size)
          .setAlpha(0.45 * (1 - puff.age / 3.2));
      }
    }
  }

  dispose() {
    for (const image of [
      ...this.lights,
      ...this.windows,
      ...this.stars.map((s) => s.image),
      ...this.fireflies.map((f) => f.image),
      ...this.smoke.map((s) => s.image),
      ...this.pool,
    ])
      image.destroy();
    this.grade.destroy();
    this.warmth.destroy();
    for (const key of [
      "ambient-dot",
      "ambient-puff",
      "ambient-glow",
      "ambient-grade",
    ])
      this.scene.textures.remove(key);
    this.smoke = [];
    this.pool = [];
    this.lights = [];
    this.windows = [];
    this.stars = [];
    this.fireflies = [];
  }
}
