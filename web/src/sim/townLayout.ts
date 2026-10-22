/** Define the familiar town geometry independently from cosmetic scenery.
 * Walkability is the navigation contract; every parked actor must occupy a valid
 * cell and leave transit lanes available for passers-by.
 */
export const TILE = 32;
export const MAP_W_TILES = 40;
export const MAP_H_TILES = 23;
export const MAP_W = MAP_W_TILES * TILE;
export const MAP_H = MAP_H_TILES * TILE;

export interface BuildingDef {
  key: string;
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
  roof: string;
  roofDark: string;
  wall: string;
  wallDark: string;
  timber?: boolean;
  ivy?: boolean;
  storeys?: number;
  chimney?: number;
  doorBottom?: boolean;
}

export const BUILDINGS: BuildingDef[] = [
  {
    key: "library",
    label: "Library",
    x: 1,
    y: 3,
    w: 7,
    h: 6,
    roof: "#55678c",
    roofDark: "#3e4c6a",
    wall: "#ece0c6",
    wallDark: "#c7b89a",
    ivy: true,
    chimney: 1,
    doorBottom: true,
  },
  {
    key: "hackernews",
    label: "Tavern",
    x: 12,
    y: 3,
    w: 6,
    h: 6,
    roof: "#8a5a3a",
    roofDark: "#6a4128",
    wall: "#d8c4a0",
    wallDark: "#b39d78",
    timber: true,
    chimney: 4,
    doorBottom: true,
  },
  {
    key: "classic",
    label: "Old Bookshop",
    x: 19,
    y: 2,
    w: 6,
    h: 7,
    roof: "#7a4e36",
    roofDark: "#5a3624",
    wall: "#d4bfa4",
    wallDark: "#ae9a7f",
    timber: true,
    ivy: true,
    storeys: 2,
    chimney: 4,
    doorBottom: true,
  },
  {
    key: "newsroom",
    label: "Newsroom",
    x: 30,
    y: 3,
    w: 5,
    h: 6,
    roof: "#8a5e52",
    roofDark: "#6a443b",
    wall: "#e2d2b4",
    wallDark: "#bca98a",
    timber: true,
    chimney: 1,
    doorBottom: true,
  },
  {
    key: "cottage",
    label: "Cottage",
    x: 36,
    y: 4,
    w: 4,
    h: 5,
    roof: "#7a4e36",
    roofDark: "#5a3624",
    wall: "#e6d6b6",
    wallDark: "#c0ae8e",
    timber: true,
    ivy: true,
    chimney: 2,
    doorBottom: true,
  },
  {
    key: "home",
    label: "Aethel's Cottage",
    x: 30,
    y: 12,
    w: 4,
    h: 5,
    roof: "#a85a6c",
    roofDark: "#7e4050",
    wall: "#efe0c2",
    wallDark: "#c8b796",
    timber: true,
    ivy: true,
    chimney: 3,
    doorBottom: true,
  },
  {
    key: "schoolhouse",
    label: "Schoolhouse",
    x: 1,
    y: 13,
    w: 7,
    h: 6,
    roof: "#55678c",
    roofDark: "#3e4c6a",
    wall: "#ece0c6",
    wallDark: "#c7b89a",
    chimney: 5,
    doorBottom: true,
  },
  {
    key: "university",
    label: "University",
    x: 13,
    y: 12,
    w: 9,
    h: 7,
    roof: "#55678c",
    roofDark: "#3e4c6a",
    wall: "#9fb48a",
    wallDark: "#7f936c",
    ivy: true,
    storeys: 2,
    chimney: 1,
    doorBottom: true,
  },
];

const t = (n: number) => n * TILE;

export interface PlaceSpot {
  key: string;
  name: string;
  x: number;
  y: number;
}

export const PLACES: Record<string, PlaceSpot> = {
  library: { key: "library", name: "Library", x: t(4.5), y: t(9.75) },
  hackernews: { key: "hackernews", name: "Tavern", x: t(15), y: t(9.75) },
  classic: { key: "classic", name: "Old Bookshop", x: t(22), y: t(9.75) },
  home: { key: "home", name: "Aethel's Cottage", x: t(32), y: t(17.75) },
  newsroom: { key: "newsroom", name: "Newsroom", x: t(32.5), y: t(9.75) },
  cottage: { key: "cottage", name: "Cottage", x: t(38), y: t(9.75) },
  schoolhouse: {
    key: "schoolhouse",
    name: "Schoolhouse",
    x: t(4.5),
    y: t(19.75),
  },
  university: {
    key: "university",
    name: "University",
    x: t(17.5),
    y: t(19.75),
  },
  postbox: { key: "postbox", name: "Postbox", x: t(25), y: t(15.6) },
  mirror: { key: "mirror", name: "Mirror", x: t(35), y: t(17.9) },
};

