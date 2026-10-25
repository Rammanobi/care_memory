import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLang, type Key } from "../../components/i18n";
import { setExtras, useExtras, type Consents } from "../../api/patientExtras";
import { LangToggle } from "./Shell";
import { Toggle } from "./Common";
import { usePortal } from "./usePortal";

export const CHANNELS: { k: keyof Consents; name: Key; desc: Key }[] = [
  { k: "telegram", name: "chTg", desc: "chTgD" },
  { k: "gmail", name: "chGm", desc: "chGmD" },
  { k: "calendar", name: "chCal", desc: "chCalD" },
];

export type ConsentKey = keyof Consents | "supporter";

export function ChannelSwitches({ onAsk }: { onAsk?: (k: ConsentKey) => void }) {
  const { t } = useLang();
  const v = usePortal();
  return (
    <div>
      {CHANNELS.map((c, i) => (
        <div key={c.k} className={`sw${i === 0 ? " first" : ""}`}>
          {/* Telegram off: the line says so, instead of promising reminders there */}
          <div className="tx"><b>{t(c.name)}</b><span>{c.k === "telegram" && !v.consents.telegram ? t("chTgOff") : t(c.desc)}</span></div>
          <Toggle on={v.consents[c.k]} label={t(c.name)} onChange={(on) => (!on && onAsk ? onAsk(c.k) : v.setConsent(c.k, on))} />
        </div>
      ))}
      {v.shareSupporter && (
        <div className="sw">
          <div className="tx"><b>{t("chSup")}</b><span>{t("chSupD")}</span></div>
          <Toggle on={v.shareSupporter.on} label={t("chSup")} onChange={(on) => (!on && onAsk ? onAsk("supporter") : v.shareSupporter?.set(on))} />
        </div>
      )}
    </div>
  );
}

export default function Welcome() {
  const { t } = useLang();
  const nav = useNavigate();
  const [step, setStep] = useState(1);
  const head = useRef<HTMLHeadingElement>(null);
  // each step's heading gets focus when the step changes, so a screen reader hears where it is
  const first = useRef(true);
  useEffect(() => { if (first.current) { first.current = false; return; } head.current?.focus(); }, [step]);
  const finish = () => { setExtras({ onboarded: true }); nav("/patient"); };
  return (
    <>
      <div className="logo" style={{ fontWeight: 700, color: "var(--teal)", fontSize: 18, marginBottom: 8 }}>CareMemory</div>
      <div className="stepdots" aria-hidden="true">{[1, 2, 3].map((n) => <i key={n} className={n <= step ? "on" : ""} />)}</div>
      <div className="s" role="status">{t("wStep", { n: step })}</div>
      {step === 1 && (
        <section className="card" aria-labelledby="w1">
          <h1 id="w1" ref={head} tabIndex={-1} style={{ fontSize: 24 }}>{t("wLangT")}</h1>
          <p className="s" style={{ margin: "6px 0 14px" }}>{t("wLangS")}</p>
          <LangToggle />
        </section>
      )}
      {step === 2 && (
        <section className="card" aria-labelledby="w2">
          <h1 id="w2" ref={head} tabIndex={-1} style={{ fontSize: 24 }}>{t("wDoesT")}</h1>
          <ul className="plain">{(["wDo1", "wDo2", "wDo3"] as Key[]).map((k) => <li key={k}>✓ {t(k)}</li>)}</ul>
          <h2 style={{ fontSize: 20, marginTop: 14 }}>{t("wDontT")}</h2>
          <ul className="plain">{(["wDont1", "wDont2", "wDont3"] as Key[]).map((k) => <li key={k}>✕ {t(k)}</li>)}</ul>
        </section>
      )}
      {step === 3 && (
        <section className="card" aria-labelledby="w3">
          <h1 id="w3" ref={head} tabIndex={-1} style={{ fontSize: 24 }}>{t("wConT")}</h1>
          <p className="s" style={{ margin: "6px 0 8px" }}>{t("wConS")}</p>
          <ChannelSwitches />
        </section>
      )}
      <div className="actions" style={{ marginTop: 14 }}>
        {step > 1 && <button type="button" className="btn ghost" onClick={() => setStep(step - 1)}>{t("back")}</button>}
        {step < 3 ? <button type="button" className="btn" onClick={() => setStep(step + 1)}>{t("next")}</button> : <button type="button" className="btn" onClick={finish}>{t("startApp")}</button>}
      </div>
      <p className="disc">{t("disc")}</p>
    </>
  );
}
