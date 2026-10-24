import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useCare } from "../api/CareProvider";
import { USE_MOCK } from "../api";
import { dueAtOf, findEvidence, fmtLeft, slaClass } from "../api/derive";

/** Re-renders every `ms` so countdowns stay live. */
export function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const i = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(i);
  }, [ms]);
  return now;
}

/** Live SLA countdown. Colour is never the only signal: the words say left or overdue. */
export function Sla({ due }: { due: number }) {
  const now = useNow();
  const left = due - now;
  const k = slaClass(left);
  return <span className={`sla ${k}`} aria-label={`Review time: ${fmtLeft(left)}`}>{k === "late" ? "⚠ " : "⏱ "}{fmtLeft(left)}</span>;
}
export function SlaOf({ item }: { item: { dueMin?: number; createdAt?: number } }) {
  const { state } = useCare();
  return state ? <Sla due={dueAtOf(state, item)} /> : null;
}

// ---------- evidence drawer ----------
const EvCtx = createContext<(id: string) => void>(() => {});
export const useEvidence = () => useContext(EvCtx);

/** A citation chip (E-, B-, C-, R-). Opens the evidence drawer. */
export function EvChip({ id }: { id: string }) {
  const open = useEvidence();
  return <button type="button" className="ev" onClick={() => open(id)} aria-label={`Open evidence ${id}`}>{id}</button>;
}
export function EvChips({ ids }: { ids?: string[] }) {
  if (!ids?.length) return null;
  return <span className="evs">{ids.map((i) => <EvChip key={i} id={i} />)}</span>;
}

const KIND: Record<string, string> = { E: "Event", B: "Belief", C: "Conflict", R: "Risk", G: "Guideline", D: "Document" };

function Drawer({ id, onClose }: { id: string; onClose: () => void }) {
  const { state } = useCare();
  const ev = state ? findEvidence(state, id) : undefined;
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="scrim" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`Evidence ${id}`} onClick={(e) => e.stopPropagation()}>
        <div className="grab" aria-hidden="true" />
        <div className="dh">
          <span className="ev big">{id}</span>
          <span className="tag t-blu">{KIND[id[0]] ?? "Source"}</span>
          <button ref={ref} type="button" className="x" onClick={onClose} aria-label="Close evidence">Close ✕</button>
        </div>
        {!ev ? (
          <div className="empty"><b>Source not found</b>This record is not in the sample data.</div>
        ) : (
          <>
            <p className="evt">{ev.text}</p>
            <div className="kv">
              <div><span>Patient</span><b><Link to={`/doctor/patients/${ev.code}`} onClick={onClose}>{ev.code}</Link></b></div>
              <div><span>When</span><b>{ev.at}</b></div>
              <div><span>Reported by</span><b>{ev.reporter}</b></div>
              <div><span>Type</span><b>{ev.kind}</b></div>
            </div>
            <div className="why"><span>Why it matters</span>{ev.why}</div>
          </>
        )}
      </aside>
    </div>
  );
}

// ---------- undo toast ----------
interface Toast { msg: string; undo?: () => void; key: number }
const ToastCtx = createContext<(msg: string, undo?: () => void) => void>(() => {});

const KEYS: [string, string][] = [["J", "Next item in the list"], ["K", "Previous item"], ["Enter", "Open the highlighted patient"], ["A", "Approve the highlighted draft"], ["E", "Edit the highlighted draft"], ["D", "Decline the highlighted draft"], ["?", "Show or hide this help"], ["Esc", "Close a panel"]];

