import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useCare } from "../../api/CareProvider";
import { DraftCard } from "../../components/DraftCard";
import { useDecide } from "../../components/doctorKit";
import { setSoundOn, soundOn, useQuestionNotify } from "../../components/QuestionNotify";
import { Skeleton } from "../../components/ui";
import { isQuestion, sortQuestions } from "../../api/questions";
import { QuestionCard } from "./QuestionCard";
import { DocumentCard } from "./DocumentCard";

type F = "waiting" | "done" | "all";

export default function RequestsPage() {
  const { state } = useCare();
  const decide = useDecide();
  const notify = useQuestionNotify();
  const [params] = useSearchParams();
  const focus = params.get("focus");
  const [f, setF] = useState<F>("waiting");
  const [sound, setSound] = useState(soundOn);
  const list = useMemo(() => (state?.requests ?? []).filter((r) => !r.archived), [state?.requests]);
  const waiting = list.filter((r) => r.status === "waiting").length;
  const urgent = list.filter((r) => r.status === "waiting" && r.research?.priority === "urgent").length;
  const shown = useMemo(() => sortQuestions(list.filter((r) => (f === "all" ? true : f === "waiting" ? r.status === "waiting" : r.status !== "waiting"))), [list, f]);
  const failed = state?.loadErrors?.includes("requests");

  useEffect(() => { notify.pageSeen(); }, [state?.requests.length]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!focus || !state) return;
    const target = list.find((r) => r.id === focus);
    if (target && target.status !== "waiting") setF("all");
    notify.open(focus);
    const t = window.setTimeout(() => document.getElementById(`q-${focus}`)?.scrollIntoView({ block: "center", behavior: "smooth" }), 80);
    return () => window.clearTimeout(t);
  }, [focus, !!state, list.length]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main className="main wide" aria-labelledby="h-req">
      <h1 id="h-req">Patient requests</h1>
      <div className="sub">Questions and documents from Telegram and the patient app. Your reply goes to the patient once you send it. Press ? for keyboard shortcuts.</div>
      {!state ? (
        <div style={{ marginTop: 14 }}><Skeleton h={160} n={2} /></div>
      ) : (
        <>
          <div className="pills wrap" role="group" aria-label="Filter requests" style={{ marginTop: 12 }}>
            {([["waiting", `Waiting ${waiting}`], ["done", `Answered ${list.length - waiting}`], ["all", `All ${list.length}`]] as [F, string][]).map(([k, label]) => (
              <button key={k} type="button" className={`pill${f === k ? " on" : ""}`} aria-pressed={f === k} onClick={() => setF(k)}>{label}</button>
            ))}
            {urgent > 0 && <span className="qchip pr-urgent" style={{ alignSelf: "center" }}>⚠ {urgent} urgent</span>}
            <label className="qsound"><input type="checkbox" checked={sound} onChange={(e) => { setSound(e.target.checked); setSoundOn(e.target.checked); }} /> Sound for new questions</label>
          </div>
          {failed && list.length === 0 ? (
            <div className="empty" role="alert"><b>Could not load patient requests</b>The server did not answer. Nothing is lost.{" "}
              <button type="button" className="btn ed" onClick={() => window.dispatchEvent(new Event("cm-session"))}>Try again</button></div>
          ) : shown.length === 0 ? (
            <div className="empty"><b>{f === "waiting" ? "No questions waiting" : "No patient requests here"}</b>When a patient asks something it will show here, and you will see a notice.</div>
          ) : (
            <div className="req-list">
              {shown.map((r) =>
                r.document ? (
                  <DocumentCard key={r.id} r={r} focused={r.id === focus} />
                ) : isQuestion(r) ? (
                  <QuestionCard key={r.id} r={r} focused={r.id === focus} />
                ) : (
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
                ),
              )}
            </div>
          )}
        </>
      )}
    </main>
  );
}
