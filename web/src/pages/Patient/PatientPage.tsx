import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useCare } from "../../api/CareProvider";
import { isLive, timelineServer } from "../../api/serverCalls";
import { splitCitations, type TimelineRow } from "../../api/mapping";
import { atStamp, buildRow, clinicName, fmtAt, missedLabel, newestFirst, stripCells, treatmentDay } from "../../api/derive";
import type { EvKind } from "../../api";
import { EvChip, EvChips } from "../../components/doctorKit";
import { Icon, Skeleton } from "../../components/ui";
import { AskPanel } from "../Ask";
import { Changes, Drafts, Snapshot } from "./PatientDetail";

const TABS = ["Overview", "Timeline", "Messages", "Ask", "Notes", "Audit trail"] as const;
type Tab = (typeof TABS)[number];
const KINDS: ("all" | EvKind)[] = ["all", "dose", "refill", "visit", "message", "supporter", "lab", "system"];

export default function PatientPage() {
  const { id = "" } = useParams();
  const { state, dispatch } = useCare();
  const [tab, setTab] = useState<Tab>("Overview");
  const [kind, setKind] = useState<"all" | EvKind>("all");
  const [note, setNote] = useState("");
  const [tl, setTl] = useState<TimelineRow[] | null>(null);
  const [tlErr, setTlErr] = useState(false);
  useEffect(() => {
    if (!isLive || tab !== "Timeline") return;
    let alive = true;
    const pull = () => timelineServer(id).then((r) => { if (alive) { setTl(r); setTlErr(false); } }).catch(() => alive && setTlErr(true));
    pull();
    const i = setInterval(pull, 5000);
    return () => { alive = false; clearInterval(i); };
  }, [tab, id]);

  if (!state) return <main className="main wide"><Skeleton h={70} n={1} /><div style={{ height: 12 }} /><Skeleton h={120} n={3} /></main>;
  const p = state.patients.find((x) => x.code === id);
  if (!p) {
    return (
      <main className="main wide">
        <Link to="/doctor" className="backl"><Icon name="back" />All patients</Link>
        <div className="empty" style={{ marginTop: 14 }}><b>Patient not found</b>Check the code or go back to the list.</div>
      </main>
    );
  }
  const row = buildRow(p, state);
  const today = treatmentDay(state, p);
  const events = isLive
    ? [...(tl ?? []).filter((e) => kind === "all" || e.kind === kind)].sort((a, b) => b.day - a.day)
    : newestFirst(state.evidence.filter((e) => e.code === id && e.id.startsWith("E-") && (kind === "all" || e.kind === kind)).map((e) => ({ id: e.id, chip: true, day: atStamp(e.at, today).day, at: fmtAt(e.at, today), kind: e.kind, reporter: e.reporter, text: e.text })), (e) => e.at, today);
  const insights = state.evidence.filter((e) => e.code === id && !e.id.startsWith("E-"));
  const msgs = state.messages.filter((m) => m.code === id);
  const notes = state.notes.filter((n) => n.code === id);
  const audit = newestFirst(state.audit.filter((a) => a.code === id), (a) => a.at, today);

  const addNote = () => {
    if (!note.trim()) return;
    dispatch({ t: "addNote", note: { id: `n-${Date.now()}`, code: id, at: "today", by: "Dr. A. Rao", text: note.trim() } });
    setNote("");
  };

  return (
    <main className="main wide" aria-labelledby="h-pt">
      <Link to="/doctor" className="backl"><Icon name="back" />All patients</Link>
      <div className="sh">
        <h1 id="h-pt">{p.code}</h1>
        <span className={`tag ${row.tagClass}`}>{row.tag}</span>
        <span className="sub">{p.sex}, {p.age} · {clinicName(state, p.clinic)}</span>
      </div>
      <div role="tablist" aria-label="Patient sections" className="pills">
        {TABS.map((t) => (
          <button key={t} role="tab" type="button" aria-selected={tab === t} className={`pill${tab === t ? " on" : ""}`} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>

      {tab === "Overview" && (
        <div className="two">
          <div>
            <Drafts code={id} />
            <Changes code={id} />
          </div>
          <div>
            <Snapshot code={id} />
            <section className="sec">
              <h3>Last 20 days</h3>
              <div className="strip" aria-hidden="true">{stripCells(p).map((k, i) => <i key={i} className={k} />)}</div>
              <span className="sm">{missedLabel(p)}</span>
            </section>
            <section className="sec">
              <h3>What the system believes</h3>
              {insights.length === 0 ? <div className="q">Nothing learned yet.</div> : insights.map((e) => (
                <div key={e.id} className="li static"><div><EvChip id={e.id} /> {e.text}</div></div>
              ))}
            </section>
          </div>
        </div>
      )}

      {tab === "Timeline" && (
        <section className="sec">
          <div className="pills" role="group" aria-label="Filter events by type">
            {KINDS.map((k) => <button key={k} type="button" className={`pill${kind === k ? " on" : ""}`} aria-pressed={kind === k} onClick={() => setKind(k)}>{k === "all" ? "All" : k}</button>)}
          </div>
          {isLive && tl === null ? <div className="empty"><b>{tlErr ? "Could not load the timeline" : "Loading the timeline"}</b></div> : events.length === 0 ? <div className="empty"><b>No events</b>Nothing of this type is recorded.</div> : (
            <ol className="tl">
              {events.map((e, n) => (
                <li key={`${e.id}-${n}`}>{e.chip ? <EvChip id={e.id} /> : <span className="sm" aria-hidden="true">{e.day ? `Day ${e.day}` : ""}</span>}<div><b>{e.text}</b><div className="sm">{e.at} · {e.reporter} · {e.kind}</div></div></li>
              ))}
            </ol>
          )}
        </section>
      )}

      {tab === "Messages" && (
        <section className="sec">
          {msgs.length === 0 ? <div className="empty"><b>No messages sent yet</b>Approved messages appear here.</div> : msgs.map((m) => (
            <div key={m.id} className="msg">
              <div className="bubble">{splitCitations(m.text).clean}</div>{splitCitations(m.text).refs.length > 0 && <EvChips ids={splitCitations(m.text).refs} />}
              <div className="sm">{m.at} · {m.channel} · approved by {m.approvedBy} · version {m.version} · {m.status === "seen" ? <b>Seen</b> : !m.delivery && <b>Sent</b>}
                {m.delivery && <span className={`dchip ${m.delivery === "failed" ? "f" : m.delivery === "sent" ? "s" : "q"}`} data-testid="delivery">{m.delivery === "failed" ? `Failed${m.deliveryError ? `: ${m.deliveryError}` : ""}` : m.delivery === "sent" ? "Sent" : "Queued"}</span>}</div>
            </div>
          ))}
        </section>
      )}

      {tab === "Ask" && <section className="sec"><AskPanel scope={p.code} /></section>}

      {tab === "Notes" && (
        <section className="sec">
          <label htmlFor="note" className="sr-only">New note</label>
          <textarea id="note" className="draft" placeholder="Write a note for the care team" value={note} onChange={(e) => setNote(e.target.value)} />
          <button type="button" className="btn ap" disabled={!note.trim()} onClick={addNote}>Save note</button>
          {notes.length === 0 ? <div className="empty" style={{ marginTop: 12 }}><b>No notes yet</b>Your notes are saved here.</div> : (
            <div style={{ marginTop: 12 }}>{notes.map((n) => <div key={n.id} className="note-i"><div>{n.text}</div><div className="sm">{n.by} · {n.at}</div></div>)}</div>
          )}
        </section>
      )}

      {tab === "Audit trail" && (
        <section className="sec">
          {audit.length === 0 ? <div className="empty"><b>No audit entries</b>Decisions are logged here.</div> : (
            <div className="tbl-wrap"><table className="tbl">
              <thead><tr><th>When</th><th>Who</th><th>What</th><th>Draft version</th></tr></thead>
              <tbody>{audit.map((a) => (
                <tr key={a.id}><td>{fmtAt(a.at, today)}</td><td>{a.actor}</td><td>{a.action}{a.note && <div className="sm">{a.note}</div>}</td><td>{a.version ? `v${a.version}` : "-"}</td></tr>
              ))}</tbody>
            </table></div>
          )}
        </section>
      )}
    </main>
  );
}
