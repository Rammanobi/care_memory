// Patient document upload helpers (pure, unit tested): client-side checks, plain-word errors, status pills, and the
// doctor-side mapping of data.document. The upload call itself is in uploadDocument.ts.
import type { DocField, DocReview, PortalDoc } from "./types";

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
// Explicit list only, matching what the backend accepts. SVG, HTML and archives are refused (never `image/*`).
const IMAGE_MIME = ["image/png", "image/jpeg", "image/webp", "image/heic", "image/heif", "image/gif"];
const IMAGE_EXT = [".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif", ".gif"];
export const IMAGE_ACCEPT = [...IMAGE_MIME, ...IMAGE_EXT].join(",");
export const ACCEPT = [...IMAGE_MIME, ...IMAGE_EXT, "application/pdf", "text/plain", ".pdf", ".txt"].join(",");
export const OK_MIME = new Set([...IMAGE_MIME, "application/pdf", "text/plain"]);
export const OK_EXT = new Set(["pdf", "txt", "jpg", "jpeg", "png", "webp", "heic", "heif", "gif"]);

/** Keys of the patient strings (i18nExtra) that describe a refusal. */
export type UploadProblem = "upEmpty" | "upBadType" | "upTooBig" | "upErrTooBig" | "upErrType" | "upErrBusy" | "upErrSignin" | "upErrNet" | "upErrGeneric";

export function validateUpload(f: { name: string; type: string; size: number }): UploadProblem | null {
  if (f.size <= 0) return "upEmpty";
  const ext = f.name.includes(".") ? f.name.split(".").pop()!.toLowerCase() : "";
  // A known MIME type must be on the list; some browsers leave it empty (HEIC), then the extension decides. An .svg name is never allowed.
  const typeOk = f.type ? OK_MIME.has(f.type.toLowerCase()) && (ext === "" || OK_EXT.has(ext)) : OK_EXT.has(ext);
  if (!typeOk) return "upBadType";
  if (f.size > MAX_UPLOAD_BYTES) return "upTooBig";
  return null;
}

/** A server or network failure in plain words. Never a status code or a stack. `isNetwork` is true for a failed connection. */
export function uploadProblemFrom(e: unknown, isNetwork = false): UploadProblem {
  const st = (e as { httpStatus?: number } | null)?.httpStatus;
  if (isNetwork || st === 0) return "upErrNet";
  if (st === 413) return "upErrTooBig";
  if (st === 415 || st === 422) return "upErrType";
  if (st === 429) return "upErrBusy";
  if (st === 401 || st === 403) return "upErrSignin";
  return "upErrGeneric";
}

export interface UploadResult { documentId: string; status: string; duplicate: boolean }

/** Patient status pill: calm words only. Unknown server words fall back to "with your care team". */
export type DocPill = "received" | "care" | "added" | "failed";
export function docPill(status: string | null | undefined): DocPill {
  const k = (status ?? "").trim().toLowerCase();
  if (k === "received") return "received";
  if (k === "added to your record") return "added";
  if (k === "could not be used") return "failed";
  return "care";
}
export const PILL_KEY: Record<DocPill, "dpReceived" | "dpCare" | "dpAdded" | "dpFailed"> = { received: "dpReceived", care: "dpCare", added: "dpAdded", failed: "dpFailed" };
export const PILL_CLASS: Record<DocPill, string> = { received: "w", care: "w", added: "a", failed: "c" };

export function mapPortalDoc(d: { id: string; title?: string | null; name?: string | null; kind?: string | null; date?: string | null; summary?: string | null; status?: string | null; created_at?: string | null }): PortalDoc {
  return {
    id: d.id, title: d.title || d.name || "Document", kind: d.kind || "other",
    date: (d.date || d.created_at || "").slice(0, 10) || new Date().toISOString().slice(0, 10), summary: d.summary ?? "",
    ...(d.status ? { status: d.status } : {}),
  };
}

// ---- doctor side: data.document of a request or review item ----
const str = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : String(v));
const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** Wire data.document -> UI shape. Returns undefined when there is no usable document block (the item stays an ordinary request). */
export function mapDocReview(w: unknown): DocReview | undefined {
  if (!w || typeof w !== "object") return undefined;
  const d = w as Record<string, unknown>;
  if (typeof d.id !== "string" || !d.id) return undefined;
  const ex = (d.extraction && typeof d.extraction === "object" ? d.extraction : {}) as Record<string, unknown>;
  const fields: DocField[] = (Array.isArray(ex.fields) ? ex.fields : [])
    .filter((f): f is Record<string, unknown> => !!f && typeof f === "object" && typeof (f as Record<string, unknown>).name === "string")
    .map((f) => ({ name: str(f.name), value: str(f.value), confidence: typeof f.confidence === "number" || typeof f.confidence === "string" ? f.confidence : null }));
  return {
    id: d.id, filename: str(d.filename) || "Uploaded file", mime: str(d.mime), size: num(d.size) ?? 0, pages: num(d.pages), status: str(d.status),
    docType: str(ex.doc_type), fields, textExcerpt: str(ex.text_excerpt),
  };
}

export type ConfLevel = "low" | "medium" | "high" | "unknown";
/** Confidence as a level. Numbers are 0..1 (or 0..100); words low|medium|high pass through. Missing = unknown, shown as needing a check. */
export function confidenceLevel(c: number | string | null | undefined): ConfLevel {
  if (typeof c === "string") {
    const k = c.trim().toLowerCase();
    if (k === "low" || k === "medium" || k === "high") return k;
    const n = Number(k);
    return Number.isFinite(n) && k !== "" ? confidenceLevel(n) : "unknown";
  }
  if (typeof c !== "number" || !Number.isFinite(c)) return "unknown";
  const v = c > 1 ? c / 100 : c;
  return v < 0.6 ? "low" : v < 0.85 ? "medium" : "high";
}
export function confidenceText(c: number | string | null | undefined): string {
  const lv = confidenceLevel(c);
  if (typeof c === "number" && lv !== "unknown") return `${Math.round(c > 1 ? c : c * 100)}%`;
  return lv === "unknown" ? "unchecked" : lv;
}
export const fmtSize = (b: number): string => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : b >= 1024 ? `${Math.round(b / 1024)} KB` : `${b} B`);
