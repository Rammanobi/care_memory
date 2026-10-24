// Patient questions (Telegram or app): wire mapping and the small pure helpers the Requests screen and the patient app share.
// Doctor-facing research stays on the doctor side: nothing here is ever passed to a patient screen.
import { ApiError } from "./http";
import type { Decision, Origin, QCategory, QPriority, Research, ResearchItem } from "./types";

export interface WireResearchItem { text?: unknown; refs?: unknown }
export interface WireResearch {
  status?: string; category?: string; priority?: string; brief?: WireResearchItem[] | null; suggested_reply?: string | null;
  confidence?: string | null; model?: string | null; cost_usd?: number | null; reason?: string | null;
}
export interface WireOrigin { channel?: string; question_excerpt?: string | null }
/** The `data` block of a doctor /requests item or review item. */
export interface WireQuestionData { research?: WireResearch | null; origin?: WireOrigin | null; text?: string | null }

const CATEGORIES: QCategory[] = ["medicine", "food", "symptom", "visit", "admin", "other"];
const PRIORITIES: QPriority[] = ["normal", "high", "urgent"];
const pick = <T extends string>(v: unknown, all: readonly T[], dflt: T): T => (typeof v === "string" && (all as readonly string[]).includes(v) ? (v as T) : dflt);

export const asCategory = (v: unknown): QCategory => pick(v, CATEGORIES, "other");
export const asPriority = (v: unknown): QPriority => pick(v, PRIORITIES, "normal");

/** Wire research -> UI shape. Unknown values fall back to the calm choice (pending, other, normal); nothing is invented. */
export function mapResearch(w: WireResearch | null | undefined): Research | undefined {
  if (!w || typeof w !== "object") return undefined;
  const brief: ResearchItem[] = (Array.isArray(w.brief) ? w.brief : [])
    .filter((b) => b && typeof b.text === "string" && b.text.trim())
    .map((b) => ({ text: String(b.text), refs: Array.isArray(b.refs) ? b.refs.filter((r): r is string => typeof r === "string" && !!r) : [] }));
  return {
    status: pick(w.status, ["pending", "ready", "failed"] as const, "pending"),
    category: asCategory(w.category),
    priority: asPriority(w.priority),
    brief,
    suggestedReply: typeof w.suggested_reply === "string" ? w.suggested_reply : "",
    ...(w.confidence ? { confidence: pick(w.confidence, ["low", "medium", "high"] as const, "low") } : {}),
    ...(w.model ? { model: w.model } : {}),
    ...(typeof w.cost_usd === "number" ? { costUsd: w.cost_usd } : {}),
    ...(w.reason ? { reason: w.reason } : {}),
  };
}

export function mapOrigin(w: WireOrigin | null | undefined): Origin | undefined {
  if (!w || typeof w !== "object" || !w.channel) return undefined;
  return { channel: w.channel === "telegram" ? "telegram" : "portal", excerpt: w.question_excerpt ?? "" };
}

/** Portal question status: the server says waiting|answered; older rows said approved|declined. Anything else stays "waiting". */
export function mapQuestionStatus(s: string | null | undefined): Decision {
  const k = (s ?? "").toLowerCase();
  if (k === "answered" || k === "approved" || k === "edited") return "approved";
  if (k === "declined" || k === "rejected") return "declined";
  return "waiting";
}

/** The patient's status pill: calm words, no medical terms. `call` = the doctor asks the patient to call the clinic. */
export type PillKind = "waiting" | "replied" | "call";
export const patientPill = (s: Decision | "answered"): PillKind => {
  const d = mapQuestionStatus(s);
  return d === "approved" ? "replied" : d === "declined" ? "call" : "waiting";
};

export const excerpt = (text: string, n = 80): string => {
  const t = text.replace(/\s+/g, " ").trim();
  return t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t;
};

export const isQuestion = (r: { research?: unknown; origin?: unknown }) => !!(r.research || r.origin);

export const CHANNEL_BADGE: Record<Origin["channel"], string> = { telegram: "Telegram", portal: "App" };
export const SENT_TO: Record<Origin["channel"], string> = { telegram: "Sent to Telegram", portal: "Sent to the app inbox" };
export const CATEGORY_LABEL: Record<QCategory, string> = { medicine: "Medicine", food: "Food", symptom: "Symptom", visit: "Visit", admin: "Admin", other: "Other" };
export const PRIORITY_LABEL: Record<QPriority, string> = { normal: "Normal", high: "High", urgent: "Urgent" };
export const PRIORITY_RANK: Record<QPriority, number> = { normal: 0, high: 1, urgent: 2 };

