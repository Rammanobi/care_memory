// Pure functions: backend wire shapes (cm/api/portal_models.py, cm/contracts) -> the UI shapes in types.ts.
import type { District, Approval, AuditEntry, Decision, Evidence, EvKind, LensSnap, Message, Patient, PatientRequest, PortalAppt, PortalMsg, PortalSlice, ServerSettings, Template, Usage } from "./types";
import { isAbstain, snippetsFrom, type CiteSnippet } from "./citations";

export interface WireReviewItem {
  approval_id: string;
  patient_token?: string | null;
  tier: "red" | "amber" | "green";
  title: string;
  status: "pending" | "approved" | "edited" | "rejected" | "expired" | "manual";
  drivers?: { label: string }[];
  due_at: string;
}
export interface WireReviewDetail extends WireReviewItem {
  proposal?: { body?: string };
  citations?: { ref?: string; id?: string }[];
}
export interface WireUiPatient {
  code: string; sex: "M" | "F"; age: number; day: number; base: "red" | "amb" | "grn"; tag: string; why: string;
  missed: number[]; no_data: number; next_step: string; clinic: string; visit_this_week: boolean; quiet: boolean;
  next_visit: string; supporter: "Linked" | "Not linked"; consent: string; changes: { text: string; ev: string }[]; person_id?: string;
}
export interface WireRequest {
  id: string; patient_code: string; kind: string; text: string; when: string; draft: string;
  status: Decision; reply?: string | null; due_at: string; refs?: string[]; archived?: boolean;
}
export interface WireMessage {
  id: string; src_id?: string | null; code: string; at: string; channel: string; text: string;
  approved_by: string; version: number; status: "sent" | "seen" | "pending"; delivery?: "queued" | "sent" | "failed"; delivery_error?: string | null;
}
export interface WireAudit { id: number; code?: string | null; at: string; actor: string; label: string; src_id?: string | null; version?: number | null; note?: string | null }
export interface WireTemplate { template_id: string; key: string; lang: string; body: string; status: string }
export interface WireUsage {
  mode: Usage["mode"]; today_spend: number; today_cap: number; budget_used: number; budget: number;
  days: { d: string; spend: number }[]; tasks: Usage["tasks"]; retries: number; breaker: number; billing: number; provider_pct: number;
}

/** Person token P-0142 and UI code PT-0142 are the same patient. */
export const toUiCode = (token?: string | null) => (token ?? "").replace(/^P-/, "PT-");
export const toApiToken = (code: string) => code.replace(/^PT-/, "P-");

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export function fmtWhen(iso: string, now = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return d.toDateString() === now.toDateString() ? `Today ${hm}` : `${DAYS[d.getDay()]} ${hm}`;
}

export function mapStatus(s: WireReviewItem["status"]): Decision {
  if (s === "approved" || s === "edited") return "approved";
  if (s === "rejected" || s === "expired") return "declined";
  return "waiting";
}

export function mapApproval(it: WireReviewItem, detail: WireReviewDetail | undefined, nowMs: number): Approval {
  const draft = detail?.proposal?.body ?? "";
  const status = mapStatus(it.status);
  return {
    id: it.approval_id,
    patientCode: toUiCode(it.patient_token),
    lane: it.tier,
    title: it.title,
    draft,
    status,
    dueMin: Math.round((Date.parse(it.due_at) - nowMs) / 60000),
    refs: (detail?.citations ?? []).map((c) => c.ref ?? c.id ?? "").filter(Boolean),
    why: it.drivers?.[0]?.label,
    ...(status === "approved" ? { reply: draft } : {}),
  };
}

export const mapPatient = (p: WireUiPatient): Patient => ({
  code: p.code, sex: p.sex, age: p.age, day: p.day, base: p.base, tag: p.tag, why: p.why, missed: p.missed,
  noData: p.no_data, nextStep: p.next_step, clinic: p.clinic, visitThisWeek: p.visit_this_week, quiet: p.quiet,
  nextVisit: p.next_visit, supporter: p.supporter, consent: p.consent, changes: p.changes, personId: p.person_id,
});

export function mapRequest(r: WireRequest, nowMs: number): PatientRequest {
  return {
    id: r.id, patientCode: r.patient_code, kind: r.kind, text: r.text, when: fmtWhen(r.when), draft: r.draft,
    status: r.status, reply: r.reply ?? undefined, archived: r.archived, createdAt: Date.parse(r.when),
    dueMin: Math.round((Date.parse(r.due_at) - nowMs) / 60000), refs: r.refs,
  };
}

