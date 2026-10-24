import { API_BASE, sessionState } from "../api/http";
import { status } from "../api/status";

export const SSE_TOPICS = ["review", "channels"];
export const POLL_DOWN_MS = 5000; // polling while SSE is not connected
export const POLL_UP_MS = 30000; // safety net while SSE is connected
export const backoffMs = (attempt: number) => Math.min(30000, 1000 * 2 ** attempt);

export interface LiveEvent { type?: string; topic?: string; ref?: string | null; patient_id?: string | null }

/** Parse one SSE message. Returns null for heartbeats and malformed data (a refetch is still safe, so callers treat null as "something changed"). */
export function parseLive(data: unknown, fallbackTopic = ""): LiveEvent | null {
  if (typeof data !== "string" || !data.trim()) return null;
  try {
    const j = JSON.parse(data) as LiveEvent;
    return j && typeof j === "object" ? { ...j, topic: j.topic ?? fallbackTopic } : null;
  } catch {
    return null;
  }
}

/**
 * Live updates: SSE on GET /stream (event name = topic). Every event triggers an immediate (debounced) refetch.
 * Polling stays as a fallback: 5 s without SSE, 30 s while connected. Reconnects with exponential backoff.
 */
export function startLive(onEvent: (e: LiveEvent | null) => void, enabled: () => boolean = () => sessionState.signedIn === true): () => void {
  let es: EventSource | null = null;
  let poll: ReturnType<typeof setTimeout> | null = null;
  let retry: ReturnType<typeof setTimeout> | null = null;
  let debounce: ReturnType<typeof setTimeout> | null = null;
  let attempt = 0;
  let connected = false;
  let stopped = false;

  const fire = (e: LiveEvent | null) => {
    if (debounce) clearTimeout(debounce);
    debounce = setTimeout(() => onEvent(e), 150);
  };
  const schedulePoll = () => {
    if (stopped) return;
    if (poll) clearTimeout(poll);
    poll = setTimeout(() => {
      if (enabled() && (typeof document === "undefined" || document.visibilityState === "visible")) onEvent(null);
      schedulePoll();
    }, connected ? POLL_UP_MS : POLL_DOWN_MS);
  };
  const setConnected = (v: boolean) => {
    connected = v;
    status.setLive(v);
    schedulePoll(); // re-arm with the interval that matches the new state
  };
  const open = () => {
    if (stopped || typeof EventSource === "undefined" || !enabled()) return; // logged out: no /stream, no 401 storm
    const src = new EventSource(`${API_BASE}/stream?topics=${SSE_TOPICS.join(",")}`, { withCredentials: true });
    es = src;
    src.onopen = () => {
      attempt = 0;
      setConnected(true);
    };
    src.onmessage = (m) => fire(parseLive((m as MessageEvent).data));
    for (const t of SSE_TOPICS) src.addEventListener(t, (m) => fire(parseLive((m as MessageEvent).data, t)));
    src.onerror = () => {
      src.close();
      es = null;
      setConnected(false);
      if (!stopped && !retry)
        retry = setTimeout(() => {
          retry = null;
          open();
        }, backoffMs(attempt++));
    };
  };
  const onSession = () => {
    // signed in or out: reconnect now instead of waiting for the backoff timer
    if (retry) clearTimeout(retry);
    retry = null;
    es?.close();
    es = null;
    attempt = 0;
    setConnected(false);
    open();
  };
  if (typeof window !== "undefined") {
    window.addEventListener("cm-session", onSession);
    window.addEventListener("cm-session-up", onSession); // /auth/me just answered 200: start now
  }
  schedulePoll();
  open();
  return () => {
    stopped = true;
    if (typeof window !== "undefined") {
      window.removeEventListener("cm-session", onSession);
      window.removeEventListener("cm-session-up", onSession);
    }
    es?.close();
    es = null;
    if (poll) clearTimeout(poll);
    if (retry) clearTimeout(retry);
    if (debounce) clearTimeout(debounce);
    status.setLive(false);
  };
}
