/** Validate the public boundary before allowing malformed data into rendering. */
import type { AethelData, Status } from "./types";
export interface RuntimeConfig {
  websocket_engine: string;
  websocket_port: number | null;
  websocket_path: string;
  proxied: boolean;
  care_enabled: boolean;
}
export interface TemperamentRecord {
  id: string;
  name: string;
  care_load: number;
  burn: Record<string, number>;
  longing: Record<string, number>;
  voices: Record<string, number>;
  prompt: string;
  jitter: [number, number] | null;
}
function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}
export function parseSnapshot(value: unknown): AethelData {
  if (
    !record(value) ||
    !record(value.status) ||
    !record(value.status.vitals) ||
    !record(value.town)
  )
    throw new Error("Invalid snapshot");
  const status = value.status;
  if (
    typeof value.world_seed !== "string" ||
    !Number.isSafeInteger(value.revision) ||
    !Number.isSafeInteger(status.tick) ||
    !["activity", "location", "location_pretty", "version", "reading"].every(
      (k) => typeof status[k] === "string",
    ) ||
    typeof status.asleep !== "boolean" ||
    typeof status.stale !== "boolean" ||
    !["concepts", "meals_eaten"].every(
      (k) => typeof status[k] === "number" && Number.isFinite(status[k]),
    ) ||
    ![
      "satiety",
      "hydration",
      "oxygen",
      "vitality",
      "excitement",
      "longing",
      "mood",
      "sleep_pressure",
      "awareness",
    ].every(
      (k) =>
        typeof (status.vitals as Record<string, unknown>)[k] === "number" &&
        Number.isFinite((status.vitals as Record<string, number>)[k]),
    )
  )
    throw new Error("Invalid status");
  if (
    !Array.isArray(value.journal) ||
    !value.journal.every(
      (e) =>
        record(e) &&
        Number.isSafeInteger(e.id) &&
        typeof e.text === "string" &&
        typeof e.t === "string" &&
        typeof e.event === "string",
    )
  )
    throw new Error("Invalid journal");
  if (
    !Array.isArray(value.town.residents) ||
    !value.town.residents.every(
      (r) =>
        record(r) &&
        typeof r.name === "string" &&
        typeof r.location === "string" &&
        ["parent", "denizen"].includes(String(r.kind)),
    )
  )
    throw new Error("Invalid residents");
  if (
    !Array.isArray(value.letters) ||
    !value.letters.every(
      (l) =>
        record(l) && typeof l.id === "string" && typeof l.text === "string",
    )
  )
    throw new Error("Invalid letters");
  return {
    ...value,
    status: status as unknown as Status,
    demo: false,
    reconnecting: false,
  } as unknown as AethelData;
}