const CHANNEL_NAMES: Record<string, string> = { telegram: "Telegram", tg: "Telegram", gmail: "Gmail", email: "Email", calendar: "Calendar", sms: "SMS", whatsapp: "WhatsApp", app: "Patient app", portal: "Patient app" };
/** Backend channel id ("telegram") -> the name a doctor reads ("Telegram"). */
export const channelName = (c: string): string => CHANNEL_NAMES[c.trim().toLowerCase()] ?? (c ? c.charAt(0).toUpperCase() + c.slice(1) : "Unknown channel");

const DELIVERY_TEXT: Record<string, string> = {
  "skipped:no_consent": "Not sent: the patient has not given consent for this channel",
  "skipped:quiet_hours": "Not sent: held for the patient's quiet hours",
  "skipped:no_channel": "Not sent: the patient has no linked channel",
  "skipped:banned_term": "Not sent: the text contains a word that cannot be sent",
};
/** Raw outbox error ("skipped:no_consent") -> plain language. Unknown codes are de-underscored, never shown raw. */
export function friendlyDeliveryError(e?: string | null): string {
  if (!e) return "";
  const k = e.trim().toLowerCase();
  if (DELIVERY_TEXT[k]) return DELIVERY_TEXT[k];
  if (k.startsWith("skipped:")) return `Not sent: ${k.slice(8).replace(/_/g, " ")}`;
  return e.replace(/_/g, " ");
}

const CITE = /\s*\[((?:[EBCRGD]-\d+)(?:\s*,\s*[EBCRGD]-\d+)*)\]/g;
/** Pull raw [E-0412] citation tokens out of draft text. `clean` is what to show; `refs` are rendered as evidence chips. */
export function splitCitations(text: string): { clean: string; refs: string[] } {
  const refs: string[] = [];
  const clean = text.replace(CITE, (_m, ids: string) => {
    for (const i of ids.split(",")) if (!refs.includes(i.trim())) refs.push(i.trim());
    return "";
  }).replace(/[ ]+\n/g, "\n").trim();
  return { clean, refs };
}

export const mapMessage = (m: WireMessage): Message => ({
  id: m.id, srcId: m.src_id ?? "", code: m.code, at: fmtWhen(m.at), channel: channelName(m.channel), text: m.text,
  approvedBy: m.approved_by, version: m.version, status: m.status === "seen" ? "seen" : "sent",
  ...(m.delivery ? { delivery: m.delivery, deliveryError: friendlyDeliveryError(m.delivery_error) || undefined } : {}),
});

export const mapAudit = (a: WireAudit): AuditEntry => ({
  id: String(a.id), code: a.code ?? "", at: fmtWhen(a.at), actor: a.actor, action: a.label,
  srcId: a.src_id ?? undefined, version: a.version ?? undefined, note: a.note ?? undefined,
});

export const mapTemplate = (t: WireTemplate): Template => ({ id: t.template_id, name: `${t.key} (${t.lang})`, text: t.body });

/** The server may list one task name several times ("Other"). Merge them so each name shows once. */
export function mergeTasks(tasks: Usage["tasks"]): Usage["tasks"] {
  const m = new Map<string, Usage["tasks"][number]>();
  for (const t of tasks ?? []) {
    const c = m.get(t.name);
    if (!c) m.set(t.name, { ...t });
    else m.set(t.name, { name: t.name, spend: c.spend + t.spend, pct: Math.min(100, c.pct + t.pct), flag: c.flag === "watch" || t.flag === "watch" ? "watch" : c.flag });
  }
  return [...m.values()];
}
export const mapUsage = (u: WireUsage): Usage => ({
  mode: u.mode, todaySpend: u.today_spend, todayCap: u.today_cap, budgetUsed: u.budget_used, budget: u.budget,
  days: u.days, tasks: mergeTasks(u.tasks), retries: u.retries, breaker: u.breaker, billing: u.billing, providerPct: u.provider_pct,
});

export const mapEvidence = (e: Evidence): Evidence => e; // wire shape already equals the UI shape
export const mapLens = (l: LensSnap): LensSnap => l;

/** Action -> backend decision body (ReviewDecisionIn). Declining needs a reason on Red/Amber. */
export function decisionBody(decision: "approved" | "declined", text?: string) {
  if (decision === "declined") return { action: "reject", reason: "Declined by doctor" };
  return text ? { action: "edit", edited: { body: text } } : { action: "approve" };
}

