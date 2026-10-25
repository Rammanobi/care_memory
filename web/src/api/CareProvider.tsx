import { createContext, useCallback, useContext, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { api } from "./index";
import { applyAction } from "./reducer";
import { status } from "./status";
import type { Action, CareState } from "./types";

interface Ctx {
  state: CareState | null; // null while loading
  dispatch: (a: Action) => void;
  /** Like dispatch but no optimistic change and no generic toast: resolves when the server accepted, rejects with the server's error. */
  dispatchAsync: (a: Action) => Promise<void>;
  reset: () => void;
  loadDetail: (id: string) => void;
}

const CareCtx = createContext<Ctx | null>(null);

function Banner({ onRetry, loadErrors }: { onRetry: () => void; loadErrors?: string[] }) {
  const s = useSyncExternalStore(status.subscribe, status.get);
  useEffect(() => {
    if (!s.toast) return;
    const t = setTimeout(() => status.toast(null), 6000);
    return () => clearTimeout(t);
  }, [s.toast]);
  return (
    <>
      {s.offline && (
        <div role="alert" style={{ position: "sticky", top: 0, zIndex: 50, background: "#b3261e", color: "#fff", padding: "10px 16px", display: "flex", gap: 12, alignItems: "center" }}>
          <span>Cannot reach the server. Showing the last data we have.</span>
          <button onClick={onRetry} style={{ minHeight: 36, padding: "0 14px", borderRadius: 8, border: "1px solid #fff", background: "transparent", color: "#fff" }}>Retry</button>
        </div>
      )}
      {!!loadErrors?.length && (
        <div role="status" style={{ background: "#fff4d6", color: "#5c3d00", padding: "8px 16px", fontSize: 14 }}>
          Could not load: {loadErrors.join(", ")}. Those parts stay empty until the server answers.
        </div>
      )}
      {s.bulk && (
        <div className="dlg-back" onClick={() => status.bulk(null)}>
          <div className="dlg" role="alertdialog" aria-labelledby="bulk-t" onClick={(e) => e.stopPropagation()}>
            <h3 id="bulk-t">{s.bulk.total - s.bulk.failures.length} of {s.bulk.total} approved</h3>
            <p className="sm">These were not approved:</p>
            <ul style={{ margin: "8px 0 14px 18px" }}>
              {s.bulk.failures.map((f) => <li key={f.id}><b>{f.code || f.id.slice(0, 8)}</b>: {f.message}</li>)}
            </ul>
            <button type="button" className="btn ap" autoFocus onClick={() => status.bulk(null)}>OK</button>
          </div>
        </div>
      )}
      {s.toast && (
        <div role="status" style={{ position: "fixed", left: 16, right: 16, bottom: 72, zIndex: 60, background: "#1f2937", color: "#fff", padding: "12px 16px", borderRadius: 10, maxWidth: 520, margin: "0 auto" }}>
          {s.toast}
        </div>
      )}
    </>
  );
}

export function sameState(a: CareState | null, b: CareState | null): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  try { return JSON.stringify(a) === JSON.stringify(b); } catch { return false; }
}

export function CareProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<CareState | null>(null);

  const refetch = useCallback(() => api.load().then(setState).catch(() => undefined), []); // offline flag is set by the http layer

  useEffect(() => {
    let alive = true;
    // Polling re-pulls every 5 s: keep the previous state object when nothing changed so React does not re-render (no flicker).
    const pull = () => api.load().then((s) => alive && setState((prev) => (sameState(prev, s) ? prev : s))).catch(() => undefined);
    pull();
    const off = api.subscribe(pull);
    window.addEventListener("cm-session", pull);
    return () => {
      alive = false;
      off();
      window.removeEventListener("cm-session", pull);
    };
  }, []);

  const dispatch = useCallback((a: Action) => {
    setState((s) => (s ? applyAction(s, a) : s)); // optimistic
    api.dispatch(a).then(setState).catch((e: unknown) => {
      status.toast(`Could not save that change: ${e instanceof Error ? e.message : "unknown error"}. It was rolled back.`);
      api.load().then(setState).catch(() => undefined); // roll back to server truth
    });
  }, []);

  const dispatchAsync = useCallback(async (a: Action) => {
    setState(await api.dispatch(a));
  }, []);

  const reset = useCallback(() => {
    api.reset().then(setState).catch(() => undefined);
  }, []);

  const loadDetail = useCallback((id: string) => {
    api.loadDetail?.(id).then(setState).catch(() => undefined);
  }, []);

  const value = useMemo(() => ({ state, dispatch, dispatchAsync, reset, loadDetail }), [state, dispatch, dispatchAsync, reset, loadDetail]);
  return (
    <CareCtx.Provider value={value}>
      <Banner onRetry={refetch} loadErrors={state?.loadErrors} />
      {children}
    </CareCtx.Provider>
  );
}

export function useCare() {
  const c = useContext(CareCtx);
  if (!c) throw new Error("useCare outside CareProvider");
  return c;
}
