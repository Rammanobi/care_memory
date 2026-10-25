// Doctor notifications for patient questions: a pure reducer (dedupe, unread count, urgent stays until opened).
import { asCategory, asPriority } from "./questions";
import type { QCategory, QPriority } from "./types";

export interface Notice { kind: "question" | "document"; id: string; patientCode: string; category: QCategory; priority: QPriority; at: number; read: boolean; toast: boolean }
export interface NotifyState { notices: Notice[] }
export const emptyNotify: NotifyState = { notices: [] };
const MAX = 50;

/** The SSE 'review' event {kind:'patient_question', approval_id, patient_code, category, priority}. Anything else is not ours. */
export function parseQuestionEvent(ev: unknown): { id: string; patientCode: string; category: QCategory; priority: QPriority } | null {
  const e = ev as Record<string, unknown> | null;
  if (!e || e.kind !== "patient_question" || typeof e.approval_id !== "string" || !e.approval_id) return null;
  return { id: e.approval_id, patientCode: typeof e.patient_code === "string" ? e.patient_code : "", category: asCategory(e.category), priority: asPriority(e.priority) };
}

/** The SSE 'review' event {kind:'patient_document', approval_id, patient_code, category:'document', priority}. */
export function parseDocumentEvent(ev: unknown): { id: string; patientCode: string; category: QCategory; priority: QPriority } | null {
  const e = ev as Record<string, unknown> | null;
  if (!e || e.kind !== "patient_document" || typeof e.approval_id !== "string" || !e.approval_id) return null;
  return { id: e.approval_id, patientCode: typeof e.patient_code === "string" ? e.patient_code : "", category: "document", priority: asPriority(e.priority) };
}

/** Either kind of doctor notice. */
export function parseNoticeEvent(ev: unknown): (Omit<Notice, "at" | "read" | "toast">) | null {
  const q = parseQuestionEvent(ev);
  if (q) return { kind: "question", ...q };
  const d = parseDocumentEvent(ev);
  return d ? { kind: "document", ...d } : null;
}

export type NotifyAction =
  | { t: "event"; ev: unknown; at: number }
  | { t: "open"; id: string } // the doctor opened that question: read, toast gone
  | { t: "hide"; id: string } // toast timeout: urgent toasts ignore it
  | { t: "dismiss"; id: string } // the x button: urgent ignores it
  | { t: "pageSeen" } // Requests page shown: non-urgent are read, urgent wait until opened
  | { t: "resolved"; ids: string[] }; // answered elsewhere: nothing left to open

export function notifyReducer(s: NotifyState, a: NotifyAction): NotifyState {
  switch (a.t) {
    case "event": {
      const q = parseNoticeEvent(a.ev);
      if (!q) return s;
      const old = s.notices.find((n) => n.id === q.id);
      if (old) {
        // same question again (SSE reconnect): no second notice; a later "urgent" upgrade is honoured
        if (old.priority === "urgent" || q.priority !== "urgent" || old.read) return s;
        return { notices: s.notices.map((n) => (n.id === q.id ? { ...n, priority: "urgent", toast: true } : n)) };
      }
      const n: Notice = { ...q, at: a.at, read: false, toast: true };
      return { notices: [n, ...s.notices].slice(0, MAX) };
    }
    case "open":
      return { notices: s.notices.map((n) => (n.id === a.id ? { ...n, read: true, toast: false } : n)) };
    case "hide":
    case "dismiss":
      return { notices: s.notices.map((n) => (n.id === a.id && n.priority !== "urgent" ? { ...n, toast: false } : n)) };
    case "pageSeen":
      return { notices: s.notices.map((n) => (n.priority === "urgent" ? n : { ...n, read: true, toast: false })) };
    case "resolved":
      return { notices: s.notices.map((n) => (a.ids.includes(n.id) ? { ...n, read: true, toast: false } : n)) };
  }
}

export const unreadCount = (s: NotifyState) => s.notices.filter((n) => !n.read).length;
export const urgentOpen = (s: NotifyState) => s.notices.some((n) => n.priority === "urgent" && !n.read);
export const titleWithCount = (base: string, n: number) => (n > 0 ? `(${n}) ${base}` : base);
