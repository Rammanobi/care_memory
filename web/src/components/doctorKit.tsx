import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useCare } from "../api/CareProvider";
import { USE_MOCK } from "../api";
import { dueAtOf, findEvidence, fmtLeft, slaClass } from "../api/derive";
import { type CiteSnippet } from "../api/citations";

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
const EvCtx = createContext<(id: string, snippet?: CiteSnippet) => void>(() => {});
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
const SNIPPET_KIND: Record<string, string> = { event: "Event", daily: "Daily summary", weekly: "Weekly summary", document: "Document" };
/** The kind shown in the drawer. A snippet's own kind wins; the id letter is only a fallback when no snippet is given. */
export function evidenceKind(id: string, snippet?: { kind?: string }): string {
  if (snippet) return SNIPPET_KIND[(snippet.kind ?? "").toLowerCase()] ?? KIND[id[0]] ?? "Record";
  return KIND[id[0]] ?? "Source";
}

const FOCUSABLE = 'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

function Drawer({ id, snippet, onClose }: { id: string; snippet?: CiteSnippet; onClose: (restoreFocus?: boolean) => void }) {
  const { state } = useCare();
  const ev = state ? findEvidence(state, id) : undefined;
  const ref = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key !== "Tab" || !box.current) return;
      const f = Array.from(box.current.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (!f.length) { e.preventDefault(); return; }
      const first = f[0], last = f[f.length - 1], at = document.activeElement;
      if (!box.current.contains(at)) { e.preventDefault(); first.focus(); }
      else if (e.shiftKey && at === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && at === last) { e.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const kind = evidenceKind(id, snippet);
  return (
    <div className="scrim" onClick={() => onClose()}>
      <aside ref={box} className="drawer" role="dialog" aria-modal="true" aria-label={`Evidence ${id}`} onClick={(e) => e.stopPropagation()}>
        <div className="grab" aria-hidden="true" />
        <div className="dh">
          <span className="ev big">{id}</span>
          <span className="tag t-blu">{kind}</span>
          <button ref={ref} type="button" className="x" onClick={() => onClose()} aria-label="Close evidence">Close ✕</button>
        </div>
        {snippet ? (
          <>
            <p className="evt">{snippet.snippet}</p>
            <div className="kv">
              <div><span>Date</span><b>{snippet.date}</b></div>
              <div><span>Type</span><b>{kind}</b></div>
            </div>
          </>
        ) : !ev ? (
          <div className="empty"><b>Source not found</b>This record is not in the sample data.</div>
        ) : (
          <>
            <p className="evt">{ev.text}</p>
            <div className="kv">
              <div><span>Patient</span><b><Link to={`/doctor/patients/${ev.code}`} onClick={() => onClose(false)}>{ev.code}</Link></b></div>
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

type Key = [key: string, desc: string, pages?: string[]];
const LISTS = ["/doctor", "/doctor/today", "/doctor/approvals", "/doctor/requests"];
const DRAFTS = ["/doctor/approvals", "/doctor/requests"];
const KEYS: Key[] = [
  ["J", "Next item in the list", LISTS], ["K", "Previous item", LISTS],
  ["Enter", "Open the highlighted patient", ["/doctor", "/doctor/today"]],
  ["A", "Approve the highlighted draft (not patient questions or documents)", DRAFTS],
  ["E", "Edit the highlighted draft, or go to the reply box", DRAFTS],
  ["D", "Decline the highlighted draft (not patient questions or documents)", DRAFTS],
  ["Ctrl+Enter", "Send from the reply box", ["/doctor/requests"]],
  ["?", "Show or hide this help"], ["Esc", "Close a panel"],
];
/** Shortcuts that apply on the current page (patient routes count as the Patients list group). */
export function keysFor(path: string): Key[] {
  const p = path.replace(/\/+$/, "") || "/";
  const page = p.startsWith("/doctor/patients") ? "/doctor" : p;
  return KEYS.filter((k) => !k[2] || k[2].includes(page));
}

/** A and D approve or decline at once. Question and document cards have no Undo, so A/D are ignored on them; only draft cards (with Undo) react. */
export function shortcutAllowed(key: string, card: { closest: (sel: string) => unknown } | null | undefined): boolean {
  if (!card) return false;
  if ((key === "a" || key === "d") && card.closest(".qcard")) return false;
  return true;
}

export function DoctorKit({ children }: { children: ReactNode }) {
  const [ev, setEv] = useState<{ id: string; snippet?: CiteSnippet } | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [help, setHelp] = useState(false);
  const opener = useRef<HTMLElement | null>(null);
  const helpOpener = useRef<HTMLElement | null>(null);
  const helpClose = useRef<HTMLButtonElement>(null);
  const helpOn = useRef(false);
  const loc = useLocation();
  const timer = useRef<number>();
  const notify = useCallback((msg: string, undo?: () => void) => {
    window.clearTimeout(timer.current);
    setToast({ msg, undo, key: Date.now() });
    timer.current = window.setTimeout(() => setToast(null), 10000);
  }, []);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const closeHelp = useCallback(() => {
    if (!helpOn.current) return;
    helpOn.current = false;
    setHelp(false);
    const el = helpOpener.current;
    helpOpener.current = null;
    window.setTimeout(() => { if (el?.isConnected) el.focus(); }, 0);
  }, []);
  const toggleHelp = useCallback(() => {
    if (helpOn.current) { closeHelp(); return; }
    helpOpener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    helpOn.current = true;
    setHelp(true);
  }, [closeHelp]);
  useShortcuts(toggleHelp, closeHelp, helpOn);
  useEffect(() => {
    window.addEventListener("cm-help", toggleHelp);
    return () => window.removeEventListener("cm-help", toggleHelp);
  }, [toggleHelp]);
  useEffect(() => { if (help) helpClose.current?.focus(); }, [help]);
  const open = useCallback((id: string, snippet?: CiteSnippet) => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setEv({ id, snippet });
  }, []);
  const closeEv = useCallback((restore = true) => {
    setEv(null);
    const el = opener.current;
    opener.current = null;
    if (restore) window.setTimeout(() => { if (el?.isConnected) el.focus(); }, 0);
  }, []);
  return (
    <EvCtx.Provider value={open}>
      <ToastCtx.Provider value={notify}>
        {children}
        {ev && <Drawer id={ev.id} snippet={ev.snippet} onClose={closeEv} />}
        {toast && (
          <div className="toast" role="status" key={toast.key}>
            <span>{toast.msg}</span>
            {toast.undo && <button type="button" onClick={() => { toast.undo?.(); setToast(null); }}>Undo</button>}
            {toast.undo && <i className="bar10" aria-hidden="true" />}
          </div>
        )}
        {help && (
          <div className="scrim" onClick={closeHelp}>
            <div className="modal" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => { if (e.key === "Tab") { e.preventDefault(); helpClose.current?.focus(); } }}>
              <h2>Keyboard shortcuts</h2>
              <dl>
                {keysFor(loc.pathname).map(([k, d]) => (
                  <div key={k}><dt><kbd>{k}</kbd></dt><dd>{d}</dd></div>
                ))}
              </dl>
              <button ref={helpClose} type="button" className="btn ed" onClick={closeHelp}>Close</button>
            </div>
          </div>
        )}
      </ToastCtx.Provider>
    </EvCtx.Provider>
  );
}

/** Approve or decline with a 10 second Undo toast. Resolves after the server accepted; rejects with the server's refusal (nothing was sent then). */
export function useDecide() {
  const { state, dispatchAsync, dispatch } = useCare();
  const notify = useContext(ToastCtx);
  return useMemo(() => {
    const run = async (ids: string[], code: string, d: "approved" | "declined", fire: () => Promise<void>) => {
      await fire();
      notify(`${d === "approved" ? "Approved and sent" : "Declined"}${ids.length > 1 ? ` ${ids.length} drafts` : ` for ${code}`}.`, USE_MOCK ? () => dispatch({ t: "undo", ids }) : undefined); // the server has no undo: no Undo button in live mode
    };
    return {
      request: (id: string, d: "approved" | "declined", text?: string) => {
        const code = state?.requests.find((r) => r.id === id)?.patientCode ?? "";
        return run([id], code, d, () => dispatchAsync({ t: "decideRequest", id, decision: d, text }));
      },
      approvals: (ids: string[], d: "approved" | "declined", text?: string) => {
        const code = state?.approvals.find((a) => a.id === ids[0])?.patientCode ?? "";
        return run(ids, code, d, () => dispatchAsync({ t: "decideApprovals", ids, decision: d, text }));
      },
    };
  }, [state, dispatchAsync, dispatch, notify]);
}

// ---------- keyboard: J/K move a highlight over [data-k] items; A/E/D press that card's buttons ----------
function useShortcuts(toggleHelp: () => void, closeHelp: () => void, helpOn: { current: boolean }) {
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
      else if (helpOn.current) return; // help is open: J/K/A/E/D/Enter must not act on the page behind it
      else if (k === "j") mark(idx.current + 1);
      else if (k === "k") mark(idx.current - 1);
      else if (k === "enter" && cur && cur.tagName === "A" && t === document.body) (cur as HTMLAnchorElement).click();
      else if (cur && ["a", "e", "d"].includes(k) && shortcutAllowed(k, cur)) cur.querySelector<HTMLButtonElement>(k === "a" ? ".btn.ap" : k === "e" ? ".btn.ed" : ".btn.rj")?.click();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [toggleHelp, closeHelp]);
}
