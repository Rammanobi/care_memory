import { Link } from "react-router-dom";
import { useCare } from "../../api/CareProvider";
import { buildRow, treatmentDay } from "../../api/derive";
import { DraftCard } from "../../components/DraftCard";
import { EvChip, useDecide } from "../../components/doctorKit";
import { Icon } from "../../components/ui";
import { USE_MOCK } from "../../api";

/** Pending request and approval cards for one patient. */
export function Drafts({ code }: { code: string }) {
  const { state, loadDetail } = useCare();
  const decide = useDecide();
  if (!state) return null;
  const reqs = state.requests.filter((r) => r.patientCode === code && !r.archived);
  const aps = state.approvals.filter((a) => a.patientCode === code && a.lane !== "green");
  return (
    <>
      {reqs.map((r) => (
        <DraftCard key={r.id} tone="req" heading="Patient asked" asked={r.text} meta={`From the patient app, ${r.when}`} draft={r.draft} status={r.status} reply={r.reply}
          srcId={r.id} refs={r.refs} due={r.status === "waiting" ? r : undefined} onDecide={(d, text) => decide.request(r.id, d, text)} />
      ))}
      {aps.map((a) => (
        <DraftCard key={a.id} heading={`Next step: ${a.title}`} draft={a.draft} status={a.status} reply={a.reply} srcId={a.id} refs={a.refs} why={a.why} onLoadDraft={USE_MOCK ? undefined : () => loadDetail(a.id)}
          due={a.status === "waiting" ? a : undefined} onDecide={(d, text) => decide.approvals([a.id], d, text)} />
      ))}
    </>
  );
}

export function Changes({ code }: { code: string }) {
  const { state } = useCare();
  const p = state?.patients.find((x) => x.code === code);
  if (!state || !p) return null;
  const dose = code === "PT-0142" && state.dose.today === "missed" ? state.dose.reason : undefined;
  return (
    <section className="sec">
      <h3>What changed (cited)</h3>
      {p.changes.map((c, i) => (
        <span key={c.ev}>{i > 0 && "; "}{c.text} <EvChip id={c.ev} /></span>
      ))}
      .
      {dose && <div className="q" style={{ marginTop: 8 }}>Patient note today: {dose}</div>}
    </section>
  );
}

export function Snapshot({ code }: { code: string }) {
  const { state } = useCare();
  const p = state?.patients.find((x) => x.code === code);
  if (!state || !p) return null;
  return (
    <section className="sec">
      <h3>Snapshot</h3>
      <div className="kv">
        <div><span>Treatment day</span><b>{treatmentDay(state, p)} of 180</b></div>
        <div><span>Next visit</span><b>{p.nextVisit}</b></div>
        <div><span>Supporter</span><b>{p.supporter}</b></div>
        <div><span>Consent</span><b className={p.consent === "Active" ? "okc" : "warnc"}>{p.consent}</b></div>
      </div>
    </section>
  );
}

/** Side summary next to the patient list (full-screen sheet on a phone). */
export function PatientDetail({ code, open, onClose }: { code: string; open: boolean; onClose: () => void }) {
  const { state } = useCare();
  if (!state) return null;
  const p = state.patients.find((x) => x.code === code);
  if (!p) {
    return (
      <aside className={`side${open ? " open" : ""}`} aria-label="Patient detail">
        <button type="button" className="back" onClick={onClose}><Icon name="back" />All patients</button>
        <div className="empty"><b>Patient not found</b>Pick a patient from the list.</div>
      </aside>
    );
  }
  const row = buildRow(p, state);
  return (
    <aside className={`side${open ? " open" : ""}`} aria-label={`Detail for ${code}`}>
      <button type="button" className="back" onClick={onClose}><Icon name="back" />All patients</button>
      <div className="sh">
        <h2>{p.code}</h2>
        <span className={`tag ${row.tagClass}`}>{row.tag}</span>
        <Link className="btn ed small" to={`/doctor/patients/${p.code}`} style={{ marginLeft: "auto" }}>Open full record ›</Link>
      </div>
      <Drafts code={code} />
      <Changes code={code} />
      <Snapshot code={code} />
    </aside>
  );
}
