/** Small accessible status primitives with no network or simulation side effects. */
import { hearts, percent } from "../sim/format";
import type { JournalEntry, Letter } from "../sim/types";
import { timeStamp } from "../sim/format";

export function Meter({
  label,
  value,
  pink,
}: {
  label: string;
  value: number;
  pink?: boolean;
}) {
  const p = percent(value);
  return (
    <div class="meter-row">
      <span>{label}</span>
      <div
        class="meter-track"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={p}
      >
        <div
          class={`meter-fill${pink ? " meter-fill-pink" : ""}`}
          style={{ width: `${p}%` }}
        />
      </div>
      <span class="meter-value font-pixel">{p}%</span>
    </div>
  );
}

export function LongingHearts({ value }: { value: number }) {
  const n = hearts(value);
  return (
    <div class="meter-row meter-row-hearts">
      <span>Longing</span>
      <span class="hearts font-pixel" aria-label={`Longing ${n} of 5`}>
        {Array.from({ length: 5 }, (_, i) => (
          <span key={i} class={i < n ? "heart-on" : "heart-off"}>
            ♥
          </span>
        ))}
      </span>
    </div>
  );
}

export function JournalItem({
  entry,
  fresh,
}: {
  entry: JournalEntry;
  fresh: boolean;
}) {
  const dream = entry.event === "dream";
  return (
    <li
      class={`journal-item${fresh ? " fade-in-entry" : ""}${dream ? " dream" : ""}`}
    >
      <span class="journal-time font-pixel">
        {dream ? "☾ " : ""}
        {timeStamp(entry.t)}
      </span>
      <span>{entry.text}</span>
    </li>
  );
}

export function LetterCard({ letter }: { letter: Letter }) {
  const body = letter.text ?? letter.body ?? JSON.stringify(letter);
  return (
    <article class="letter">
      {(letter.to || letter.subject) && (
        <p class="letter-subject">{letter.subject ?? `To ${letter.to}`}</p>
      )}
      <p class="letter-body">{body}</p>
    </article>
  );
}

export function CareDots({ n }: { n: number }) {
  return (
    <span class="care-dots" aria-label={`Care ${n} of 5`}>
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i} class={`care-dot${i < n ? " on" : ""}`} />
      ))}
    </span>
  );
}

/** Rates use a shared two-times scale, with an explicit baseline marker. */
export function NeedBar({ label, v }: { label: string; v: number }) {
  return (
    <div class="need-row">
      <span>{label}</span>
      <div class="need-track">
        <span class="need-baseline" />
        <div
          class="need-fill"
          style={{ width: `${Math.min(100, (v / 2) * 100)}%` }}
        />
      </div>
      <span class="font-pixel">{v.toFixed(2)}×</span>
    </div>
  );
}
