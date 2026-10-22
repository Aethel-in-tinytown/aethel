/** Project authoritative resident locations into visible actor identities. */
import { normalizePlace } from "./townLayout";
import type { Resident, ResidentKind, Status } from "./types";

export interface ActorAssignment {
  name: string;
  kind: ResidentKind | "aethel";
  place: string;

  hide: boolean;
}

export function computeAssignments(
  status: Status,
  residents: Resident[],
): ActorAssignment[] {
  const out: ActorAssignment[] = [];
  out.push({
    name: "Aethel",
    kind: "aethel",
    place: status.asleep ? "home" : normalizePlace(status.location),
    hide: false,
  });
  residents.forEach((r) => {
    out.push({
      name: r.name,
      kind: r.kind,
      place: normalizePlace(r.location),
      hide: false,
    });
  });
  return out;
}
