import { LogoutLink } from "../../auth/session";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCare } from "../../api/CareProvider";
import { useExtras } from "../../api/patientExtras";
import { useLang } from "../../components/i18n";
import { MockBadge, Skeleton } from "../../components/ui";
import { Empty } from "../PatientApp/Common";
import { fmtMsgDay } from "../PatientApp/Messages";
import { LangToggle, OfflineBanner } from "../PatientApp/Shell";
import { ME } from "../PatientApp/parts";
import { USE_MOCK } from "../../api";
import { usePortal } from "../PatientApp/usePortal";
import "../../styles/patient.css";
import "../PatientApp/extra.css";

/** Family helper view. Shows only what the patient allowed. */
export default function SupporterApp() {
  const { t, lang } = useLang();
  const { state, dispatch } = useCare();
  const [ex] = useExtras();
  const [q, setQ] = useState("");
  const [sent, setSent] = useState(false);
  const v = usePortal();
  const today = state?.dose.today ?? "none";
  const week = v.sup.week(today);
  const msgs = v.sup.messages;
  const P = { name: v.sup.patientName, code: v.code };
  const SUPPORTER = { name: v.sup.supporterName, relation: v.sup.relation };
  const who = SUPPORTER.relation ? `${SUPPORTER.name} (${SUPPORTER.relation})` : SUPPORTER.name;
  const allowed = v.sup.allowed;
  const loc = lang === "te" ? "te-IN" : "en-IN";
  const dayName = (i: number) => { const d = new Date(); d.setDate(d.getDate() - (6 - i)); return d.toLocaleDateString(loc, { weekday: "short" }); };
  const mark = () => { v.markBySupporter(); dispatch({ t: "dose", value: { today: "taken" } }); };
  const ask = () => {
    const text = q.trim();
    if (!text) return;
    dispatch({ t: "newRequest", req: { id: `sup-${Date.now()}`, patientCode: v.code || (USE_MOCK ? ME : ""), kind: "Supporter question", text: USE_MOCK ? `(From Supporter ${SUPPORTER.name}) ${text}` : text, /* live: the server adds the "From Supporter" label itself */ when: "today, just now", draft: "Thank you for your message. Your care team will reply soon.", status: "waiting" } });
    setQ(""); setSent(true);
  };
  return (
    <div className={`pat${ex.largeText ? " lt" : ""}`}>
      <header className="top" style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: "12px 24px", maxWidth: 1100, margin: "0 auto" }}><span className="l" style={{ fontWeight: 700, color: "var(--teal)" }}>CareMemory · {t("spTitle")}</span><LangToggle /><MockBadge /></header>
      <main style={{ margin: "0 auto" }}>
        <OfflineBanner />
        <h1>{t("spFor", { n: P.name })}</h1>
        <div className="sub">{[P.code, who].filter(Boolean).join(" · ")}</div>
        {!state ? <div className="col"><Skeleton h={150} /><Skeleton h={90} /></div> : (
          <div className="grid">
            <div className="col">
              <section className={`card big${today === "taken" ? " done" : ""}`} aria-labelledby="sp-t">
                <div className="t" id="sp-t">{t("spToday", { n: P.name })}</div>
                {allowed ? <div className="v" aria-live="polite">{today === "none" ? t("notTaken") : today === "taken" ? `✓ ${t("taken")}` : t("missedToday")}</div> : <div className="s" role="status">{t("spNotAllowed", { n: P.name })}</div>}
                {today === "none" && allowed && <button type="button" className="btn" onClick={mark}>{t("spTaken", { n: P.name })}</button>}
                {today === "taken" && v.supporterMarked && <span className="badge a">{t("spDone")}</span>}
              </section>
              <section className="card" aria-labelledby="wk">
                <div className="k" id="wk">{t("spWeek")}</div>
                {(!allowed || week.length === 0) && <div className="s">{t("spNoWeek")}</div>}
                <div className="strip">
                  {allowed && week.map((c, i) => (
                    <div key={i} className={c} role="img" aria-label={`${dayName(i)}: ${c === "o" ? t("dTaken") : c === "m" ? t("dMissed") : t("legToday")}`}>
                      {dayName(i)}<b aria-hidden="true">{c === "o" ? "✓" : c === "m" ? "✕" : "·"}</b>
                    </div>
                  ))}
                </div>
              </section>
              <p className="card s" role="note">{t("spConsent", { n: P.name })}</p>
            </div>
            <div className="col">
              <section className="card" aria-labelledby="sm">
                <div className="k" id="sm">{t("spMsgs")}</div>
                {msgs.length === 0 ? <Empty title={t("spNoMsgs")} /> : msgs.map((m, i) => (
                  <div key={m.id} className={`med${i === 0 ? " first" : ""}`}><div style={{ minWidth: 0 }}><b>{m.title}</b><span>{fmtMsgDay(m, lang)} · {m.text}</span></div></div>
                ))}
              </section>
              <section className="card" aria-labelledby="sa">
                <div className="k" id="sa">{t("spAsk")}</div>
                <label className="sr-only" htmlFor="sq">{t("spAskPh")}</label>
                <textarea id="sq" className="box" placeholder={t("spAskPh")} value={q} maxLength={500} onChange={(e) => setQ(e.target.value)} />
                <button type="button" className="btn" disabled={!q.trim()} onClick={ask}>{t("spAsk")}</button>
                <div className="s" role="status" style={{ marginTop: 8, minHeight: 20 }}>{sent ? `✓ ${t("spSent")}` : ""}</div>
              </section>
              <LogoutLink className="nl">{t("switchRole")} ›</LogoutLink>
            </div>
          </div>
        )}
        <p className="disc">{t("disc")}</p>
      </main>
    </div>
  );
}
