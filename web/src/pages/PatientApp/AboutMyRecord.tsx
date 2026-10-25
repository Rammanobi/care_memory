// Calm "About my record" section on Home: tappable question chips, one answer open at a time (accordion).
// answer_text is the server's approved wording in the patient's language: rendered as is, never rewritten.
import { useId, useState } from "react";
import { useLang } from "../../components/i18n";
import { Skeleton } from "../../components/ui";
import { asOfWhen } from "../../api/mapping";
import type { OwnAnswer } from "../../api/types";
import { useOwnAnswers } from "./useOwnAnswers";

export const ASK_BOX_ID = "ask-box";

/** Scroll to the existing "ask your care team" box and put the cursor in its text field. */
export function goToAskBox() {
  const box = document.getElementById(ASK_BOX_ID);
  if (!box) return;
  box.scrollIntoView({ behavior: "smooth", block: "center" });
  window.setTimeout(() => document.getElementById("msg")?.focus({ preventScroll: true }), 350);
}

function AsOf({ a }: { a: OwnAnswer }) {
  const { t, lang } = useLang();
  const w = asOfWhen(a.asOf);
  if (!w) return null;
  let text: string;
  if (w.kind === "today") text = t("omUpToday");
  else if (w.kind === "yesterday") text = t("omUpYest");
  else text = t("omUpOn", { d: w.date.toLocaleDateString(lang === "te" ? "te-IN" : "en-IN", { day: "numeric", month: "short" }) });
  return <div className="s" style={{ marginTop: 6 }}>{text}</div>;
}

export function AboutMyRecord({ onAsk = goToAskBox }: { onAsk?: () => void }) {
  const { t } = useLang();
  const { s, retry } = useOwnAnswers();
  const [open, setOpen] = useState<string | null>(null);
  const uid = useId();
  return (
    <section className="card om" aria-labelledby={`${uid}-t`}>
      <div className="k" id={`${uid}-t`}>{t("omTitle")}</div>
      {s.k === "loading" && <div aria-busy="true"><Skeleton h={44} n={3} /></div>}
      {s.k === "error" && (
        <div className="wait" role="alert" style={{ marginBottom: 0 }}>
          <div>{t("omError")}</div>
          <button type="button" className="btn ghost" style={{ minHeight: 44, width: "auto", marginTop: 8 }} onClick={retry}>{t("tryAgain")}</button>
        </div>
      )}
      {s.k === "ready" && s.data.cards.length === 0 && !s.data.advice && <div className="s">{t("omEmpty")}</div>}
      {s.k === "ready" && (s.data.cards.length > 0 || s.data.advice) && (
        <>
          <div className="s" style={{ marginBottom: 6 }}>{t("omHint")}</div>
          <div className="om-list">
            {s.data.cards.map((c) => {
              const isOpen = open === c.topic;
              const pid = `${uid}-${c.topic}`;
              return (
                <div key={c.topic} className="om-item">
                  <button type="button" className="chip om-q" aria-expanded={isOpen} aria-controls={pid} onClick={() => setOpen(isOpen ? null : c.topic)}>{c.question}</button>
                  {isOpen && (
                    <div id={pid} className="wait om-a" role="region" aria-label={c.question}>
                      <div>{c.answerText}</div>
                      <AsOf a={c} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          {s.data.advice && (
            <div className="om-note" role="note">
              <div>{s.data.advice.answerText}</div>
              <button type="button" className="btn" style={{ minHeight: 44, width: "auto", marginTop: 8 }} onClick={onAsk}>{t("omAsk")}</button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
