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

export function missedLabel(p: Patient) {
  return p.noData > 0 ? "no data since Mon" : `${p.missed.length} missed of last 20`;
}

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
