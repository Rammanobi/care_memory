import { useState } from "react";
import { useCare } from "../../api/CareProvider";
import { DraftCard } from "../../components/DraftCard";
import { useDecide } from "../../components/doctorKit";
import { Skeleton } from "../../components/ui";

type F = "waiting" | "done" | "all";

export default function RequestsPage() {
  const { state } = useCare();
  const decide = useDecide();
  const [f, setF] = useState<F>("waiting");
  const list = (state?.requests ?? []).filter((r) => !r.archived);
  const waiting = list.filter((r) => r.status === "waiting").length;
  const shown = list.filter((r) => (f === "all" ? true : f === "waiting" ? r.status === "waiting" : r.status !== "waiting"));

  return (
    <main className="main wide" aria-labelledby="h-req">
      <h1 id="h-req">Patient requests</h1>
      <div className="sub">Sent from the patient app. Your reply is shown to the patient once you approve it.</div>
      {!state ? (
        <div style={{ marginTop: 14 }}><Skeleton h={160} n={2} /></div>
      ) : (
        <>
          <div className="pills" role="group" aria-label="Filter requests" style={{ marginTop: 12 }}>
            {([["waiting", `Waiting ${waiting}`], ["done", `Answered ${list.length - waiting}`], ["all", `All ${list.length}`]] as [F, string][]).map(([k, label]) => (
              <button key={k} type="button" className={`pill${f === k ? " on" : ""}`} aria-pressed={f === k} onClick={() => setF(k)}>{label}</button>
            ))}
          </div>
          {shown.length === 0 ? (
            <div className="empty"><b>No patient requests right now</b>When a patient asks something it will show here.</div>
          ) : (
            <div className="req-list">
              {shown.map((r) => (
                <DraftCard
                  key={r.id}
                  tone="req"
                  heading={`${r.patientCode} asked · ${r.kind}`}
                  asked={r.text}
                  meta={`From the patient app, ${r.when}`}
                  draft={r.draft}
                  status={r.status}
                  reply={r.reply}
                  onDecide={(d, text) => decide.request(r.id, d, text)}
                  srcId={r.id}
                  refs={r.refs}
                  due={r.status === "waiting" ? r : undefined}
                />
              ))}
            </div>
          )}
        </>
      )}
    </main>
  );
}
