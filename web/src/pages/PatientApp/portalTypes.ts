// Shapes and date helpers shared by the patient and Supporter screens. No sample data lives here:
// the live paths import this file; sampleData.ts (mock mode only) imports it too.
import type { Consents } from "../../api/patientExtras";

export const TOTAL_DAYS = 60;

export const dayDate = (daysAgo: number) => { const d = new Date(); d.setHours(12, 0, 0, 0); d.setDate(d.getDate() - daysAgo); return d; };
/** index 0..59 (59 = today) to Date */
export const idxDate = (i: number) => dayDate(TOTAL_DAYS - 1 - i);

export interface Msg { id: string; daysAgo: number; title: string; text: string; forSupporter?: boolean; date?: Date; inReplyTo?: { excerpt: string } }
export interface Appt { id: string; kind: "visit" | "lab"; title: string; when: string; place: string; daysAgo?: number; note?: string }
export type ReqState = "waiting" | "approved" | "declined";
export interface PastReq { id: string; text: string; when: string; status: ReqState; reply?: string }

export interface PView {
  live: boolean;
  /** Mock demo switch "show empty states". Always false in live mode. */
  empty: boolean;
  name: string; code: string; clinic: string;
  /** Treatment day; 0 = unknown (never shown). */
  day: number;
  supporter: { name: string; relation: string | null } | null;
  history60: string; // oldest first; the last char is overridden by today's dose in the screens
  /** False when the server sent no record: the screens show "could not load", never a made-up calendar. */
  recordReady: boolean;
  reasonAt: (i: number) => string | undefined;
  dateAt: (i: number) => Date;
  streak: number; // already includes today when taken
  messages: Msg[];
  isRead: (id: string) => boolean;
  markRead: (id: string) => void;
  upcoming: Appt[];
  past: Appt[];
  /** Null = nothing scheduled (live) - the screens say so. */
  nextVisitText: string | null;
  pastRequests: PastReq[];
  consents: Consents;
  setConsent: (k: keyof Consents, v: boolean) => void;
  reminder: { current: string | null; pending: string | null; ask: (time: string) => void };
  supporterMarked: boolean;
  clearMark: () => void; // forget "marked by supporter" before the patient taps Took it
  markBySupporter: () => void; // mock only: remember that the Supporter tapped it
  canUndo: boolean;
  showMedicines: boolean;
  medicines: { id: string; label: string; when: string; note: string | null }[] | null; // null = mock mode (sample list)
  documents: { id: string; title: string; kind: string; date: string; summary: string }[] | null;
  /** Clinic phone: only known in mock mode. Live: no number is shown. */
  clinicPhone: string | null;
  /** Supporter screen */
  sup: { patientName: string; supporterName: string; relation: string | null; allowed: boolean; week: (today: "none" | "taken" | "missed") => string[]; messages: Msg[] };
}
