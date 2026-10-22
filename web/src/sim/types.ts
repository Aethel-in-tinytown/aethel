/** Shared frontend domain types. Runtime checks live at the protocol boundary. */
export interface Vitals {
  satiety: number;
  hydration: number;
  oxygen: number;
  vitality: number;
  excitement: number;
  longing: number;
  mood: number;
  sleep_pressure: number;
  awareness: number;
}

export interface Status {
  language?: {
    backend: "heuristic" | "nltk";
    pipeline_revision: number;
    nltk_version: string | null;
    resources: Record<string, string>;
  };
  temperament?: string;
  temperament_pending?: string | null;
  mood_name?: string | null;
  grammar_rules?: number;
  grammar_last_rule?: string | null;
  tick: number;
  version: string;
  alive: boolean;
  stale: boolean;
  vitals: Vitals;
  location: string;
  location_pretty: string;
  activity: string;
  asleep: boolean;
  meals_eaten: number;
  concepts: number;
  reading: string;
}

export interface JournalEntry {
  id?: number;
  t: string;
  event: string;
  text: string;
  n: number;
}

export interface Place {
  key: string;
  name: string;
}

export type ResidentKind = "denizen" | "parent" | "aethel";

export interface Resident {
  name: string;
  location: string;
  location_pretty: string;
  kind: ResidentKind;
}

export interface Town {
  places: Place[];
  residents: Resident[];
  aethel?: { location: string; location_pretty: string };
}

export interface Letter {
  id?: string;
  to?: string;
  subject?: string;
  text?: string;
  body?: string;
}

export interface AethelData {
  world_seed?: string;
  revision?: number;
  published_at?: string;
  journal_cursor?: number | null;
  status: Status;
  journal: JournalEntry[];
  town: Town;
  letters: Letter[];

  demo: boolean;

  reconnecting: boolean;
}
