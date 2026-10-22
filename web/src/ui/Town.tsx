/** Keep the render loop outside Preact; snapshots cross a small explicit bridge. */
import { useEffect, useRef, useState } from "preact/hooks";
import type { TownHandle } from "../game/createGame";
import type { AethelData } from "../sim/types";
export function Town({
  data,
  night,
  low,
  reduced,
}: {
  data: AethelData;
  night: boolean;
  low: boolean;
  reduced: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  const handle = useRef<TownHandle | null>(null);
  const latest = useRef(data);
  latest.current = data;
  const settings = useRef({ night, low, reduced });
  settings.current = { night, low, reduced };
  useEffect(() => {
    let cancelled = false;
    setError("");
    void import("../game/createGame")
      .then((module) => module.createTownGame(host.current!, latest.current))
      .then((game) => {
        if (cancelled) game.destroy();
        else {
          handle.current = game;
          game.push(latest.current);
          game.configure(settings.current);
          game.setVisible(!document.hidden);
        }
      })
      .catch(() => {
        if (!cancelled)
          setError(
            "The town illustration could not load. Her journal is still here.",
          );
      });
    const visibility = () => handle.current?.setVisible(!document.hidden);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      cancelled = true;
      handle.current?.destroy();
      handle.current = null;
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);
  useEffect(() => {
    handle.current?.push(data);
  }, [data]);
  useEffect(() => {
    handle.current?.configure({ night, low, reduced });
  }, [night, low, reduced]);
  return (
    <section class="town-frame" aria-label="Aethel’s pixel town">
      <div ref={host} class="town-host" />
      {error && (
        <div class="town-error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={() => window.location.reload()}>
            Reload the town
          </button>
        </div>
      )}
      <div class="town-atmosphere" aria-hidden="true" />
      <div class="town-caption font-pixel">
        {night
          ? "☾ windows warm, the world quiet"
          : "✦ a small world, carrying on"}
      </div>
      <span class="sr-only">
        Aethel is{" "}
        {data.status.asleep ? "sleeping" : `at ${data.status.location_pretty}`}.{" "}
        {data.town.residents
          .map((r) => `${r.name}: ${r.location_pretty ?? r.location}`)
          .join(". ")}
      </span>
    </section>
  );
}
