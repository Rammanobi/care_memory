import type { CareState, Level, Patient } from "./types";

export interface Row {
  p: Patient;
  level: Level;
  tag: string;
  tagClass: string;
  next: string;
  needsMe: boolean;
  hasRequest: boolean;
}

const TAG_CLASS: Record<Level, string> = { red: "t-red", amb: "t-amb", grn: "t-grn", blu: "t-blu" };

/** Items that decide a patient's row (routine green approvals do not). */
function related(s: CareState, code: string) {
  return {
    reqs: s.requests.filter((r) => r.patientCode === code && !r.archived),
    aps: s.approvals.filter((a) => a.patientCode === code && a.lane !== "green"),
  };
}

export function buildRow(p: Patient, s: CareState): Row {
  const { reqs, aps } = related(s, p.code);
  const all = [...reqs, ...aps];
  const pending = all.filter((x) => x.status === "waiting");
  const hasRequest = reqs.some((r) => r.status === "waiting");
  const needsMe = pending.length > 0;
  let level: Level = p.base;
  let tag = p.tag;
  let next = p.nextStep;
  if (needsMe && p.base === "grn") {
    level = "blu";
    tag = "ASKED";
  } else if (!needsMe && p.base !== "grn" && all.length > 0) {
    level = "grn";
    tag = "HANDLED";
  }
  if (!needsMe && all.length > 0) {
    const last = all[all.length - 1];
    next = all.some((x) => x.status === "approved") ? "Approved and sent" : last.status === "declined" ? "Declined" : next;
  }
  return { p, level, tag, tagClass: TAG_CLASS[level], next, needsMe, hasRequest };
}

export type FilterKey = "all" | "needs" | "requests" | "quiet" | "visit";

export function buildRows(s: CareState) {
  return s.patients.map((p) => buildRow(p, s));
}

export function matches(r: Row, f: FilterKey) {
  switch (f) {
    case "needs": return r.needsMe;
    case "requests": return r.hasRequest;
    case "quiet": return r.p.quiet;
    case "visit": return r.p.visitThisWeek;
    default: return true;
  }
}

export function counts(s: CareState) {
  const rows = buildRows(s);
  const c = (f: FilterKey) => rows.filter((r) => matches(r, f)).length;
  return {
    rows,
    all: rows.length,
    needs: c("needs"),
    requests: c("requests"),
    quiet: c("quiet"),
    visit: c("visit"),
    red: rows.filter((r) => r.level === "red").length,
    track: rows.filter((r) => r.level === "grn").length,
    pendingRequests: s.requests.filter((r) => r.status === "waiting").length,
    pendingApprovals: s.approvals.filter((a) => a.status === "waiting").length,
  };
}

/** One source for "quiet for N days": Patient.noData. */
export const quietDays = (p: Pick<Patient, "noData">) => `${p.noData} ${p.noData === 1 ? "day" : "days"}`;

export function missedLabel(p: Patient) {
  return p.noData > 0 ? `no data for ${quietDays(p)}` : `${p.missed.length} missed of last 20`;
}

/** The real weekday name, for the Today subtitle. */
export const weekdayName = (d: Date = new Date()) => d.toLocaleDateString("en-GB", { weekday: "long" });

/** Display label for a request kind (raw values: "Question", "dose", "Reminder time" ...). */
const KIND_LABELS: Record<string, string> = {
  question: "Patient question", dose: "Dose question", document: "Document to check", "reminder time": "Reminder time change",
  "change visit": "Visit change", visit: "Visit question", other: "Patient request",
};
export function requestLabel(kind: string) {
  const k = kind.trim().toLowerCase();
  return KIND_LABELS[k] ?? (kind ? kind.charAt(0).toUpperCase() + kind.slice(1) : "Patient request");
}

/** A belief confidence as plain words: "High confidence", "Seen once", "Not known yet". */
export function confText(conf: string) {
  const k = conf.trim().toLowerCase();
  if (k === "high" || k === "medium" || k === "low") return `${k.charAt(0).toUpperCase()}${k.slice(1)} confidence`;
  if (k === "seen once") return "Seen once";
  if (k === "unknown" || k === "") return "Not known yet";
  return conf.charAt(0).toUpperCase() + conf.slice(1);
}

