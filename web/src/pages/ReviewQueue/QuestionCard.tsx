// One patient question on the Requests screen: the question, the prepared research, an editable reply and the decision buttons.
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useCare } from "../../api/CareProvider";
import { friendlyDeliveryError } from "../../api/mapping";
import { bannedTerms, briefParts, CATEGORY_LABEL, CHANNEL_BADGE, fmtWaited, friendlyDecisionError, PRIORITY_LABEL, SENT_TO, waitTone } from "../../api/questions";
import type { Origin, PatientRequest, Research } from "../../api";
import { EvChips, useNow } from "../../components/doctorKit";
import { useQuestionNotify } from "../../components/QuestionNotify";

const MAX_CHARS = 1000;

function Waiting({ since, priority }: { since?: number; priority: Research["priority"] }) {
  const now = useNow(15000);
  if (!since) return null;
  const ms = now - since;
  const tone = waitTone(ms, priority);
  return <span className={`sla ${tone}`} aria-label={`Waiting ${fmtWaited(ms)}`}>{tone === "late" ? "⚠ " : "⏱ "}Waiting {fmtWaited(ms)}</span>;
}

function ResearchPanel({ r }: { r?: Research }) {
  const status = r?.status ?? "pending";
  return (
    <section className="qres" aria-label="Research for the doctor" aria-live="polite">
      <h4>Research{status === "ready" && r?.confidence && <span className={`qconf c-${r.confidence}`}>Confidence: {r.confidence}</span>}</h4>
      {status === "pending" && (
        <div role="status">
          <div className="skel-line" aria-hidden="true" /><div className="skel-line short" aria-hidden="true" />
          <p className="sub">Preparing research for the doctor...</p>
        </div>
      )}
      {status === "failed" && (
        <p className="qfail" role="status">The research could not be prepared{r?.reason ? ` (${r.reason})` : ""}. You can still read the question and reply below.</p>
      )}
      {status === "ready" && r && (
        <>
          {r.brief.length === 0 ? <p className="sub">The record has nothing on this question yet.</p> : (
            <ul className="qbrief">
              {r.brief.map((b, i) => {
                const p = briefParts(b);
                return <li key={i}>{p.text} <EvChips ids={p.refs} /></li>;
              })}
            </ul>
          )}
          <p className="qnote">Prepared from the record. The decision is yours.</p>
          {(r.model || r.costUsd !== undefined) && <details className="qmeta"><summary>How this was prepared</summary>{r.model ? `Model: ${r.model}. ` : ""}{r.costUsd !== undefined ? `Cost: $${r.costUsd.toFixed(4)}.` : ""}</details>}
        </>
      )}
    </section>
  );
}

function SentLine({ id, channel }: { id: string; channel: Origin["channel"] }) {
  const { state } = useCare();
  const m = state?.messages.find((x) => x.srcId === id);
  const failed = m?.delivery === "failed";
  return (
    <div role="status">
      <b>{failed ? "✗ Not delivered" : `✓ ${SENT_TO[channel]}`}</b>
      {failed && <span className="sub"> {friendlyDeliveryError(m?.deliveryError) || "The message could not be delivered."}</span>}
    </div>
  );
}

export function QuestionCard({ r, focused }: { r: PatientRequest; focused?: boolean }) {
  const { dispatchAsync } = useCare();
  const notify = useQuestionNotify();
  const research = r.research;
  const priority = research?.priority ?? "normal";
  const category = research?.category ?? "other";
  const channel: Origin["channel"] = r.origin?.channel ?? "portal";
  const suggested = research?.suggestedReply || r.draft || "";
  const [text, setText] = useState(suggested);
  const touched = useRef(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);
  // research may arrive after the card is shown: fill the box unless the doctor already started typing
  useEffect(() => { if (!touched.current) setText(suggested); }, [suggested]);

  const flagged = bannedTerms(text);
  const decide = async (d: "approved" | "declined") => {
    setBusy(true);
    setErr("");
    try {
      await dispatchAsync({ t: "decideRequest", id: r.id, decision: d, text: d === "approved" ? text.trim() : undefined });
      notify.open(r.id);
    } catch (e) {
      setErr(friendlyDecisionError(e));
    } finally {
      setBusy(false);
    }
  };

  const head = (
    <div className="qhead">
      <Link to={`/doctor/patients/${r.patientCode}`} className="qcode">{r.patientCode}</Link>
      <span className={`qchip ch-${channel}`}>{CHANNEL_BADGE[channel]}</span>
      <span className="qchip">{CATEGORY_LABEL[category]}</span>
      <span className={`qchip pr-${priority}`}>{priority === "urgent" ? "⚠ " : ""}{PRIORITY_LABEL[priority]}</span>
      {r.status === "waiting" && <Waiting since={r.createdAt} priority={priority} />}
      <span className="sub qwhen">{r.when}</span>
    </div>
  );
  const asked = <p className="asked" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>"{r.text}"</p>;

  if (r.status === "approved") {
    return (
      <section id={`q-${r.id}`} className="sec done qcard" data-k aria-live="polite">
        {head}{asked}
        <SentLine id={r.id} channel={channel} />
        <p className="sub" style={{ overflowWrap: "anywhere" }}>"{r.reply ?? r.draft}"</p>
      </section>
    );
  }
  if (r.status === "declined") {
    return (
      <section id={`q-${r.id}`} className="sec no qcard" data-k aria-live="polite">
        {head}{asked}
        <div><b>Declined.</b> <span className="sub">The patient is told to call the clinic.</span></div>
      </section>
    );
  }
  const over = text.length > MAX_CHARS;
  return (
    <section id={`q-${r.id}`} className={`sec req qcard${priority === "urgent" ? " urgent" : ""}${focused ? " qfocus" : ""}`} data-k onFocusCapture={() => notify.open(r.id)} onClick={() => notify.open(r.id)}>
      {head}{asked}
      <ResearchPanel r={research} />
      <label className="qlabel" htmlFor={`qr-${r.id}`}>Reply to patient</label>
      <textarea
        id={`qr-${r.id}`} ref={box} className="draft qbox" value={text} rows={4} aria-describedby={`qh-${r.id}`}
        onChange={(e) => { touched.current = true; setText(e.target.value); setErr(""); }}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && text.trim() && !busy && text.length <= MAX_CHARS) { e.preventDefault(); void decide("approved"); } }}
      />
      <div id={`qh-${r.id}`} className="qhelp">
        <span className={over ? "qwarn" : ""}>{text.length} / {MAX_CHARS} characters</span>
        <span>Write in the patient's language if you can. Keep it short and plain.</span>
      </div>
      {over && <p className="qwarn" role="alert">This reply is {text.length - MAX_CHARS} characters over the {MAX_CHARS} character limit. Shorten it to {MAX_CHARS} characters or fewer to send.</p>}
      {flagged.length > 0 && <p className="qwarn" role="alert">This reply has words that cannot be sent to patients ({flagged.join(", ")}). The server will block it. Please remove them.</p>}
      {err && <p className="qerr" role="alert">{err}</p>}
      <div className="btns">
        <button type="button" className="btn ap" disabled={busy || !text.trim() || over} onClick={() => void decide("approved")}>{busy ? "Sending..." : "✓ Send reply"}</button>
        <button type="button" className="btn ed" disabled={busy} onClick={() => box.current?.focus()}>Edit reply</button>
        <button type="button" className="btn rj" disabled={busy} onClick={() => void decide("declined")}>Decline / ask me later</button>
      </div>
      <p className="sub qhint">Declining tells the patient to call the clinic. Ctrl+Enter sends from the reply box.</p>
    </section>
  );
}
