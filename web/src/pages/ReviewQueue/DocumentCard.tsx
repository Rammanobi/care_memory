// A patient-uploaded file waiting for the doctor: what was read from it, how sure the reading is, and Approve / Reject.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCare } from "../../api/CareProvider";
import { confidenceLevel, confidenceText, fmtSize } from "../../api/documents";
import { friendlyDecisionError } from "../../api/questions";
import type { PatientRequest } from "../../api";
import { useQuestionNotify } from "../../components/QuestionNotify";

const TYPE_LABEL: Record<string, string> = { lab_slip: "Lab slip", visit_summary: "Visit summary", letter: "Letter", prescription: "Prescription", other: "Other" };
const typeLabel = (t: string) => TYPE_LABEL[t] ?? (t ? t.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) : "Type not recognised");

export function DocumentCard({ r, focused }: { r: PatientRequest; focused?: boolean }) {
  const d = r.document!;
  const { dispatchAsync } = useCare();
  const notify = useQuestionNotify();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const decide = async (decision: "approved" | "declined") => {
    setBusy(true);
    setErr("");
    try {
      await dispatchAsync({ t: "decideRequest", id: r.id, decision });
      notify.open(r.id);
    } catch (e) {
      setErr(friendlyDecisionError(e));
    } finally {
      setBusy(false);
    }
  };

  const meta = [typeLabel(d.docType), d.size ? fmtSize(d.size) : "", d.pages ? `${d.pages} page${d.pages === 1 ? "" : "s"}` : ""].filter(Boolean).join(" · ");
  const lowCount = d.fields.filter((f) => confidenceLevel(f.confidence) === "low").length;
  return (
    <section id={`q-${r.id}`} className={`sec ${r.status === "waiting" ? "req" : r.status === "approved" ? "done" : "no"} qcard dcard${focused ? " qfocus" : ""}`} data-k onFocusCapture={() => notify.open(r.id)} onClick={() => notify.open(r.id)}>
      <div className="qhead">
        <Link to={`/doctor/patients/${r.patientCode}`} className="qcode">{r.patientCode}</Link>
        <span className="qchip">Document</span>
        {d.status && <span className="qchip dstatus">{d.status}</span>}
        <span className="sub qwhen">{r.when}</span>
      </div>
      <p className="dname"><b>{d.filename}</b></p>
      <p className="sub">{meta}</p>
      {/* TODO: add a "Download original" link once the backend exposes a doctor download route. None exists yet, so none is shown. */}
      <p className="qnote dnote">Prepared automatically from the file. Check it against the original before approving.</p>
      <section className="qres" aria-label="Fields read from the file">
        <h4>Fields read from the file{lowCount > 0 && <span className="qconf">{lowCount} to double-check</span>}</h4>
        {d.fields.length === 0 ? <p className="sub">Nothing could be read from this file. Check the original.</p> : (
          <table className="dfields">
            <thead><tr><th scope="col">Field</th><th scope="col">Value</th><th scope="col">Confidence</th></tr></thead>
            <tbody>
              {d.fields.map((f, i) => {
                const lv = confidenceLevel(f.confidence);
                return (
                  <tr key={i} className={lv === "low" || lv === "unknown" ? "dlow" : ""}>
                    <th scope="row">{f.name}</th>
                    <td>{f.value || "-"}</td>
                    <td><span className={`dconf c-${lv}`}>{lv === "low" ? "⚠ " : ""}{confidenceText(f.confidence)}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {d.textExcerpt && <details className="dexcerpt" open><summary>Text from the file</summary><pre>{d.textExcerpt}</pre></details>}
      </section>
      {r.status === "waiting" ? (
        <>
          {err && <p className="qerr" role="alert">{err}</p>}
          <div className="btns">
            <button type="button" className="btn ap" disabled={busy} onClick={() => void decide("approved")}>{busy ? "Saving..." : "✓ Approve (add to record)"}</button>
            <button type="button" className="btn rj" disabled={busy} onClick={() => void decide("declined")}>Reject</button>
          </div>
        </>
      ) : (
        <div role="status"><b>{r.status === "approved" ? "✓ Added to the record." : "Rejected."}</b> <span className="sub">{r.status === "approved" ? "The patient sees it as added to their record." : "The patient is told it could not be used."}</span></div>
      )}
    </section>
  );
}