/** Position of a time label on the simulated day line. Accepts "Day 59 · 18:30", "today 07:58", "yesterday 12:20", "2 days ago 10:30", "last week 09:00". `today` is the day that "today" means. */
export function atStamp(at: string, today = 60): { day: number; min: number } {
  const t = at.match(/(\d{1,2}):(\d{2})/);
  const min = t ? Number(t[1]) * 60 + Number(t[2]) : 0;
  const d = at.match(/(?:^|[^a-z])day\s+(\d+)/i);
  let day = today;
  if (d) day = Number(d[1]);
  else if (/yesterday/i.test(at)) day = today - 1;
  else if (/(\d+)\s+days?\s+ago/i.test(at)) day = today - Number(at.match(/(\d+)\s+days?\s+ago/i)![1]);
  else if (/last week/i.test(at)) day = today - 7;
  return { day, min };
}
/** One display format for every time: "Day 59 · 18:30". */
export function fmtAt(at: string, today = 60) {
  const { day, min } = atStamp(at, today);
  return /\d{1,2}:\d{2}/.test(at) ? `Day ${day} · ${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}` : `Day ${day}`;
}
/** Newest first by day, then time. Stable for equal stamps. */
export function newestFirst<T>(rows: T[], at: (r: T) => string, today = 60): T[] {
  return rows.map((r, i) => ({ r, i, k: atStamp(at(r), today) }))
    .sort((a, b) => b.k.day - a.k.day || b.k.min - a.k.min || a.i - b.i)
    .map((x) => x.r);
}

/** Privacy suppression: a count of 1 to threshold-1 is hidden (null). Zero stays zero. */
export const suppress = (n: number, threshold = 5): number | null => (n > 0 && n < threshold ? null : n);

export function stripCells(p: Patient): string[] {
  return Array.from({ length: 20 }, (_, i) => (i >= 20 - p.noData ? "l" : p.missed.includes(i) ? "m" : ""));
}

// ---- doctor-side helpers ----
import type { Approval, Evidence, PatientRequest } from "./types";

export const dueAtOf = (s: CareState, x: { dueMin?: number; createdAt?: number }) => (x.createdAt && x.dueMin === undefined ? x.createdAt + 4 * 3600000 : s.seededAt + (x.dueMin ?? 240) * 60000);

/** "1h 42m", "12m 05s", or "overdue 5m". */
export function fmtLeft(ms: number) {
  const over = ms < 0;
  const t = Math.abs(Math.round(ms / 1000));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), sec = t % 60;
  const body = h > 0 ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m ${String(sec).padStart(2, "0")}s`;
  return over ? `overdue ${body}` : `${body} left`;
}
export const slaClass = (ms: number) => (ms < 0 ? "late" : ms < 3600000 ? "soon" : "ok");

export const findEvidence = (s: CareState, id: string): Evidence | undefined => s.evidence.find((e) => e.id === id);
export const clinicName = (s: CareState, id: string) => s.clinics.find((c) => c.id === id)?.name ?? id;
export const treatmentDay = (s: CareState, p: Patient) => p.day + (s.simDay - 60);

export function waitingApprovals(s: CareState): Approval[] {
  return s.approvals.filter((a) => a.status === "waiting");
}
export function waitingRequests(s: CareState): PatientRequest[] {
  return s.requests.filter((r) => r.status === "waiting" && !r.archived);
}

/** Adherence for a patient = share of the last 20 days that were not missed (days with no data count as missed). */
export const adherencePct = (p: Patient) => Math.round(((20 - p.missed.length - p.noData) / 20) * 100);

export function clinicStats(s: CareState) {
  return s.clinics.map((c) => {
    const ps = s.patients.filter((p) => p.clinic === c.id);
    const codes = ps.map((p) => p.code);
    const adherence = ps.length ? Math.round(ps.reduce((a, p) => a + adherencePct(p), 0) / ps.length) : 0;
    return {
      ...c,
      patients: ps.length,
      adherence,
      quiet: ps.filter((p) => p.quiet).length,
      pending: s.approvals.filter((a) => a.status === "waiting" && codes.includes(a.patientCode)).length + s.requests.filter((r) => r.status === "waiting" && !r.archived && codes.includes(r.patientCode)).length,
    };
  });
}
