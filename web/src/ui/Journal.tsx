/** Stable journal IDs preserve focus and only animate genuinely new entries. */
import { useMemo, useState } from "preact/hooks";
import { api } from "../sim/provider";
import type { JournalEntry } from "../sim/types";
import { JournalItem } from "./components";
export function Journal({
  entries,
  cursor,
}: {
  entries: JournalEntry[];
  cursor?: number | null;
}) {
  const [search, setSearch] = useState("");
  const [event, setEvent] = useState("");
  const [older, setOlder] = useState<JournalEntry[]>([]);
  const [next, setNext] = useState<number | null | undefined>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const all = useMemo(() => {
    const map = new Map(
      [...older, ...entries].map((e) => [e.id ?? e.t + e.text, e]),
    );
    return [...map.values()].sort((a, b) => (b.id ?? 0) - (a.id ?? 0));
  }, [entries, older]);
  const filtered = all.filter(
    (e) =>
      (!event || e.event === event) &&
      e.text.toLowerCase().includes(search.toLowerCase()),
  );
  const more = next === undefined ? cursor : next;
  const load = async () => {
    setBusy(true);
    setError("");
    try {
      const page = await api<{
        entries: JournalEntry[];
        next_cursor: number | null;
      }>(`journal?limit=30&before=${more}`);
      setOlder((items) => [...items, ...page.entries]);
      setNext(page.next_cursor);
    } catch {
      setError("Could not load earlier moments. Please try again.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <section aria-labelledby="journal-title">
      <h3 id="journal-title" class="font-serif aside-title">
        Her journal
      </h3>
      <div class="journal-filters">
        <label>
          Search moments
          <input
            type="search"
            value={search}
            onInput={(e) => setSearch(e.currentTarget.value)}
            placeholder="A word, a place, a feeling"
          />
        </label>
        <label>
          Kind
          <select
            value={event}
            onChange={(e) => setEvent(e.currentTarget.value)}
          >
            <option value="">All moments</option>
            <option value="experience">Days</option>
            <option value="dream">Dreams</option>
            <option value="initiation">Notes & questions</option>
          </select>
        </label>
      </div>
      <ol class="journal-list">
        {filtered.map((e) => (
          <JournalItem
            key={e.id ?? e.t + e.text}
            entry={e}
            fresh={e.id === entries[0]?.id}
          />
        ))}
      </ol>
      {!filtered.length && (
        <p class="letters-empty">No moments match just yet.</p>
      )}
      {more && (
        <button type="button" disabled={busy} onClick={() => void load()}>
          {busy ? "Finding earlier moments…" : "Earlier moments"}
        </button>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