const PLACE_ALIASES: Record<string, string> = { wikipedia: "library" };

export function normalizePlace(location: string | undefined | null): string {
  const key = (location ?? "").toLowerCase();
  return PLACE_ALIASES[key] ?? key;
}

export const WALKABLE: boolean[][] = (() => {
  const grid = Array.from({ length: MAP_H_TILES }, () =>
    Array(MAP_W_TILES).fill(false),
  );
  const fill = (x0: number, y0: number, x1: number, y1: number) => {
    for (let y = y0; y <= y1; y++)
      for (let x = x0; x <= x1; x++)
        if (y >= 0 && y < MAP_H_TILES && x >= 0 && x < MAP_W_TILES)
          grid[y][x] = true;
  };
  fill(0, 10, 39, 11);
  fill(0, 20, 39, 21);
  fill(10, 10, 11, 21);
  fill(27, 10, 28, 21);
  fill(4, 9, 4, 9);
  fill(14, 9, 15, 9);
  fill(21, 9, 22, 9);
  fill(32, 9, 32, 9);
  fill(37, 9, 38, 9);
  fill(4, 19, 4, 19);
  fill(17, 19, 17, 19);
  fill(24, 15, 25, 19);
  fill(31, 17, 32, 19);
  fill(34, 17, 35, 19);
  return grid;
})();

export const LAMPS: Array<[number, number]> = [
  [2, 12],
  [9, 9.6],
  [18.6, 12],
  [26, 12],
  [34.6, 12],
  [39, 12],
  [6, 22],
  [13, 22],
  [23, 22],
  [31, 22],
  [38, 22],
  [12.2, 15],
];

export const TREES: Array<[number, number]> = [
  [0, 1],
  [3, 0.6],
  [9, 1],
  [10.5, 4],
  [11, 7],
  [18, 1],
  [26.5, 1],
  [28.5, 4],
  [27.5, 7],
  [35, 1],
  [38.5, 1.5],
  [0, 21.5],
  [8.5, 14],
  [8.7, 17],
  [9, 19.2],
  [23, 13],
  [30, 18],
  [39, 14],
  [36, 22.4],
  [20, 22.6],
  [2, 22.6],
];

export const BENCHES: Array<[number, number]> = [
  [6.5, 9.4],
  [30.5, 19.3],
  [19.5, 19.4],
];

export type HairStyle = "long" | "short" | "bun" | "messy" | "wavy";

export interface CharacterDef {
  skin: string;
  hair: string;
  hairStyle: HairStyle;
  top: string;
  topDark: string;
  bottom: string;
  tall?: boolean;
  dress?: boolean;
  hood?: boolean;
  cap?: string;
  stubble?: boolean;
  shawl?: string;
}

export const CHARACTERS: Record<string, CharacterDef> = {
  Aethel: {
    skin: "#f3cfa8",
    hair: "#6b4226",
    hairStyle: "long",
    top: "#ec93ad",
    topDark: "#c96f8b",
    bottom: "#5b4636",
  },
  John: {
    skin: "#e9be94",
    hair: "#2b211b",
    hairStyle: "short",
    top: "#33393d",
    topDark: "#23282b",
    bottom: "#4a4038",
    cap: "#5d4a33",
  },
  Star: {
    skin: "#f6d6b6",
    hair: "#f0dc96",
    hairStyle: "long",
    top: "#3f9c94",
    topDark: "#2e7a73",
    bottom: "#3f9c94",
    dress: true,
  },
  Julius: {
    skin: "#c99572",
    hair: "#1e1915",
    hairStyle: "short",
    top: "#2f5a3a",
    topDark: "#21432a",
    bottom: "#3b3229",
    tall: true,
  },
  Octavia: {
    skin: "#f1c9a2",
    hair: "#a4482a",
    hairStyle: "bun",
    top: "#6e3a5e",
    topDark: "#532a47",
    bottom: "#6e3a5e",
    dress: true,
  },
  Trey: {
    skin: "#dcae86",
    hair: "#3a2a1e",
    hairStyle: "messy",
    top: "#7d8a6a",
    topDark: "#5f6b4f",
    bottom: "#3e4650",
    hood: true,
  },
  Donald: {
    skin: "#ecc29b",
    hair: "#6a4a30",
    hairStyle: "short",
    top: "#c0622b",
    topDark: "#984b1f",
    bottom: "#4b4136",
    stubble: true,
  },
  Cassandra: {
    skin: "#efc6a0",
    hair: "#2a1d18",
    hairStyle: "wavy",
    top: "#8a4b3a",
    topDark: "#6d3a2c",
    bottom: "#4d3a32",
    shawl: "#b8392f",
  },
};

export const TICKS_PER_DAY = 2880;

export function dayFromTick(tick: number): number {
  return Math.floor(tick / TICKS_PER_DAY) + 1;
}
