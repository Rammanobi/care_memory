// Live notification for a new patient question: toast (urgent ones stay until opened), unread count, tab title, optional sound.
import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useCare } from "../api/CareProvider";
import { USE_MOCK } from "../api";
import { emptyNotify, notifyReducer, parseQuestionEvent, titleWithCount, unreadCount, type Notice } from "../api/notify";
import { CATEGORY_LABEL, PRIORITY_LABEL } from "../api/questions";
import { emitLiveEvent, onLiveEvent } from "../realtime/sse";

interface Ctx { unread: number; open: (id: string) => void; pageSeen: () => void }
const NotifyCtx = createContext<Ctx>({ unread: 0, open: () => {}, pageSeen: () => {} });
export const useQuestionNotify = () => useContext(NotifyCtx);

const SOUND_KEY = "cm_q_sound";
export const soundOn = () => { try { return localStorage.getItem(SOUND_KEY) === "1"; } catch { return false; } };
export const setSoundOn = (v: boolean) => { try { localStorage.setItem(SOUND_KEY, v ? "1" : "0"); } catch { /* ignore */ } };
function beep() {
  try {
    const A = window.AudioContext;
    if (!A) return;
    const c = new A(), o = c.createOscillator(), g = c.createGain();
    o.frequency.value = 660; g.gain.value = 0.06; o.connect(g); g.connect(c.destination);
    o.start(); o.stop(c.currentTime + 0.18); o.onended = () => void c.close();
  } catch { /* sound is optional */ }
}

const TOAST_MS = 12000;

function Toast({ n, onOpen, onClose }: { n: Notice; onOpen: () => void; onClose: () => void }) {
  const urgent = n.priority === "urgent";
  useEffect(() => {
    if (urgent) return;
    const t = window.setTimeout(onClose, TOAST_MS);
    return () => window.clearTimeout(t);
  }, [urgent, onClose]);
  return (
    <div className={`qtoast ${urgent ? "urgent" : n.priority === "high" ? "high" : ""}`} role={urgent ? "alert" : "status"}>
      <div className="qt-main">
        <b>New patient question{n.patientCode ? ` · ${n.patientCode}` : ""}</b>
        <span className="qt-chips">
          <span className="qchip">{CATEGORY_LABEL[n.category]}</span>
          <span className={`qchip pr-${n.priority}`}>{urgent ? "⚠ " : ""}{PRIORITY_LABEL[n.priority]}</span>
        </span>
      </div>
      <button type="button" className="qt-open" onClick={onOpen}>Open</button>
      {!urgent && <button type="button" className="qt-x" onClick={onClose} aria-label="Dismiss notification">✕</button>}
    </div>
  );
}

export function QuestionNotify({ children }: { children: ReactNode }) {
  const [s, dispatch] = useReducer(notifyReducer, emptyNotify);
  const nav = useNavigate();
  const { state } = useCare();
  const seen = useRef(new Set<string>());
  const base = useRef(typeof document !== "undefined" ? document.title : "");

  useEffect(() => onLiveEvent((ev) => {
    const q = parseQuestionEvent(ev);
    if (q && !seen.current.has(q.id)) { seen.current.add(q.id); if (soundOn()) beep(); }
    dispatch({ t: "event", ev, at: Date.now() });
  }), []);

  // mock mode has no server stream: ?notify shows one sample urgent notification so the UI can be demoed offline
  useEffect(() => {
    if (!USE_MOCK || !location.search.includes("notify")) return;
    const t = window.setTimeout(() => emitLiveEvent({ topic: "review", kind: "patient_question", approval_id: "rq-q3", patient_code: "PT-0254", category: "symptom", priority: "urgent" }), 1500);
    return () => window.clearTimeout(t);
  }, []);

  // a question someone already answered needs no more attention
  const answered = useMemo(() => (state?.requests ?? []).filter((r) => r.status !== "waiting").map((r) => r.id), [state?.requests]);
  useEffect(() => {
    const ids = answered.filter((id) => s.notices.some((n) => n.id === id && !n.read));
    if (ids.length) dispatch({ t: "resolved", ids });
  }, [answered, s.notices]);

  const unread = unreadCount(s);
  useEffect(() => {
    document.title = titleWithCount(base.current, unread);
  }, [unread]);
  useEffect(() => () => { document.title = base.current; }, []);

  const open = useCallback((id: string) => dispatch({ t: "open", id }), []);
  const pageSeen = useCallback(() => dispatch({ t: "pageSeen" }), []);
  const value = useMemo(() => ({ unread, open, pageSeen }), [unread, open, pageSeen]);
  const toasts = s.notices.filter((n) => n.toast).slice(0, 4);

  return (
    <NotifyCtx.Provider value={value}>
      {children}
      {toasts.length > 0 && (
        <div className="qtoasts" aria-label="New patient questions">
          {toasts.map((n) => (
            <Toast key={n.id} n={n} onClose={() => dispatch({ t: "hide", id: n.id })} onOpen={() => { dispatch({ t: "open", id: n.id }); nav(`/doctor/requests?focus=${encodeURIComponent(n.id)}`); }} />
          ))}
        </div>
      )}
    </NotifyCtx.Provider>
  );
}
