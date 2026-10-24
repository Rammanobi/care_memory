import { useEffect, useMemo, useState } from "react";
import { useCare } from "../../api/CareProvider";
import { counts, dueAtOf, findEvidence } from "../../api/derive";
import { checkNumbers } from "../../api/numberCheck";
import { askServer, isLive, suggestionsServer } from "../../api/serverCalls";
import type { AskSource } from "../../api/mapping";
import type { CareState } from "../../api";
import { EvChip, useEvidence } from "../../components/doctorKit";
import { Skeleton } from "../../components/ui";

interface Sentence { text: string; refs: string[] }
interface Answer { q: string; sentences: Sentence[]; sources?: AskSource[]; verified?: boolean; refused?: boolean; error?: string; pending?: boolean }

const CHIPS = ["Who needs me first today?", "Who has gone quiet?", "Why is PT-0142 flagged?", "Which patients have a refill gap?", "How many requests are waiting?", "What changed for PT-0176?"];

/** Canned answers built from the live mock state, so every number is data. */
function answer(q: string, s: CareState): Answer {
  const t = q.toLowerCase();
  const code = q.match(/PT-\d{4}/i)?.[0].toUpperCase();
  const c = counts(s);
  const first = (pc: string) => s.patients.find((p) => p.code === pc)?.changes[0]?.ev;
  let sentences: Sentence[];
  if (code && s.patients.some((p) => p.code === code)) {
    const p = s.patients.find((x) => x.code === code)!;
    sentences = [{ text: `${p.code} is on day ${p.day}: ${p.why.toLowerCase()}.`, refs: [] }, ...p.changes.map((ch) => ({ text: `${ch.text}.`, refs: [ch.ev] }))];
    const ap = s.approvals.find((a) => a.patientCode === code && a.status === "waiting" && a.lane !== "green");
    if (ap) sentences.push({ text: `A draft is waiting for your review: ${ap.title}.`, refs: ap.refs?.slice(0, 1) ?? [] });
  } else if (/first|urgent|red|worst|need/.test(t)) {
    const reds = s.approvals.filter((a) => a.lane === "red" && a.status === "waiting").sort((a, b) => dueAtOf(s, a) - dueAtOf(s, b));
    sentences = reds.length
      ? [{ text: `${reds.length} red drafts are waiting, soonest first.`, refs: [] }, ...reds.map((a) => ({ text: `${a.patientCode}: ${a.title}.`, refs: a.refs?.slice(0, 1) ?? [] }))]
      : [{ text: "No red drafts are waiting right now.", refs: [] }];
  } else if (/quiet|silent|no reply|no data/.test(t)) {
    const qs = s.patients.filter((p) => p.quiet);
    sentences = [{ text: `${qs.length} patients are quiet for 3 or more days.`, refs: [] }, ...qs.map((p) => ({ text: `${p.code}: ${p.changes[0]?.text ?? p.why}.`, refs: first(p.code) ? [first(p.code)!] : [] }))];
  } else if (/refill|chemist|supply/.test(t)) {
    const ev = s.evidence.filter((e) => e.kind === "refill" && /no refill|left/i.test(e.text));
    sentences = ev.length ? [{ text: `${ev.length} patients have a supply concern.`, refs: [] }, ...ev.map((e) => ({ text: `${e.code}: ${e.text.toLowerCase()}.`, refs: [e.id] }))] : [{ text: "No supply concerns are recorded.", refs: [] }];
  } else if (/request|ask|waiting/.test(t)) {
    const rs = s.requests.filter((r) => r.status === "waiting" && !r.archived);
    sentences = [{ text: `${c.pendingRequests} patient requests are waiting for you.`, refs: [] }, ...rs.map((r) => ({ text: `${r.patientCode} asked: "${r.text}"`, refs: r.refs?.slice(0, 1) ?? [] }))];
  } else if (/approv|draft/.test(t)) {
    sentences = [{ text: `${c.pendingApprovals} drafts are waiting for approval.`, refs: [] }];
  } else {
    sentences = [{ text: `I can answer from the ${c.all} patients on the list. Try one of the suggested questions.`, refs: [] }];
  }
  return { q, sentences };
}