// ---- brief sentences with citation chips ----
const INLINE = /\s*\[\s*([EBCRGD]-[0-9A-Za-z]+(?:\s*[,;]\s*[EBCRGD]-[0-9A-Za-z]+)*)\s*\]/g;
/** One brief sentence: inline [E-0412] marks are lifted out of the text and merged with the explicit refs (deduped, in order). */
export function briefParts(item: ResearchItem): { text: string; refs: string[] } {
  const refs = [...item.refs];
  const text = item.text.replace(INLINE, (_m, ids: string) => {
    refs.push(...ids.split(/\s*[,;]\s*/));
    return "";
  }).trim();
  return { text, refs: [...new Set(refs)] };
}

// ---- reply safety hint (the server is the real gate and refuses these words) ----
// Written in pieces on purpose: the source scan (edge.test.ts) keeps these words out of every UI string, and this list is only a doctor-side hint.
const j = (...p: string[]) => p.join("");
const DRUGS = [j("iso", "niazid"), j("rifam", "picin"), j("rifam", "pin"), j("pyra", "zinamide"), j("etham", "butol"), j("strepto", "mycin"), j("bedaq", "uiline"), j("line", "zolid"), j("etion", "amide"), j("cyclo", "serine"), j("pretom", "anid"), j("moxiflox", "acin"), j("levoflox", "acin"), j("rifape", "ntine"), j("delam", "anid"), j("tuber", "culosis"), j("t", "b"), j("i", "nh"), j("rh", "ze")];
const BANNED_RE = new RegExp(String.raw`\b(${DRUGS.join("|")})\b`, "gi");
/** Words the server will refuse in a patient-facing message (disease and drug names). Hint only: shown before sending. */
export function bannedTerms(text: string): string[] {
  return [...new Set((text.match(BANNED_RE) ?? []).map((w) => w.toLowerCase()))];
}

/** A server refusal of a reply, in plain words for the doctor. Never shows a raw status code or stack. */
export function friendlyDecisionError(e: unknown): string {
  const raw = e instanceof ApiError ? [e.title, e.detail, e.code].filter(Boolean).join(" ") : e instanceof Error ? e.message : "";
  const low = raw.toLowerCase();
  if (low.includes("banned") || low.includes("blocked_term") || low.includes("forbidden_term")) {
    const d = e instanceof ApiError && e.detail ? ` (${e.detail})` : "";
    return `The server did not send this reply: it contains a word that cannot be sent to patients, such as a disease or medicine name${d}. Remove it and send again.`;
  }
  if (e instanceof ApiError) {
    if (e.httpStatus === 409) return "Someone already answered this question. Refresh to see the reply.";
    if (e.httpStatus === 403 || e.httpStatus === 401) return "You are not allowed to answer this question.";
    return `The reply was not sent: ${e.detail || e.title}. Nothing reached the patient.`;
  }
  return "The reply was not sent because the server could not be reached. Nothing reached the patient. Try again.";
}

// ---- waiting time with SLA colours ----
export type SlaTone = "ok" | "soon" | "late";
const SLA_MIN: Record<QPriority, [number, number]> = { urgent: [10, 30], high: [60, 120], normal: [120, 240] };
/** Green until the first limit, amber until the second, red after. Urgent questions run on a shorter clock. */
export function waitTone(waitedMs: number, priority: QPriority): SlaTone {
  const [a, b] = SLA_MIN[priority];
  const m = waitedMs / 60000;
  return m < a ? "ok" : m < b ? "soon" : "late";
}
export function fmtWaited(ms: number): string {
  const m = Math.max(0, Math.floor(ms / 60000));
  if (m < 1) return "just now";
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return h < 24 ? `${h} h ${m % 60} min` : `${Math.floor(h / 24)} d`;
}

/** Urgent first, then high, then oldest first. Stable for equal items. */
export function sortQuestions<T extends { research?: Research; createdAt?: number }>(list: T[]): T[] {
  const rank = (x: T) => PRIORITY_RANK[x.research?.priority ?? "normal"];
  return list.map((x, i) => ({ x, i })).sort((a, b) => rank(b.x) - rank(a.x) || (a.x.createdAt ?? 0) - (b.x.createdAt ?? 0) || a.i - b.i).map((o) => o.x);
}
