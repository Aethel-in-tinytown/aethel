/** Browsing a nature never changes the organism; only an owner command does. */
import { useState } from "preact/hooks";
import type { Status } from "../sim/types";
import type { TemperamentRecord } from "../sim/protocol";
import { CareDots, NeedBar } from "./components";

export function Temperaments({
  status,
  records,
  request,
}: {
  status: Status;
  records: TemperamentRecord[];
  request?: (id: string) => void;
}) {
  const [selected, select] = useState("");
  const current =
    records.find((r) => r.id === selected) ??
    records.find((r) => r.id === status.temperament) ??
    records[0];
  if (!current) return null;
  const rates = [
    current.burn.hunger,
    current.burn.thirst,
    current.burn.excitement,
    current.longing.person,
    current.burn.sleep,
    current.burn.vitality,
  ];
  return (
    <section class="panel temperament-section" aria-labelledby="natures-title">
      <p class="eyebrow">A nature, not a reset</p>
      <h2 id="natures-title" class="font-serif">
        Six ways to meet the world
      </h2>
      <p>
        Active:{" "}
        <strong>
          {records.find((r) => r.id === status.temperament)?.name}
        </strong>
        {status.temperament_pending
          ? ` · ${status.temperament_pending} waits for her next waking`
          : ""}
      </p>
      <div class="temperament-grid" aria-label="Browse temperaments">
        {records.map((r) => (
          <button
            key={r.id}
            type="button"
            aria-pressed={current.id === r.id}
            onClick={() => select(r.id)}
            class={`temperament-card${current.id === r.id ? " selected" : ""}`}
          >
            <span class="font-serif temperament-name">{r.name}</span>
            <span class="font-pixel temperament-care">
              care <CareDots n={r.care_load} />
            </span>
          </button>
        ))}
      </div>
      <div class="temperament-detail">
        <div>
          <h3 class="font-serif">How her needs run</h3>
          {[
            "Hunger",
            "Thirst",
            "Excitement",
            "Longing for people",
            "Sleep",
            "Vitality",
          ].map((label, i) => (
            <NeedBar key={label} label={label} v={rates[i]} />
          ))}
          <p class="detail-note">
            1.0 is the Even Keel baseline.{" "}
            {current.jitter
              ? "Briar’s daily metabolic variation is 0.8–1.6×; excitement stays fixed."
              : ""}
          </p>
        </div>
        <div>
          <h3 class="font-serif">Council emphasis</h3>
          {Object.entries(current.voices).map(([voice, weight]) => (
            <p key={voice}>
              {voice}: {weight}×
            </p>
          ))}
          {!Object.keys(current.voices).length && (
            <p>All voices count equally.</p>
          )}
        </div>
        <div>
          <h3 class="font-serif">A starting disposition</h3>
          <p>
            {current.prompt ||
              "Balanced needs, a steady pace, and room to become herself."}
          </p>
          <p class="detail-note">
            Disposition guidance, not a diary entry or an active language model.
          </p>
          {request && (
            <button
              type="button"
              onClick={() => request(current.id)}
              disabled={
                current.id === status.temperament && !status.temperament_pending
              }
            >
              Request this nature
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
