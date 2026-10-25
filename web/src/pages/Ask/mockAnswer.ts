// Offline (mock) answers for the Ask box. Pure, so the matcher is unit tested: no keyword match means ABSTAIN, never a guess.
import { counts, dueAtOf } from "../../api/derive";
import { ABSTAIN_TEXT, type CiteSnippet } from "../../api/citations";
import type { CareState } from "../../api";

export interface Sentence { text: string; refs: string[] }
export interface RecordAnswer { text: string; cites: Record<string, CiteSnippet>; abstain: boolean }
export interface MockAnswer { sentences: Sentence[]; record?: RecordAnswer }

/** First letter upper case ("no chemist refill" -> "No chemist refill"). */
export const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

export const CHIPS = ["Who needs me first today?", "Who has gone quiet?", "Why is PT-0142 flagged?", "Which patients have a refill gap?", "How many requests are waiting?", "What changed for PT-0176?"];
/** Chips that only make sense for one patient (shown while the Ask box is scoped to a patient). */
export const PATIENT_CHIPS = ["Why were evening doses missed?", "What is the patient's insurance status?"];

const SAMPLE_CITES: Record<string, CiteSnippet> = {
  "D-3f9a1c20": { date: "2026-03-03", kind: "event", snippet: "Evening dose not taken. Reason given: working late." },
  "D-7b2e4d11": { date: "2026-03-10", kind: "event", snippet: "Evening dose not taken. No reason given." },
  "D-a41c9e05": { date: "2026-03-14", kind: "weekly", snippet: "Week summary: 2 evening doses missed, morning doses all taken." },
};
const ABSTAIN: RecordAnswer = { abstain: true, cites: {}, text: ABSTAIN_TEXT };

/** Patient-record samples: one with citations, one that abstains. */
export function sampleRecord(q: string): RecordAnswer | null {
  if (/miss|evening|skipp/i.test(q)) return { abstain: false, cites: SAMPLE_CITES, text: "Missed the evening dose on 3 March [D-3f9a1c20]. Missed the evening dose again on 10 March [D-7b2e4d11]. The week to 14 March shows 2 evening doses missed [D-a41c9e05][D-3f9a1c20]." };
  if (/insurance|income|weather|diet|family history|alcohol|smok|drink|religion|salary/i.test(q)) return ABSTAIN;
  return null;
}

/** Words that make a question about one patient answerable from the list data. */
const PATIENT_Q = /flag|why|chang|summary|happen|wrong|concern|draft|waiting|doing|update/i;
const HAS_CODE = /PT-\d{4}/i;

/** Canned answers built from the live mock state, so every number is data. Returns null when nothing matches. */
function answer(q: string, s: CareState): Sentence[] | null {
  const t = q.toLowerCase();
  const code = q.match(HAS_CODE)?.[0].toUpperCase();
  const c = counts(s);
  const first = (pc: string) => s.patients.find((p) => p.code === pc)?.changes[0]?.ev;
  if (code) {
    const p = s.patients.find((x) => x.code === code);
    if (!p || !PATIENT_Q.test(t)) return null;
    const out: Sentence[] = [{ text: `${p.code} is on day ${p.day}.`, refs: [] }, { text: `${cap(p.why)}.`, refs: [] }, ...p.changes.map((ch) => ({ text: `${cap(ch.text)}.`, refs: [ch.ev] }))];
    const ap = s.approvals.find((a) => a.patientCode === code && a.status === "waiting" && a.lane !== "green");
    if (ap) out.push({ text: `A draft is waiting for your review: ${ap.title}.`, refs: ap.refs?.slice(0, 1) ?? [] });
    return out;
  }
  if (/first|urgent|\bred\b|worst|need/.test(t)) {
    const reds = s.approvals.filter((a) => a.lane === "red" && a.status === "waiting").sort((a, b) => dueAtOf(s, a) - dueAtOf(s, b));
    return reds.length
      ? [{ text: `${reds.length} red drafts are waiting, soonest first.`, refs: [] }, ...reds.map((a) => ({ text: `${a.patientCode}: ${a.title}.`, refs: a.refs?.slice(0, 1) ?? [] }))]
      : [{ text: "No red drafts are waiting right now.", refs: [] }];
  }
  if (/quiet|silent|no reply|no data/.test(t)) {
    const qs = s.patients.filter((p) => p.quiet);
    return [{ text: `${qs.length} patients are quiet for 3 or more days.`, refs: [] }, ...qs.map((p) => ({ text: `${p.code}: ${p.changes[0]?.text ?? p.why}.`, refs: first(p.code) ? [first(p.code)!] : [] }))];
  }
  if (/refill|chemist|supply/.test(t)) {
    const ev = s.evidence.filter((e) => e.kind === "refill" && /no refill|left/i.test(e.text));
    return ev.length ? [{ text: `${ev.length} patients have a supply concern.`, refs: [] }, ...ev.map((e) => ({ text: `${e.code}: ${e.text.toLowerCase()}.`, refs: [e.id] }))] : [{ text: "No supply concerns are recorded.", refs: [] }];
  }
  if (/request|waiting/.test(t)) {
    const rs = s.requests.filter((r) => r.status === "waiting" && !r.archived);
    return [{ text: `${c.pendingRequests} patient requests are waiting for you.`, refs: [] }, ...rs.map((r) => ({ text: `${r.patientCode} asked: "${r.text}"`, refs: r.refs?.slice(0, 1) ?? [] }))];
  }
  if (/approv|draft/.test(t)) return [{ text: `${c.pendingApprovals} drafts are waiting for approval.`, refs: [] }];
  return null;
}

/** The mock reply to a question. `scope` is the patient the box is scoped to (its code leads the question). */
export function mockReply(qt: string, scope: string | null, s: CareState): MockAnswer {
  const rec = sampleRecord(qt);
  if (rec) return { sentences: [], record: rec };
  const scoped = !!scope && !HAS_CODE.test(qt);
  // Scoped free text only answers when it asks about the flagged state; anything else is not in the record.
  const out = scoped && !PATIENT_Q.test(qt) ? null : answer(scoped ? `${scope}: ${qt}` : qt, s);
  return out ? { sentences: out } : { sentences: [], record: ABSTAIN };
}
