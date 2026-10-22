/** Live data enters through one revision-checked store; demos are explicit. */
import { useEffect, useState } from "preact/hooks";
import type { AethelData } from "./types";
import {
  parseSnapshot,
  type RuntimeConfig,
  type TemperamentRecord,
} from "./protocol";
export { tickDemo } from "./demo";
export const POLL_MS = 5000;

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  init.signal?.addEventListener("abort", cancel, { once: true });
  if (init.signal?.aborted) cancel();
  const timeout = setTimeout(cancel, 10_000);
  try {
    const response = await fetch(`/api/v1/${path}`, {
      cache: "no-store",
      ...init,
      signal: controller.signal,
    });
    const body = await response.json();
    if (!response.ok)
      throw new Error(
        body?.error?.message ?? `Request failed (${response.status})`,
      );
    return body as T;
  } finally {
    clearTimeout(timeout);
    init.signal?.removeEventListener("abort", cancel);
  }
}

export function useAethelData() {
  const [data, setData] = useState<AethelData | null>(null);
  const [error, setError] = useState("");
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [temperaments, setTemperaments] = useState<TemperamentRecord[]>([]);
  const [transport, setTransport] = useState("connecting");
  useEffect(() => {
    let disposed = false,
      revision = -1,
      failures = 0;
    let socket: WebSocket | undefined;
    let pollTimer: ReturnType<typeof setTimeout>;
    let socketTimer: ReturnType<typeof setTimeout>;
    let configTimer: ReturnType<typeof setTimeout>;
    let pollingStarted = false;
    let pollingInFlight = false;
    let lastMessage = Date.now();
    const abort = new AbortController();
    const accept = (payload: unknown) => {
      const snapshot = parseSnapshot(payload);
      if (snapshot.revision! < revision) return;
      revision = snapshot.revision!;
      if (!disposed) {
        setData(snapshot);
        setError("");
      }
    };
    const poll = async () => {
      if (disposed || pollingInFlight) return;
      pollingInFlight = true;
      try {
        accept(await api("snapshot", { signal: abort.signal }));
        failures = 0;
        if (!disposed && socket?.readyState !== WebSocket.OPEN)
          setTransport("polling");
      } catch (cause) {
        if (!disposed) {
          setError(String(cause instanceof Error ? cause.message : cause));
          setData((d) => (d ? { ...d, reconnecting: true } : d));
        }
        failures++;
      } finally {
        pollingInFlight = false;
        if (!disposed)
          pollTimer = setTimeout(
            poll,
            socket?.readyState === WebSocket.OPEN
              ? 30_000
              : Math.min(30_000, POLL_MS * 2 ** Math.min(failures, 3)),
          );
      }
    };
    const connect = (settings: RuntimeConfig) => {
      if (disposed || settings.websocket_engine === "disabled") return;
      const url = new URL(settings.websocket_path, window.location.href);
      url.protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      // A proxy uses the public /stream path; direct local launches use the companion port.
      if (settings.websocket_port && !settings.proxied)
        url.port = String(settings.websocket_port);
      socket = new WebSocket(url);
      socket.onopen = () => {
        failures = 0;
        lastMessage = Date.now();
        setTransport("live");
      };
      socket.onmessage = (event) => {
        try {
          accept(JSON.parse(event.data));
          lastMessage = Date.now();
        } catch {
          socket?.close(1002, "Invalid snapshot");
        }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (disposed) return;
        setTransport("polling");
        socketTimer = setTimeout(
          () => connect(settings),
          Math.min(30_000, 1000 * 2 ** Math.min(failures++, 5)) *
            (0.75 + Math.random() / 2),
        );
      };
    };
    const boot = async () => {
      if (new URLSearchParams(location.search).get("demo") === "1") {
        const { DEMO_DATA } = await import("./demoSnapshot");
        if (!disposed) {
          setData(DEMO_DATA);
          setTransport("demo");
        }
        return;
      }
      if (!pollingStarted) {
        pollingStarted = true;
        void poll();
      }
      try {
        const [settings, definitions] = await Promise.all([
          api<RuntimeConfig>("config", { signal: abort.signal }),
          api<{ temperaments: TemperamentRecord[] }>("temperaments", {
            signal: abort.signal,
          }),
        ]);
        if (!disposed) {
          setConfig(settings);
          setTemperaments(definitions.temperaments);
          connect(settings);
        }
      } catch (cause) {
        if (!disposed) {
          setError(String(cause));
          configTimer = setTimeout(boot, 5000);
        }
      }
    };
    const offline = () => {
      socket?.close();
      setTransport("reconnecting");
      setData((current) =>
        current ? { ...current, reconnecting: true } : current,
      );
    };
    const online = () => {
      clearTimeout(pollTimer);
      if (pollingStarted) void poll();
    };
    window.addEventListener("offline", offline);
    window.addEventListener("online", online);
    void boot();
    const health = setInterval(() => {
      if (Date.now() - lastMessage > 90_000) socket?.close();
    }, 15_000);
    return () => {
      disposed = true;
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
      abort.abort();
      clearTimeout(pollTimer);
      clearTimeout(socketTimer);
      clearTimeout(configTimer);
      clearInterval(health);
      socket?.close();
    };
  }, []);
  return { data, error, config, temperaments, transport };
}