// ---- patient / Supporter portal (cm/api/portal_models.py) ----
export interface WirePortalMe {
  patient_code: string; name: string; clinic: string; day: number; supporter?: { name: string; relation?: string | null } | null;
  reminder?: string | null; pending_reminder?: string | null; consents: Record<string, boolean>;
}
export interface WireToday { today: "none" | "taken" | "missed"; reason?: string | null; marked_by?: "self" | "supporter" | null; streak: number; next_visit?: string | null; history: string }
export interface WireRecord {
  days: { date: string; status: "taken" | "missed" | "none"; reason?: string | null }[];
  upcoming?: PortalAppt[]; past?: PortalAppt[];
}
export interface WirePortalMsg { id: string; title: string; text: string; created_at: string; read: boolean; for_supporter?: boolean }
export interface WireSupporterView {
  patient_code: string; patient_name: string; supporter_name: string; relation?: string | null; allowed: boolean;
  today: "none" | "taken" | "missed"; marked_by?: "self" | "supporter" | null; week: string; messages: WirePortalMsg[];
}
export interface WirePortalRequest { id: string; text: string; kind: string; when: string; status: Decision; reply?: string | null }

export const mapPortalMsg = (m: WirePortalMsg): PortalMsg => ({ id: m.id, title: m.title, text: m.text, at: m.created_at, read: m.read, forSupporter: !!m.for_supporter });

const apptOf = (a: PortalAppt): PortalAppt => ({ id: a.id, kind: a.kind, title: a.title, when: a.when, place: a.place, ...(a.note ? { note: a.note } : {}) });
export const mapRecord = (r: WireRecord): NonNullable<PortalSlice["record"]> => ({
  days: r.days.map((d) => ({ date: d.date, status: d.status, reason: d.reason ?? undefined })),
  upcoming: (r.upcoming ?? []).map(apptOf),
  past: (r.past ?? []).map(apptOf),
});

export const mapPortalMe = (m: WirePortalMe): NonNullable<PortalSlice["me"]> => ({
  code: m.patient_code, name: m.name, clinic: m.clinic, day: m.day,
  supporter: m.supporter ? { name: m.supporter.name, relation: m.supporter.relation || null } : null,
  reminder: m.reminder || null, pendingReminder: m.pending_reminder ?? null,
});

export const mapConsents = (c: Record<string, boolean> | undefined): PortalSlice["consents"] => ({
  telegram: !!c?.telegram, gmail: !!c?.gmail, calendar: !!c?.calendar,
});

export const mapSupporterView = (v: WireSupporterView): NonNullable<PortalSlice["supporter"]> => ({
  patientCode: v.patient_code, patientName: v.patient_name, supporterName: v.supporter_name, relation: v.relation || null, allowed: v.allowed, week: v.week,
});

/** A patient's own request (portal view): the patient code is the signed-in patient. */
export const mapPortalRequest = (r: WirePortalRequest, code: string): PatientRequest => ({
  id: r.id, patientCode: code, kind: r.kind, text: r.text, when: fmtWhen(r.when), draft: "", status: r.status,
  reply: r.reply ?? undefined, createdAt: Date.parse(r.when),
});

/** Date key "YYYY-MM-DD" -> local noon Date (avoids a UTC shift into the previous day). */
export function dayFromIso(d: string): Date {
  const [y, m, dd] = d.split("-").map(Number);
  return new Date(y, (m || 1) - 1, dd || 1, 12);
}

// ---- doctor extras ----
export interface WireTimeline { id: string; day: number; occurred_at: string; type: string; kind: string; source: string; text: string; ref?: string | null }
export interface TimelineRow { id: string; chip: boolean; day: number; at: string; kind: EvKind; reporter: string; text: string }
const TL_KIND: Record<string, EvKind> = { dose: "dose", refill: "refill", visit: "visit", message: "message", supporter: "supporter", lab: "lab" };
export const mapTimeline = (t: WireTimeline): TimelineRow => ({
  id: t.ref ?? t.id, chip: /^[EBCR]-\d+$/.test(t.ref ?? t.id), day: t.day, at: fmtWhen(t.occurred_at), kind: TL_KIND[t.kind] ?? "system", reporter: t.source, text: t.text,
});

export interface WireQueryAnswer {
  answer_text: string; numbers_verified: boolean; refused?: boolean; refusal_reason?: string | null;
  tool_calls_used?: { n: number; tool: string; row_count: number; result_preview?: Record<string, unknown>[] }[];
}
export interface AskSentence { text: string; refs: string[] }
export interface AskSource { n: number; label: string }
export interface MappedAnswer { sentences: AskSentence[]; sources: AskSource[]; verified: boolean; refused: boolean; record?: { text: string; cites: Record<string, CiteSnippet>; abstain: boolean } }

