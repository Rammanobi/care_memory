import type { CareState } from "./types";
import { counts } from "./derive";

const digits = (t: string) => t.match(/\d+(?:\.\d+)?/g) ?? [];

/** Every number that exists in the mock data (record text, times, ages, usage) plus the dashboard counts. */
export function knownNumbers(s: CareState): Set<string> {
  const set = new Set<string>();
  const raw = JSON.stringify({ p: s.patients, r: s.requests, a: s.approvals, e: s.evidence, m: s.messages, l: s.lens, c: s.clinics });
  digits(raw).forEach((d) => set.add(String(Number(d))));
  const c = counts(s);
  [c.all, c.needs, c.requests, c.quiet, c.visit, c.red, c.track, c.pendingApprovals, c.pendingRequests].forEach((n) => set.add(String(n)));
  return set;
}

/** Every number in an answer must come from the data. Citation markers like [2] are ignored. */
export function checkNumbers(text: string, s: CareState): { ok: boolean; unknown: string[] } {
  const known = knownNumbers(s);
  const unknown = digits(text.replace(/\[\d+\]/g, "")).filter((d) => !known.has(String(Number(d))));
  return { ok: unknown.length === 0, unknown };
}
