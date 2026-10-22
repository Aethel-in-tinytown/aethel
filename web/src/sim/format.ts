/** Presentation-only formatting for bounded vitals and local journal timestamps. */
export function percent(v: number | undefined | null): number {
  return Math.round(Math.max(0, Math.min(1, v ?? 0)) * 100);
}

export function hearts(v: number | undefined | null): number {
  return Math.round(Math.max(0, Math.min(1, v ?? 0)) * 5);
}

export function asClause(activity: string | undefined): string {
  return (activity || "about").replace(/[.…\s]+$/, "");
}

export function timeStamp(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}
