import { useState } from "react";
import { useCare } from "../../api/CareProvider";
import { USE_MOCK, type Approval } from "../../api";
import { DraftCard } from "../../components/DraftCard";
import { useDecide } from "../../components/doctorKit";
import { dueAtOf } from "../../api/derive";
import { Skeleton } from "../../components/ui";

const LANES: { key: Approval["lane"]; label: string; cls: string; help: string }[] = [
  { key: "red", label: "RED", cls: "t-red", help: "Needs you now" },
  { key: "amber", label: "AMBER", cls: "t-amb", help: "Needs you today" },
  { key: "green", label: "GREEN", cls: "t-grn", help: "Routine, safe to approve together" },
];

export default function ApprovalsPage() {
  const { state, loadDetail } = useCare();
  const decide = useDecide();
  const [sort, setSort] = useState<"time" | "patient">("time");
  const [picked, setPicked] = useState<string[]>([]);

  const greens = state?.approvals.filter((a) => a.lane === "green" && a.status === "waiting") ?? [];
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const chosen = picked.filter((id) => greens.some((g) => g.id === id));
  const bulk = () => {
    decide.approvals(chosen, "approved");
    setPicked([]);
  };

  return (
    <main className="main wide" aria-labelledby="h-appr">
      <h1 id="h-appr">Approvals</h1>
      <div className="sub">Messages written by the assistant. Nothing is sent until you approve it. Press ? for keyboard shortcuts.</div>
      <div className="pills" role="group" aria-label="Sort drafts" style={{ marginTop: 10 }}>
        <span className="sub" style={{ alignSelf: "center" }}>Sort by</span>
        {([["time", "Time remaining"], ["patient", "Patient code"]] as const).map(([k, l]) => (
          <button key={k} type="button" className={`pill${sort === k ? " on" : ""}`} aria-pressed={sort === k} onClick={() => setSort(k)}>{l}</button>
        ))}
      </div>
      {!state ? (
        <div style={{ marginTop: 14 }}><Skeleton h={150} n={3} /></div>
      ) : state.approvals.length === 0 ? (
        <div className="empty" style={{ marginTop: 14 }}><b>Nothing to approve</b>New drafts will appear here.</div>
      ) : (
        <div className="lanes">
          {LANES.map((l) => {
            const items = state.approvals.filter((a) => a.lane === l.key).sort((a, b) =>
              (a.status === "waiting" ? 0 : 1) - (b.status === "waiting" ? 0 : 1) ||
              (sort === "time" ? dueAtOf(state, a) - dueAtOf(state, b) : a.patientCode.localeCompare(b.patientCode)));
            const waiting = items.filter((a) => a.status === "waiting").length;
            return (
              <section key={l.key} className="lane" aria-labelledby={`lane-${l.key}`}>
                <h2 id={`lane-${l.key}`}><span className={`tag ${l.cls}`}>{l.label}</span>{waiting} waiting</h2>
                <div className="sub" style={{ marginBottom: 8 }}>{l.help}</div>
                {l.key === "green" && waiting > 0 && (
                  <div className="bulk">
                    <button type="button" className="btn ed" onClick={() => setPicked(chosen.length === greens.length ? [] : greens.map((g) => g.id))}>
                      {chosen.length === greens.length ? "Clear selection" : "Select all green"}
                    </button>
                    <button type="button" className="btn ap" disabled={chosen.length === 0} onClick={bulk}>✓ Approve selected ({chosen.length})</button>
                  </div>
                )}
                {items.length === 0 && <div className="empty">Nothing here</div>}
                {items.map((a) => (
                  <DraftCard
                    key={a.id}
                    heading={a.title}
                    who={a.patientCode}
                    draft={a.draft}
                    status={a.status}
                    reply={a.reply}
                    srcId={a.id}
                    refs={a.refs}
                    why={a.why}
                    due={l.key === "green" ? undefined : a}
                    lead={
                      l.key === "green" && a.status === "waiting" ? (
                        <label className="chk">
                          <input type="checkbox" checked={picked.includes(a.id)} onChange={() => toggle(a.id)} />
                          Select {a.patientCode}
                        </label>
                      ) : undefined
                    }
                    onLoadDraft={USE_MOCK ? undefined : () => loadDetail(a.id)}
                    onDecide={(d, text) => decide.approvals([a.id], d, text)}
                  />
                ))}
              </section>
            );
          })}
        </div>
      )}
    </main>
  );
}
