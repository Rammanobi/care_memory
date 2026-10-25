// Shapes and date helpers shared by the patient and Supporter screens. No sample data lives here:
// the live paths import this file; sampleData.ts (mock mode only) imports it too.
import type { Consents } from "../../api/patientExtras";
import type { Key } from "../../components/i18n";

export const TOTAL_DAYS = 60;

export const dayDate = (daysAgo: number) => { const d = new Date(); d.setHours(12, 0, 0, 0); d.setDate(d.getDate() - daysAgo); return d; };
/** index 0..59 (59 = today) to Date */
export const idxDate = (i: number) => dayDate(TOTAL_DAYS - 1 - i);

/** The English words stored for "just now" requests; shown translated by whenText. */
export const JUST_NOW = "today, just now";
export const whenText = (w: string, t: (k: Key, v?: Record<string, string | number>) => string): string => {
  if (w === JUST_NOW) return t("whenNow");
  const m = /^today (\d{1,2}:\d{2})$/.exec(w);
  return m ? t("whenToday", { t: m[1] }) : w;
};

/** Missed-dose reasons. `en` is what the doctor receives; the patient sees `shown` in their language. */
export const REASONS: { chip: Key; shown: Key; en: string }[] = [
  { chip: "rForgot", shown: "mrForgot", en: "Forgot to take it" },
  { chip: "rUnwell", shown: "mrUnwell", en: "Felt unwell" },
  { chip: "rRanOut", shown: "mrRanOut", en: "Ran out of tablets" },
  { chip: "rTravel", shown: "mrTravel", en: "Travelling" },
];
/** A stored English reason in the patient's language (unknown text is returned as is). */
export const reasonText = (r: string, t: (k: Key) => string): string => { const h = REASONS.find((x) => x.en === r); return h ? t(h.shown) : r; };

/** The "Take today's medicine" line on Home: a missed dose is shown as missed, never as Done. */
export const doseLine = (today: "none" | "taken" | "missed", marked: boolean, t: (k: Key) => string): string =>
  today === "taken" ? `✓ ${t("done")}${marked ? " · " + t("marked") : ""}` : today === "missed" ? `✕ ${t("missedNext")}` : t("notTaken");

/** "7:00 pm" in the patient's language. Telugu uses a day-part word; the stored value stays "7:00 pm". */
export function fmtTime(s: string, lang: string): string {
  const m = /^(\d{1,2}):(\d{2}) (am|pm)$/i.exec(s.trim());
  if (!m || lang !== "te") return s;
  const h12 = Number(m[1]);
  const h24 = (h12 % 12) + (m[3].toLowerCase() === "pm" ? 12 : 0);
  const part = h24 < 12 ? "ఉదయం" : h24 < 16 ? "మధ్యాహ్నం" : h24 < 19 ? "సాయంత్రం" : "రాత్రి";
  return `${part} ${h12}:${m[2]}`;
}

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
  /** Mock only: the "Share with my Supporter" switch. Null in live mode (the server decides what the Supporter sees). */
  shareSupporter: { on: boolean; set: (on: boolean) => void } | null;
  setConsent: (k: keyof Consents, v: boolean) => void;
  reminder: { current: string | null; pending: string | null; ask: (time: string) => void };
  supporterMarked: boolean;
  clearMark: () => void; // forget "marked by supporter" before the patient taps Took it
  markBySupporter: () => void; // mock only: remember that the Supporter tapped it
  canUndo: boolean;
  showMedicines: boolean;
  medicines: { id: string; label: string; when: string; note: string | null }[] | null; // null = mock mode (sample list)
  documents: { id: string; title: string; kind: string; date: string; summary: string; status?: string }[] | null;
  /** Clinic phone: only known in mock mode. Live: no number is shown. */
  clinicPhone: string | null;
  /** Supporter screen */
  sup: { patientName: string; supporterName: string; relation: string | null; allowed: boolean; week: (today: "none" | "taken" | "missed") => string[]; messages: Msg[] };
}
