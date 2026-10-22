/** Credentials stay in memory; retries reuse the same command identifier. */
import { useRef, useState } from "preact/hooks";
import { api } from "../sim/provider";

export interface Receipt {
  id: string;
  status: string;
  tick?: number;
  command?: { kind: string };
}
export function useCare() {
  const [token, setToken] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [unlocked, unlock] = useState(false);
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const retry = useRef<{ id: string; signature: string } | null>(null);
  const send = async (kind: string, fields: Record<string, string> = {}) => {
    const signature = JSON.stringify({ kind, ...fields });
    const id =
      retry.current?.signature === signature
        ? retry.current.id
        : crypto.randomUUID();
    retry.current = { id, signature };
    setBusy(true);
    try {
      const receipt = await api<Receipt>("commands", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ id, kind, ...fields }),
      });
      setMessage(
        `${kind === "temperament" ? "Nature request" : kind === "letter" ? "Letter" : "Check-in"} ${receipt.status}. She will notice at a heartbeat.`,
      );
      retry.current = null;
      void refresh().catch(() => {});
      return true;
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
      return false;
    } finally {
      setBusy(false);
    }
  };
  const refresh = async () => {
    const data = await api<{ commands: Receipt[] }>("commands", {
      headers: { Authorization: `Bearer ${token}` },
    });
    setReceipts(data.commands);
  };
  return {
    token,
    setToken,
    message,
    setMessage,
    busy,
    send,
    receipts,
    refresh,
    unlocked,
    unlock,
  };
}

export function Care({
  care,
  enabled,
}: {
  care: ReturnType<typeof useCare>;
  enabled: boolean;
}) {
  const [draft, setDraft] = useState("");
  const { unlocked, unlock } = care;
  return (
    <section class="panel care-panel" aria-labelledby="care-title">
      <div>
        <p class="eyebrow">A little company</p>
        <h2 id="care-title" class="font-serif">
          Leave a light on
        </h2>
        <p>
          Check in, write a letter, or ask her to try a new nature. She carries
          on in her own time.
        </p>
      </div>
      {!enabled ? (
        <p>Care is disabled on this server. You can still watch her world.</p>
      ) : !unlocked ? (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await care.refresh();
              unlock(true);
            } catch (cause) {
              care.setMessage(
                cause instanceof Error
                  ? cause.message
                  : "Could not unlock care",
              );
              care.setToken("");
            }
          }}
        >
          <label for="owner-token">Owner token</label>
          <input
            id="owner-token"
            type="password"
            value={care.token}
            onInput={(e) => care.setToken(e.currentTarget.value)}
            required
            autoComplete="off"
          />
          <button>Unlock care</button>
          <p class="detail-note">Your token stays in this tab’s memory.</p>
        </form>
      ) : (
        <div class="care-actions">
          <div class="button-row">
            <button
              type="button"
              disabled={care.busy}
              onClick={() => void care.send("check-in")}
            >
              Knock on her door
            </button>
            <button
              type="button"
              class="quiet"
              onClick={() => {
                care.setToken("");
                care.setMessage("");
                setDraft("");
                unlock(false);
              }}
            >
              Lock care
            </button>
          </div>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (await care.send("letter", { text: draft })) setDraft("");
            }}
          >
            <label for="letter">A letter from home</label>
            <textarea
              id="letter"
              value={draft}
              onInput={(e) => setDraft(e.currentTarget.value)}
              rows={4}
              maxLength={4000}
              required
              placeholder="Tell her about your day…"
            />
            <div class="button-row">
              <button disabled={care.busy || !draft.trim()}>Send letter</button>
              <small>{draft.length}/4000</small>
            </div>
          </form>
          <details>
            <summary>Care history</summary>
            <button
              type="button"
              class="quiet"
              onClick={() => void care.refresh().catch(() => {})}
            >
              Refresh receipts
            </button>
            <ul>
              {[...care.receipts]
                .reverse()
                .slice(0, 10)
                .map((r) => (
                  <li key={r.id}>
                    {r.command?.kind ?? "Care"} · {r.status}
                    {r.tick ? ` at tick ${r.tick}` : ""}
                  </li>
                ))}
            </ul>
          </details>
        </div>
      )}
      <p role="status" aria-live="polite">
        {care.message}
      </p>
    </section>
  );
}