export function DoctorKit({ children }: { children: ReactNode }) {
  const [ev, setEv] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [help, setHelp] = useState(false);
  const timer = useRef<number>();
  const notify = useCallback((msg: string, undo?: () => void) => {
    window.clearTimeout(timer.current);
    setToast({ msg, undo, key: Date.now() });
    timer.current = window.setTimeout(() => setToast(null), 10000);
  }, []);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const toggleHelp = useCallback(() => setHelp((h) => !h), []);
  const closeHelp = useCallback(() => setHelp(false), []);
  useShortcuts(toggleHelp, closeHelp);
  const open = useCallback((id: string) => setEv(id), []);
  return (
    <EvCtx.Provider value={open}>
      <ToastCtx.Provider value={notify}>
        {children}
        {ev && <Drawer id={ev} onClose={() => setEv(null)} />}
        {toast && (
          <div className="toast" role="status" key={toast.key}>
            <span>{toast.msg}</span>
            {toast.undo && <button type="button" onClick={() => { toast.undo?.(); setToast(null); }}>Undo</button>}
            {toast.undo && <i className="bar10" aria-hidden="true" />}
          </div>
        )}
        {help && (
          <div className="scrim" onClick={closeHelp}>
            <div className="modal" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" onClick={(e) => e.stopPropagation()}>
              <h2>Keyboard shortcuts</h2>
              <dl>
                {KEYS.map(([k, d]) => (
                  <div key={k}><dt><kbd>{k}</kbd></dt><dd>{d}</dd></div>
                ))}
              </dl>
              <button type="button" className="btn ed" onClick={closeHelp}>Close</button>
            </div>
          </div>
        )}
      </ToastCtx.Provider>
    </EvCtx.Provider>
  );
}

/** Approve or decline with a 10 second Undo toast. */
export function useDecide() {
  const { state, dispatch } = useCare();
  const notify = useContext(ToastCtx);
  return useMemo(() => {
    const run = (ids: string[], code: string, d: "approved" | "declined", fire: () => void) => {
      fire();
      notify(`${d === "approved" ? "Approved and sent" : "Declined"}${ids.length > 1 ? ` ${ids.length} drafts` : ` for ${code}`}.`, USE_MOCK ? () => dispatch({ t: "undo", ids }) : undefined); // the server has no undo: no Undo button in live mode
    };
    return {
      request: (id: string, d: "approved" | "declined", text?: string) => {
        const code = state?.requests.find((r) => r.id === id)?.patientCode ?? "";
        run([id], code, d, () => dispatch({ t: "decideRequest", id, decision: d, text }));
      },
      approvals: (ids: string[], d: "approved" | "declined", text?: string) => {
        const code = state?.approvals.find((a) => a.id === ids[0])?.patientCode ?? "";
        run(ids, code, d, () => dispatch({ t: "decideApprovals", ids, decision: d, text }));
      },
    };
  }, [state, dispatch, notify]);
}

// ---------- keyboard: J/K move a highlight over [data-k] items; A/E/D press that card's buttons ----------
function useShortcuts(toggleHelp: () => void, closeHelp: () => void) {
  const idx = useRef(-1);
  useEffect(() => {
    const items = () => Array.from(document.querySelectorAll<HTMLElement>("[data-k]"));
    const mark = (n: number) => {
      const l = items();
      l.forEach((el) => el.classList.remove("kf"));
      if (!l.length) return;
      idx.current = Math.max(0, Math.min(l.length - 1, n));
      const el = l[idx.current];
      el.classList.add("kf");
      el.scrollIntoView({ block: "nearest" });
    };
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.ctrlKey || e.metaKey || e.altKey || /INPUT|TEXTAREA|SELECT/.test(t.tagName) || t.isContentEditable) return;
      const k = e.key.toLowerCase();
      if (!document.querySelector(".kf")) idx.current = -1;
      const cur = items()[idx.current];
      if (k === "?") { e.preventDefault(); toggleHelp(); }
      else if (k === "escape") closeHelp();
      else if (k === "j") mark(idx.current + 1);
      else if (k === "k") mark(idx.current - 1);
      else if (k === "enter" && cur && cur.tagName === "A" && t === document.body) (cur as HTMLAnchorElement).click();
      else if (cur && ["a", "e", "d"].includes(k)) cur.querySelector<HTMLButtonElement>(k === "a" ? ".btn.ap" : k === "e" ? ".btn.ed" : ".btn.rj")?.click();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [toggleHelp, closeHelp]);
}
