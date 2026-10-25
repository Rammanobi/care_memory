import { useEffect, useMemo, useState } from "react";
import { useCare } from "../../api/CareProvider";
import { findEvidence } from "../../api/derive";
import { checkNumbers } from "../../api/numberCheck";
import { askServer, isLive, suggestionsServer } from "../../api/serverCalls";
import type { AskSource } from "../../api/mapping";
import { ABSTAIN_TEXT, parseCitations, scopedQuestion, type CiteSnippet } from "../../api/citations";
import { cap, CHIPS, mockReply, PATIENT_CHIPS, type Sentence } from "./mockAnswer";
import { EvChip, useEvidence } from "../../components/doctorKit";
import { Skeleton } from "../../components/ui";

interface Answer { q: string; sentences: Sentence[]; sources?: AskSource[]; verified?: boolean; refused?: boolean; record?: { text: string; cites: Record<string, CiteSnippet>; abstain: boolean }; scope?: string; error?: string; pending?: boolean }

/** Render "[1]" markers inside answer text as superscript chips; `onMark` jumps to that source. */
function withMarkers(text: string, onMark: (n: string) => void) {
  return text.split(/(\[\d{1,2}\])/).map((part, k) => {
    const m = part.match(/^\[(\d{1,2})\]$/);
    return m ? <sup key={k}><button type="button" className="cite" onClick={() => onMark(m[1])} aria-label={`Source ${m[1]}`}>{part}</button></sup> : <span key={k}>{part}</span>;
  });
}

function RecordAnswer({ rec, open }: { rec: NonNullable<Answer["record"]>; open: (id: string, s?: CiteSnippet) => void }) {
  if (rec.abstain) {
    return (
      <div className="abstain" role="status">
        <b>{ABSTAIN_TEXT}</b>
        <span className="sm">The system only answers from cited records.</span>
      </div>
    );
  }
  return (
    <p className="atext">
      {parseCitations(rec.text, rec.cites).map((g, k) => g.t === "text" ? <span key={k}>{g.v}</span> : (
        <button key={k} type="button" className={`ev rc${g.known ? "" : " unk"}`} onClick={() => open(g.ref, rec.cites[g.ref])} aria-label={`Open record ${g.ref}`}>{g.ref}</button>
      ))}
    </p>
  );
}

/** The Ask box. `scope` (a patient code) pre-scopes it: the code leads the question text, the API has no patient field. */
export function AskPanel({ scope: scope0 }: { scope?: string }) {
  const [scope, setScope] = useState<string | null>(scope0 ?? null);
  const { state } = useCare();
  const open = useEvidence();
  const [q, setQ] = useState("");
  const [history, setHistory] = useState<Answer[]>([]);
  const [serverChips, setServerChips] = useState<string[] | null>(null);
  useEffect(() => {
    if (isLive && !scope) suggestionsServer().then((c) => c.length && setServerChips(c)).catch(() => undefined);
  }, [scope]);
  // Patient-specific chips only while the box is scoped to a patient: clearing the scope resets them.
  const chips = scope ? (isLive ? CHIPS : [...PATIENT_CHIPS, ...CHIPS]) : serverChips ?? CHIPS;
  const ask = (text: string) => {
    if (!state || !text.trim()) return;
    const qt = text.trim();
    const sent = scopedQuestion(scope, qt);
    setQ("");
    if (!isLive) {
      return setHistory((h) => [{ ...mockReply(qt, scope, state), q: qt, scope: scope ?? undefined }, ...h]);
    }
    const stamp: Answer = { q: qt, scope: scope ?? undefined, sentences: [], pending: true };
    setHistory((h) => [stamp, ...h]);
    const settle = (a: Answer) => setHistory((h) => h.map((x) => (x === stamp ? a : x)));
    askServer(sent)
      .then((r) => settle({ q: qt, scope: scope ?? undefined, sentences: r.sentences, sources: r.sources, verified: r.verified, refused: r.refused, record: r.record }))
      .catch((e: unknown) => settle({ q: qt, scope: scope ?? undefined, sentences: [], error: e instanceof Error ? e.message : "The question could not be answered." }));
  };

  const view = useMemo(() => history.map((a) => {
    const order: string[] = [];
    a.sentences.forEach((s) => s.refs.forEach((r) => !order.includes(r) && order.push(r)));
    const text = a.sentences.map((s) => s.text).join(" ");
    const check = a.verified !== undefined ? { ok: a.verified, unknown: [] as string[] } : state ? checkNumbers(text, state) : { ok: true, unknown: [] as string[] };
    return { a, order, check };
  }), [history, state]);

  return (
    <>
      {!state ? <div style={{ marginTop: 14 }}><Skeleton h={60} n={3} /></div> : (
        <>
          <form className="askbox" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
            {scope && <span className="scope" data-testid="scope-pill">Asking about {scope}<button type="button" onClick={() => setScope(null)}>Clear</button></span>}
            <label htmlFor="askq" className="sr-only">Your question</label>
            <input id="askq" style={{ flex: "1 1 0", minWidth: 0 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder={scope ? `Ask about ${scope}, for example: why were evening doses missed?` : "Type a question, for example: who has gone quiet?"} />
            <button type="submit" className="btn ap" style={{ flex: "0 0 auto", width: "auto" }} disabled={!q.trim()}>Ask</button>
          </form>
          <div className="pills" role="group" aria-label="Suggested questions" style={{ flexWrap: "wrap", overflowX: "visible" }}>
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
              {a.scope && <div className="sm">About {a.scope}</div>}
              {a.record && <RecordAnswer rec={a.record} open={open} />}
              <p className="atext">
                {a.sentences.map((s, j) => (
                  <span key={j}>{withMarkers(cap(s.text), (n) => document.getElementById(`src-${i}-${n}`)?.scrollIntoView({ block: "nearest" }))}{s.refs.map((r) => <sup key={r}><button type="button" className="cite" onClick={() => (a.sources ? document.getElementById(`src-${i}-${r}`)?.scrollIntoView({ block: "nearest" }) : open(r))} aria-label={`Source ${order.indexOf(r) + 1}: ${r}`}>[{order.indexOf(r) + 1}]</button></sup>)} </span>
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
              {!a.pending && !a.error && !a.record && <div className={`numchk ${check.ok ? "ok" : "bad"}`}>{check.ok ? "✓ Numbers checked against the data" : `⚠ ${check.unknown.length ? `Not found in the data: ${check.unknown.join(", ")}` : "Some numbers could not be matched to the data"}`}</div>}
            </section>
          ))}
        </>
      )}
    </>
  );
}

export default function AskPage() {
  return (
    <main className="main wide" aria-labelledby="h-ask">
      <h1 id="h-ask">Ask</h1>
      <div className="sub">Ask about your patients. Answers use only the records in this clinic, and every claim has a source.</div>
      <AskPanel />
    </main>
  );
}
