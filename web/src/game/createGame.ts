/** Own Phaser lifecycle behind a snapshot/settings bridge; defer boot until fonts settle. */
import Phaser from "phaser";
import { cosmeticSeed } from "../sim/prng";
import { MAP_H, MAP_W } from "../sim/townLayout";
import type { AethelData } from "../sim/types";
import { TownScene, type SceneBridge } from "./TownScene";

export interface TownHandle {
  game: Phaser.Game;
  bridge: SceneBridge;
  push(data: AethelData): void;
  destroy(): void;
  configure(settings: { night: boolean; low: boolean; reduced: boolean }): void;
  setVisible(visible: boolean): void;
}

export async function createTownGame(
  parent: HTMLElement,
  initial: AethelData,
): Promise<TownHandle> {
  try {
    await document.fonts?.ready;
  } catch {
    /* Font API failure must not prevent a functional system-font canvas. */
  }

  const bridge: SceneBridge = {
    status: initial.status,
    residents: initial.town.residents,
    dirty: false,
    seed: cosmeticSeed(initial.world_seed ?? "7"),
    night: initial.status.asleep,
    low: false,
    reduced: false,
  };

  const scene = new TownScene(bridge);
  const game = new Phaser.Game({
    // This scene uses cached 2D art; Canvas avoids software-WebGL overhead.
    type: Phaser.CANVAS,
    parent,
    width: MAP_W,
    height: MAP_H,
    backgroundColor: "#231a20",
    pixelArt: true,
    roundPixels: true,
    scene,
    scale: {
      mode: Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_BOTH,
      width: MAP_W,
      height: MAP_H,
    },
    banner: false,
    audio: { noAudio: true },
  });

  return {
    game,
    bridge,
    push(data) {
      bridge.status = data.status;
      bridge.residents = data.town.residents;
      bridge.dirty = true;
    },
    configure(settings) {
      Object.assign(bridge, settings);
    },
    setVisible(visible) {
      if (visible) game.loop.wake();
      else game.loop.sleep();
    },
    destroy() {
      game.destroy(true);
    },
  };
}
