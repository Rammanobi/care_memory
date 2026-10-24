// Parser for the patient-record answers: "Missed the evening dose [D-1a2b3c4d]." -> text and citation segments.
export type CiteSnippet = { date: string; kind: string; snippet: string };
export type CiteSegment = { t: "text"; v: string } | { t: "ref"; ref: string; known: boolean };

export const ABSTAIN_TEXT = "Not in the record yet.";
export const isAbstain = (text: string) => text.trim() === ABSTAIN_TEXT;

// One bracket group: [D-1a2b3c4d] or [D-1a2b3c4d, D-5e6f7a8b]. Only D- refs are chips; other brackets stay text.
const GROUP = /\[\s*(D-[0-9a-f]{8}(?:\s*[,;]\s*D-[0-9a-f]{8})*)\s*\]/g;

/** Split answer text into text and ref segments. `known` = the ref has a snippet in the answer's evidence. */
export function parseCitations(text: string, known?: ReadonlySet<string> | Record<string, unknown>): CiteSegment[] {
  const has = (r: string) => (known instanceof Set ? known.has(r) : known ? r in known : false);
  const out: CiteSegment[] = [];
  let last = 0;
  for (const m of text.matchAll(GROUP)) {
    const i = m.index ?? 0;
    if (i > last) out.push({ t: "text", v: text.slice(last, i) });
    for (const ref of m[1].split(/\s*[,;]\s*/)) out.push({ t: "ref", ref, known: has(ref) });
    last = i + m[0].length;
  }
  if (last < text.length) out.push({ t: "text", v: text.slice(last) });
  return out;
}

export const KIND_LABEL: Record<string, string> = { event: "Event", daily: "Daily summary", weekly: "Weekly summary" };
export const kindLabel = (k: string) => KIND_LABEL[k] ?? "Record";

/** Evidence rows of the server answer ({ref,date,kind,snippet}) keyed by ref. */
export function snippetsFrom(rows: Record<string, unknown>[] | undefined): Record<string, CiteSnippet> {
  const out: Record<string, CiteSnippet> = {};
  for (const r of rows ?? []) {
    if (typeof r.ref === "string" && /^D-[0-9a-f]{8}$/.test(r.ref)) out[r.ref] = { date: String(r.date ?? ""), kind: String(r.kind ?? ""), snippet: String(r.snippet ?? "") };
  }
  return out;
}

/** The scoped question sent to the server: the API has no patient field, so the code leads the text. */
export const scopedQuestion = (code: string | null | undefined, q: string) => (code ? `${code}: ${q.trim()}` : q.trim());
