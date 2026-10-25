import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Decision } from "../api";
import { useCare } from "../api/CareProvider";
import { EvChips, SlaOf } from "./doctorKit";
import { splitCitations } from "../api/mapping";
import { bannedTerms, friendlyDecisionError } from "../api/questions";

interface Props {
  heading: string;
  who?: string; // patient code line
  asked?: string;
  meta?: string;
  draft: string;
  status: Decision;
  reply?: string;
  onDecide: (d: "approved" | "declined", text: string) => void | Promise<void>; // a rejected promise is the server refusing the reply
  lead?: ReactNode; // e.g. checkbox
  tone?: "req" | "plain";
  srcId?: string; // request or approval id, to show Sent / Seen
  refs?: string[]; // evidence chips
  why?: string;
  due?: { dueMin?: number; createdAt?: number };
  channel?: string;
  onLoadDraft?: () => void; // live mode: the draft text is fetched when the card is opened
}

/** What the patient will see: a small phone-style preview of the exact message. */
export function PhonePreview({ text, channel = "Telegram" }: { text: string; channel?: string }) {
  return (
    <div className="phone" aria-label="What the patient will see">
      <div className="pbar">{channel}</div>
      <div className="bubble">{text || "(empty message)"}</div>
    </div>
  );
}

function Delivery({ srcId }: { srcId: string }) {
  const { state, dispatch } = useCare();
  const m = state?.messages.find((x) => x.srcId === srcId);
  const sent = m?.status === "sent";
  useEffect(() => {
    if (!sent) return;
    const t = window.setTimeout(() => dispatch({ t: "seen", srcId }), 4000); // mock: the patient opens it a few seconds later
    return () => window.clearTimeout(t);
  }, [sent, srcId, dispatch]);
  if (!m) return null;
  return (
    <div className="deliv" aria-live="polite">
      <span className="step on">✓ Sent {m.at.replace("today ", "")}</span>
      <span className={`step${m.status === "seen" ? " on" : ""}`}>{m.status === "seen" ? "✓ Seen by patient" : "… Waiting to be seen"}</span>
    </div>
  );
}

/** AI draft + Approve and send / Edit / Decline. Nothing is sent until the doctor approves. */
export function DraftCard({ heading, who, asked, meta, draft, status, reply, onDecide, lead, tone = "plain", srcId, refs, why, due, channel, onLoadDraft }: Props) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(draft);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);
  const tid = useId();
  useEffect(() => { if (draft && !text) setText(draft); }, [draft]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (editing) area.current?.focus(); }, [editing]);
  const ready = !!text.trim();
  const flagged = bannedTerms(text);
  const decide = async (d: "approved" | "declined") => {
    setBusy(true);
    setErr("");
    try {
      await onDecide(d, d === "approved" ? text.trim() : text);
    } catch (e) {
      setErr(friendlyDecisionError(e));
    } finally {
      setBusy(false);
    }
  };
  const shown = splitCitations(text);
  const allRefs = [...new Set([...(refs ?? []), ...shown.refs])];

  if (status === "approved") {
    return (
      <section className="sec done" aria-live="polite" data-k>
        <h3>{heading}: approved</h3>
        {who && <div className="who"><Link to={`/doctor/patients/${who}`}>{who}</Link></div>}
        {asked && <div className="q">"{asked}"</div>}
        <div><b>✓ Approved and sent to the patient.</b> <span className="sub">"{splitCitations(reply ?? draft).clean}"</span></div>
        {srcId && <Delivery srcId={srcId} />}
        <EvChips ids={allRefs} />
      </section>
    );
  }
  if (status === "declined") {
    return (
      <section className="sec no" aria-live="polite" data-k>
        <h3>{heading}: declined</h3>
        {who && <div className="who"><Link to={`/doctor/patients/${who}`}>{who}</Link></div>}
        {asked && <div className="q">"{asked}"</div>}
        <div><b>Declined.</b> <span className="sub">The patient is told to call the clinic.</span></div>
      </section>
    );
  }
  return (
    <section className={tone === "req" ? "sec req" : "sec"} data-k>
      <h3>{heading}{due && <SlaOf item={due} />}</h3>
      {lead}
      {who && <div className="who"><Link to={`/doctor/patients/${who}`}>{who}</Link></div>}
      {asked && <div className="asked">"{asked}"</div>}
      {meta && <div className="q">{meta}</div>}
      {why && <div className="q">Why: {why} <EvChips ids={allRefs} /></div>}
      {!why && <EvChips ids={allRefs} />}
      {!draft && !text && onLoadDraft ? (
        <div className="draft"><button type="button" className="btn ed" onClick={onLoadDraft}>Open draft</button></div>
      ) : editing ? (
        <>
          <span className="ai">EDITING DRAFT</span>
          <label className="sr-only" htmlFor={`d-${tid}`}>Edit the reply</label>
          <textarea id={`d-${tid}`} ref={area} className="draft" value={text} onChange={(e) => { setText(e.target.value); setErr(""); }} />
        </>
      ) : (
        <div className="draft"><span className="ai">AI DRAFT</span><br />{ready ? shown.clean : <span className="qwarn" role="status">Draft not ready</span>}</div>
      )}
      {flagged.length > 0 && <p className="qwarn" role="alert">This reply has words that cannot be sent to patients ({flagged.join(", ")}). The server will block it. Please remove them.</p>}
      {err && <p className="qerr" role="alert">{err}</p>}
      {ready && (
        <details className="prev" open>
          <summary>What the patient will see</summary>
          <PhonePreview text={shown.clean} channel={channel ?? (tone === "req" ? "Patient app" : "Telegram")} />
        </details>
      )}
      <div className="btns">
        <button type="button" className="btn ap" disabled={!ready || busy} onClick={() => void decide("approved")}>{!ready ? "Draft not ready" : busy ? "Sending..." : "✓ Approve and send"}</button>
        <button type="button" className="btn ed" disabled={busy} onClick={() => setEditing((e) => !e)}>{editing ? "Done editing" : "Edit"}</button>
        <button type="button" className="btn rj" disabled={busy} onClick={() => void decide("declined")}>Decline</button>
      </div>
    </section>
  );
}
