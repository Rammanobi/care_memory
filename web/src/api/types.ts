// Shapes the UI needs. The real backend adapter must return these (or be mapped to them).
export type Base = "red" | "amb" | "grn";
export type Level = Base | "blu";

export interface Patient {
  code: string;
  sex: "M" | "F";
  age: number;
  day: number;
  base: Base;
  tag: string; // text label shown next to the colour (RED, QUIET ...)
  why: string;
  missed: number[]; // indexes (0..19) of missed days in the last 20
  noData: number; // trailing days with no data
  nextStep: string;
  clinic: string; // clinic id
  visitThisWeek: boolean;
  quiet: boolean;
  nextVisit: string;
  supporter: string;
  consent: string;
  reviewIn?: string;
  changes: { text: string; ev: string }[];
  personId?: string; // server person id, used for /consents/{person_id}
}

export type Decision = "waiting" | "approved" | "declined";

export interface PatientRequest {
  id: string;
  patientCode: string;
  kind: string;
  text: string;
  when: string;
  draft: string;
  status: Decision;
  reply?: string;
  archived?: boolean; // old history: not shown as a live card
  createdAt?: number; // epoch ms
  dueMin?: number; // review deadline, minutes after the seed time (or createdAt)
  refs?: string[]; // evidence ids behind the draft
}

export interface Approval {
  id: string;
  patientCode: string;
  lane: "red" | "amber" | "green";
  title: string;
  draft: string;
  status: Decision;
  reply?: string;
  dueMin?: number; // minutes after the seed time
  refs?: string[];
  why?: string; // one plain line: why the assistant wrote this
}

export interface Dose {
  today: "none" | "taken" | "missed";
  reason?: string;
}

export type EvKind = "dose" | "refill" | "visit" | "message" | "supporter" | "lab" | "system";
/** Source records behind every E-/B-/C-/R- chip. */
export interface Evidence {
  id: string; // E-0412, B-0101, C-0201, R-0301
  code: string;
  at: string;
  kind: EvKind;
  reporter: string;
  text: string;
  why: string;
}
export interface Message {
  id: string;
  srcId: string; // approval or request id
  code: string;
  at: string;
  channel: string;
  text: string;
  approvedBy: string;
  version: number;
  status: "sent" | "seen";
  delivery?: "queued" | "sent" | "failed"; // outbox state (server only)
  deliveryError?: string;
}
export interface AuditEntry {
  id: string;
  code: string;
  at: string;
  actor: string;
  action: string;
  srcId?: string;
  version?: number;
  note?: string;
}
export interface Note { id: string; code: string; at: string; by: string; text: string }
export interface Clinic { id: string; name: string; area: string }
export interface Template { id: string; name: string; text: string }
export interface LensSnap {
  code: string;
  day: 3 | 60;
  known: string;
  beliefs: { id: string; text: string; conf: string }[];
  risk: [number, number];
  conflicts: { id: string; text: string }[];
}
export type UsageMode = "GREEN" | "AMBER" | "RED";
export interface Usage {
  mode: UsageMode;
  todaySpend: number;
  todayCap: number;
  budgetUsed: number;
  budget: number;
  days: { d: string; spend: number }[]; // 14 days
  tasks: { name: string; spend: number; pct: number; flag: string }[];
  retries: number;
  breaker: number;
  billing: number;
  providerPct: number;
}
export interface Settings { notifyRed: boolean; notifyRequests: boolean; digest: boolean; quiet: boolean; sound: boolean }

/** Patient or Supporter data read from /portal/*. Absent in mock mode (the screens then use the sample data). */
export interface PortalAppt { id: string; kind: "visit" | "lab"; title: string; when: string; place: string; note?: string }
export interface PortalMsg { id: string; title: string; text: string; at: string; read: boolean; forSupporter: boolean }
export interface PortalDoc { id: string; title: string; kind: string; date: string; summary: string }
export interface PortalMed { id: string; label: string; when: string; note: string | null }
export interface PortalSlice {
  me?: { code: string; name: string; clinic: string; day: number; supporter: { name: string; relation: string } | null; reminder: string; pendingReminder: string | null };
  consents: { telegram: boolean; gmail: boolean; calendar: boolean };
  streak: number;
  nextVisit: string | null;
  history: string; // 60 chars oldest first: o taken, m missed, f not yet recorded
  markedBy: "self" | "supporter" | null;
  record: { days: { date: string; status: "taken" | "missed" | "none"; reason?: string | null }[]; upcoming: PortalAppt[]; past: PortalAppt[] } | null;
  inbox: PortalMsg[];
  documents?: PortalDoc[];
  medicines?: PortalMed[];
  supporter?: { patientCode: string; patientName: string; supporterName: string; relation: string; allowed: boolean; week: string };
}

/** Server-side rule thresholds (GET /admin/settings) with their optimistic-lock version. */
export interface ServerSettings { version: number; values: Record<string, string | number>; channels: Record<string, boolean>; updatedAt?: string }

/** GET /dashboard/district. A null number is a suppressed small cell (1..threshold-1). */
export interface District {
  asOf: string;
  threshold: number;
  clinics: { id: string; name: string; area: string; patients: number | null; adherence: number | null; quiet: number | null; pending: number | null; suppressed: string[] }[];
  quiet: { code: string; clinic: string; why: string; adherence: number; noData: number }[];
  totalPatients: number | null;
  totalPending: number;
}

export interface CareState {
  district?: District;
  patients: Patient[];
  requests: PatientRequest[];
  approvals: Approval[];
  dose: Dose;
  // doctor-side extras (optional so older stored data still loads)
  seededAt: number;
  simDay: number;
  evidence: Evidence[];
  messages: Message[];
  audit: AuditEntry[];
  notes: Note[];
  clinics: Clinic[];
  templates: Template[];
  lens: LensSnap[];
  usage: Usage;
  channels: { name: string; connected: boolean; detail: string }[];
  settings: Settings;
  portal?: PortalSlice;
  serverSettings?: ServerSettings;
  /** Live mode: slices that failed to load (shown as "could not load", never replaced by sample data). */
  loadErrors?: string[];
}

export type Action =
  | { t: "dose"; value: Dose }
  | { t: "newRequest"; req: PatientRequest }
  | { t: "decideRequest"; id: string; decision: "approved" | "declined"; text?: string }
  | { t: "decideApprovals"; ids: string[]; decision: "approved" | "declined"; text?: string }
  | { t: "undo"; ids: string[] }
  | { t: "seen"; srcId: string }
  | { t: "addNote"; note: Note }
  | { t: "usageMode"; mode: UsageMode }
  | { t: "simDay"; value: number }
  | { t: "channel"; name: string; connected: boolean }
  | { t: "setting"; key: keyof Settings; value: boolean }
  | { t: "empty" }
  | { t: "markRead"; id: string }
  | { t: "consent"; key: "telegram" | "gmail" | "calendar"; value: boolean }
  | { t: "reminder"; time: string };

/** Everything the screens need from a backend. The mock adapter implements it today. */
export interface CareApi {
  load(): Promise<CareState>;
  dispatch(action: Action): Promise<CareState>;
  /** Called when another tab (or the server) changed the data. */
  subscribe(cb: () => void): () => void;
  reset(): Promise<CareState>;
  /** Live mode: fetch one approval's draft text when its card is opened. */
  loadDetail?(id: string): Promise<CareState>;
}