export default function AskPage() {
  const { state } = useCare();
  const open = useEvidence();
  const [q, setQ] = useState("");
  const [history, setHistory] = useState<Answer[]>([]);
  const [chips, setChips] = useState(CHIPS);
  useEffect(() => {
    if (isLive) suggestionsServer().then((c) => c.length && setChips(c)).catch(() => undefined);
  }, []);
  const ask = (text: string) => {
    if (!state || !text.trim()) return;
    const qt = text.trim();
    setQ("");
    if (!isLive) return setHistory((h) => [answer(qt, state), ...h]);
    const stamp: Answer = { q: qt, sentences: [], pending: true };
    setHistory((h) => [stamp, ...h]);
    const settle = (a: Answer) => setHistory((h) => h.map((x) => (x === stamp ? a : x)));
    askServer(qt)
      .then((r) => settle({ q: qt, sentences: r.sentences, sources: r.sources, verified: r.verified, refused: r.refused }))
      .catch((e: unknown) => settle({ q: qt, sentences: [], error: e instanceof Error ? e.message : "The question could not be answered." }));
  };

  const view = useMemo(() => history.map((a) => {
    const order: string[] = [];
    a.sentences.forEach((s) => s.refs.forEach((r) => !order.includes(r) && order.push(r)));
    const text = a.sentences.map((s) => s.text).join(" ");
    const check = a.verified !== undefined ? { ok: a.verified, unknown: [] as string[] } : state ? checkNumbers(text, state) : { ok: true, unknown: [] as string[] };
    return { a, order, check };
  }), [history, state]);

  return (
    <main className="main wide" aria-labelledby="h-ask">
      <h1 id="h-ask">Ask</h1>
      <div className="sub">Ask about your patients. Answers use only the records in this clinic, and every claim has a source.</div>
      {!state ? <div style={{ marginTop: 14 }}><Skeleton h={60} n={3} /></div> : (
        <>
          <form className="askbox" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
            <label htmlFor="askq" className="sr-only">Your question</label>
            <input id="askq" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type a question, for example: who has gone quiet?" />
            <button type="submit" className="btn ap" disabled={!q.trim()}>Ask</button>
          </form>
          <div className="pills" role="group" aria-label="Suggested questions">
            {chips.map((c) => <button key={c} type="button" className="pill" onClick={() => ask(c)}>{c}</button>)}
          </div>
          {view.length === 0 ? (
            <div className="empty"><b>No questions yet</b>Pick a suggested question or type your own.</div>
          ) : view.map(({ a, order, check }, i) => (
            <section key={i} className="sec ans">
              <h3>You asked</h3>
              <div className="asked">{a.q}</div>
              {a.pending && <p className="atext" role="status">Looking at the records...</p>}
              {a.error && <p className="atext" role="alert">{a.error}</p>}
              <p className="atext">
                {a.sentences.map((s, j) => (
                  <span key={j}>{s.text}{s.refs.map((r) => <sup key={r}><button type="button" className="cite" onClick={() => (a.sources ? document.getElementById(`src-${i}-${r}`)?.scrollIntoView({ block: "nearest" }) : open(r))} aria-label={`Source ${order.indexOf(r) + 1}: ${r}`}>[{order.indexOf(r) + 1}]</button></sup>)} </span>
                ))}
              </p>
              {a.sources && a.sources.length > 0 && (
                <ol className="sources" aria-label="Sources">
                  {order.map((r) => <li key={r} id={`src-${i}-${r}`}><span className="sm">[{order.indexOf(r) + 1}] {a.sources!.find((s) => String(s.n) === r)?.label ?? r}</span></li>)}
                </ol>
              )}
              {!a.sources && order.length > 0 && (
                <ol className="sources" aria-label="Sources">
                  {order.map((r) => <li key={r}><EvChip id={r} /> <span className="sm">{state ? findEvidence(state, r)?.text : ""}</span></li>)}
                </ol>
              )}
              {!a.pending && !a.error && <div className={`numchk ${check.ok ? "ok" : "bad"}`}>{check.ok ? "✓ Numbers checked against the data" : `⚠ ${check.unknown.length ? `Not found in the data: ${check.unknown.join(", ")}` : "Some numbers could not be matched to the data"}`}</div>}
            </section>
          ))}
        </>
      )}
    </main>
  );
}
