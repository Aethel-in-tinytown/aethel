/** Compose accessible spectator panels without subscribing the game to UI edits. */
import { useAethelData } from "../sim/provider";
import { dayFromTick } from "../sim/townLayout";
import { LetterCard, LongingHearts, Meter } from "./components";
import { Temperaments } from "./Temperaments";
import { Care, useCare } from "./Care";
import { Journal } from "./Journal";
import { Town } from "./Town";
import { usePresentation, type Quality, type Theme } from "./settings";

export function App() {
  const { data, error, config, temperaments, transport } = useAethelData();
  const care = useCare();
  const presentation = usePresentation(data?.status.asleep ?? false);
  const status = data?.status;
  return (
    <div class="page">
      <a class="skip-link" href="#main">
        Skip to her world
      </a>
      <header class="page-header">
        <div>
          <p class="eyebrow">An ordinary life, in a tiny town</p>
          <h1 class="font-serif page-title">
            Watch Aethel
            <span class="title-star" aria-hidden="true">
              ✦
            </span>
          </h1>
          <p class="page-subtitle">
            A book, a wandering thought, a light left on for you.
          </p>
        </div>
        <div class="header-tools">
          <p class="font-pixel page-status" role="status">
            <span
              class={`live-dot ${data?.reconnecting || !data ? "waiting" : ""}`}
            />
            {data?.demo
              ? "demo · illustrative world"
              : data?.reconnecting
                ? "reconnecting · last known moment"
                : status?.stale
                  ? "her last known moment"
                  : `${transport} · heartbeat ${status?.tick ?? "…"}`}
          </p>
          <div class="presentation-controls">
            <label>
              Light
              <select
                aria-label="Light"
                value={presentation.theme}
                onChange={(e) =>
                  presentation.setTheme(e.currentTarget.value as Theme)
                }
              >
                <option value="auto">Her rhythm</option>
                <option value="day">Daylight</option>
                <option value="night">Nightfall</option>
              </select>
            </label>
            <label>
              Effects
              <select
                aria-label="Effects"
                value={presentation.quality}
                onChange={(e) =>
                  presentation.setQuality(e.currentTarget.value as Quality)
                }
              >
                <option value="full">Full atmosphere</option>
                <option value="low">Quiet & light</option>
              </select>
            </label>
          </div>
        </div>
      </header>
      {error && (
        <p class="connection-note" role="alert">
          {error} · We’ll keep trying.
        </p>
      )}
      {!data || !status ? (
        <main id="main" class="loading-state" aria-busy="true">
          <span class="loading-star">✦</span>
          <h2 class="font-serif">The town is waking up</h2>
          <p>Finding her latest moment…</p>
        </main>
      ) : (
        <>
          <main id="main" class="page-main">
            <div class="world-column">
              <Town
                data={data}
                night={presentation.night}
                low={presentation.quality === "low"}
                reduced={presentation.reducedMotion}
              />
              <div class="world-note">
                <span class="font-serif">Day {dayFromTick(status.tick)}</span>
                <span>
                  {status.asleep
                    ? "A dream is taking shape."
                    : "There is always another page."}
                </span>
                <span class="font-pixel">
                  {status.mood_name || "a little weather within"}
                </span>
              </div>
              <Care
                care={care}
                enabled={!!config?.care_enabled && !data.demo}
              />
            </div>
            <aside class="panel side-panel">
              <div>
                <div class="name-row">
                  <h2 class="font-serif">Aethel</h2>
                  <span class="day-badge font-pixel">
                    Day {dayFromTick(status.tick)}
                  </span>
                </div>
                <p class="location font-pixel">
                  {status.asleep
                    ? "☾ asleep, dreaming"
                    : status.location_pretty}
                </p>
                <p class="font-serif activity">{status.activity}</p>
              </div>
              <div class="meters">
                <Meter label="Food" value={status.vitals.satiety} />
                <Meter label="Water" value={status.vitals.hydration} />
                <Meter label="Air" value={status.vitals.oxygen} />
                <Meter
                  label="Will to live"
                  value={status.vitals.vitality}
                  pink
                />
                <Meter label="Excitement" value={status.vitals.excitement} />
                <LongingHearts value={status.vitals.longing} />
              </div>
              <div class="reading-card">
                <p>
                  Currently reading:{" "}
                  <span class="font-serif reading-title">
                    {status.reading || "nothing just now"}
                  </span>
                </p>
                <div class="font-pixel counters">
                  <span>{status.meals_eaten.toLocaleString()} meals eaten</span>
                  <span>{status.concepts.toLocaleString()} things learned</span>
                </div>
              </div>
              <Journal entries={data.journal} cursor={data.journal_cursor} />
              <section aria-labelledby="letters-title">
                <h3 id="letters-title" class="font-serif aside-title">
                  From her postbox
                </h3>
                {data.letters.length ? (
                  <div class="letters">
                    {data.letters.map((l) => (
                      <LetterCard key={l.id ?? l.subject} letter={l} />
                    ))}
                  </div>
                ) : (
                  <p class="letters-empty">
                    No letters yet. She writes when something has been on her
                    mind.
                  </p>
                )}
              </section>
            </aside>
          </main>
          <Temperaments
            status={status}
            records={temperaments}
            request={
              care.unlocked && !care.busy
                ? (id) => void care.send("temperament", { temperament: id })
                : undefined
            }
          />
        </>
      )}
      <footer class="page-footer">
        <span class="footer-flower" aria-hidden="true">
          ✳
        </span>
        <p>
          Aethel is a performance, not a person — a digital organism played by
          software.
        </p>
        <p>She is not conscious. She is just very committed to the bit.</p>
      </footer>
    </div>
  );
}