/** Split "text [1] more [2]" into sentences that carry the citation numbers as refs ("1", "2"). */
export function mapQueryAnswer(a: WireQueryAnswer): MappedAnswer {
  // Patient-record answer: [D-xxxxxxxx] refs (or the abstain line) are shown as citation chips, not numbered sources.
  const cites = snippetsFrom((a.tool_calls_used ?? []).flatMap((c) => c.result_preview ?? []));
  if (isAbstain(a.answer_text) || /\[D-[0-9a-f]{8}/.test(a.answer_text)) {
    return { sentences: [], sources: [], verified: a.numbers_verified, refused: !!a.refused, record: { text: a.answer_text.trim(), cites, abstain: isAbstain(a.answer_text) } };
  }
  const parts = a.answer_text.split(/(?<=\.)\s+(?=[A-Z0-9])/);
  const sentences = parts.map((p) => {
    const refs = [...p.matchAll(/\[(\d+)\]/g)].map((m) => m[1]);
    return { text: p.replace(/\s*\[\d+\]/g, "").trim(), refs: [...new Set(refs)] };
  }).filter((s) => s.text);
  const sources = (a.tool_calls_used ?? []).map((c) => ({ n: c.n, label: `${c.tool.replace(/_/g, " ")}: ${c.row_count} record${c.row_count === 1 ? "" : "s"}` }));
  return { sentences, sources, verified: a.numbers_verified, refused: !!a.refused };
}

/** /admin/settings.channels ({telegram: true}) -> the Admin channel list. Only what the server reports, nothing invented. */
export function mapChannels(ch: Record<string, boolean> | undefined): { name: string; connected: boolean; detail: string }[] {
  return Object.entries(ch ?? {}).map(([k, v]) => ({ name: channelName(k), connected: !!v, detail: v ? "Connected" : "Not connected" }));
}

export function mapServerSettings(s: { version: number; values: Record<string, string | number>; channels?: Record<string, boolean>; updated_at?: string | null }): ServerSettings {
  return { version: s.version, values: s.values, channels: s.channels ?? {}, updatedAt: s.updated_at ?? undefined };
}

export interface WireBulkItem { approval_id: string; ok?: boolean; error_code?: string | null; message?: string | null }
export interface BulkFailure { id: string; message: string }
const BULK_TEXT: Record<string, string> = {
  red_not_bulk: "Red items must be decided one at a time",
  amber_not_viewed: "Open this Amber item before approving it",
  already_decided: "Already decided",
  not_found: "Approval not found",
  reason_required: "A reason is required",
  banned_term: "The text contains a word that cannot be sent",
};
/** Items of a bulk decision that did not go through, each with a plain reason. */
export const bulkFailures = (rows: WireBulkItem[]): BulkFailure[] =>
  rows.filter((r) => r.ok === false || r.error_code).map((r) => ({ id: r.approval_id, message: r.message || (r.error_code ? BULK_TEXT[r.error_code] ?? r.error_code : "Not approved") }));

// ---- documents, medicines, district, consent ----
export interface WireDistrict {
  as_of: string; small_cell_threshold: number;
  clinics: { id: string; name: string; area: string; patients: number | null; adherence: number | null; quiet: number | null; pending: number | null; suppressed?: string[] }[];
  quiet_patients: { code: string; clinic: string; why: string; adherence: number; no_data: number }[];
  total_patients: number | null; total_pending_approvals: number;
}
export const mapDistrict = (d: WireDistrict): District => ({
  asOf: d.as_of, threshold: d.small_cell_threshold,
  clinics: d.clinics.map((c) => ({ ...c, suppressed: c.suppressed ?? [] })),
  quiet: d.quiet_patients.map((q) => ({ code: q.code, clinic: q.clinic, why: q.why, adherence: q.adherence, noData: q.no_data })),
  totalPatients: d.total_patients, totalPending: d.total_pending_approvals,
});
export const mapDocument = (d: { id: string; title: string; kind: string; date: string; summary: string }) => ({ id: d.id, title: d.title, kind: d.kind, date: d.date, summary: d.summary });
export const mapMedicine = (m: { id: string; label: string; when: string; note?: string | null }) => ({ id: m.id, label: m.label, when: m.when, note: m.note ?? null });

/** GET /consents/{person_id} -> one word for the overview table. Granted anywhere wins, then withdrawn, otherwise pending. */
export function mapConsentState(c: { by_source_purpose?: Record<string, Record<string, string>> }): "Active" | "Pending" | "Withdrawn" {
  const all = Object.values(c.by_source_purpose ?? {}).flatMap((p) => Object.values(p));
  return all.includes("granted") ? "Active" : all.includes("withdrawn") ? "Withdrawn" : "Pending";
}
