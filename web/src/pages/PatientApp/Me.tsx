import { LogoutLink } from "../../auth/session";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useCare } from "../../api/CareProvider";
import { resetExtras, setExtras, useExtras, type Consents } from "../../api/patientExtras";
import { useLang, type Key } from "../../components/i18n";
import { Confirm, Toggle } from "./Common";
import { usePortal } from "./usePortal";
import { USE_MOCK } from "../../api";
import { LangToggle } from "./Shell";
import { CHANNELS, ChannelSwitches } from "./Welcome";

const TIMES = ["6:00 am", "7:00 am", "8:00 am", "9:00 am", "12:00 pm", "6:00 pm", "7:00 pm", "8:00 pm"];

function ReminderCard() {
  const { t } = useLang();
  const { reminder } = usePortal();
  const [pick, setPick] = useState("7:00 pm");
  const [sent, setSent] = useState(false);
  const pending = reminder.pending ? { time: reminder.pending } : null;
  const current = reminder.current;
  const ask = () => { reminder.ask(pick); setSent(true); };
  return (
    <section className="card" aria-labelledby="rem-t">
      <div className="k" id="rem-t">{t("remT")}</div>
      <div className="n">{t("remNow", { t: current })}</div>
      {pending ? (
        <div className="wait" style={{ marginTop: 10 }} role="status"><span className="badge w">◔ {t("stWait")}</span><br />{t("remPend", { t: pending.time, c: current })}</div>
      ) : (
        <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
          <label htmlFor="rem-sel" className="s">{t("remPick")}</label>
          <select id="rem-sel" value={pick} onChange={(e) => setPick(e.target.value)}>{TIMES.map((x) => <option key={x}>{x}</option>)}</select>
          <button type="button" className="btn" onClick={ask}>{t("remAsk")}</button>
        </div>
      )}
      <div className="s" role="status" style={{ minHeight: 18, marginTop: 6 }}>{sent ? `✓ ${t("remSent")}` : ""}</div>
    </section>
  );
}

export default function Me() {
  const { t } = useLang();
  const { reset } = useCare();
  const nav = useNavigate();
  const [ex] = useExtras();
  const v = usePortal();
  const [revoke, setRevoke] = useState<keyof Consents | null>(null);
  const ch = CHANNELS.find((c) => c.k === revoke);
  return (
    <>
      <h1>{t("meTitle")}</h1>
      <div className="sub">{v.name} · {v.code}</div>
      <div className="grid">
        <div className="col">
          <section className="card" aria-labelledby="pf">
            <div className="k" id="pf">{t("profile")}</div>
            <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 14px" }}>
              <dt className="s">{t("nameL")}</dt><dd><b>{v.name}</b></dd>
              <dt className="s">{t("codeL")}</dt><dd><b>{v.code}</b></dd>
              <dt className="s">{t("clinic")}</dt><dd><b>{v.clinic}</b></dd>
              <dt className="s">{t("supL")}</dt><dd><b>{v.supporter ? t("supLinked", { n: `${v.supporter.name} (${v.supporter.relation})` }) : "-"}</b></dd>
            </dl>
          </section>
          <ReminderCard />
          <section className="card">
            <div className="k">{t("langName")}</div><LangToggle />
            <div className="sw" style={{ marginTop: 12 }}>
              <div className="tx"><b>{t("lgT")}</b><span>{t("lgS")}</span></div>
              <Toggle on={ex.largeText} label={t("lgT")} onChange={(v) => setExtras({ largeText: v })} />
            </div>
          </section>
        </div>
        <div className="col">
          <section className="card" aria-labelledby="ch-t"><div className="k" id="ch-t">{t("chans")}</div><ChannelSwitches onAsk={setRevoke} /></section>
          <section className="card">
            <Link className="nl" to="/patient/help">{t("helpL")} ›</Link><br />
            <Link className="nl" to="/patient/privacy">{t("privL")} ›</Link><br />
            <button type="button" className="link" onClick={() => { setExtras({ onboarded: false }); nav("/patient/welcome"); }}>{t("welcomeL")}</button><br />
            <LogoutLink className="nl">{t("switchRole")} ›</LogoutLink>
          </section>
          {USE_MOCK && <section className="card">
            <div className="k">Demo</div>
            <div className="sw first"><div className="tx"><b>{t("demoEmpty")}</b></div><Toggle on={ex.empty} label={t("demoEmpty")} onChange={(v) => setExtras({ empty: v })} /></div>
            <div className="sw"><div className="tx"><b>{t("demoOff")}</b></div><Toggle on={ex.offline} label={t("demoOff")} onChange={(v) => setExtras({ offline: v })} /></div>
            <button type="button" className="btn ghost" onClick={() => { resetExtras(); reset(); }}>Reset demo data</button>
          </section>}
        </div>
      </div>
      {ch && (
        <Confirm danger title={t("revT", { c: t(ch.name as Key) })} body={t("revS")} yes={t("revYes")} no={t("keepOn")}
          onNo={() => setRevoke(null)} onYes={() => { v.setConsent(ch.k, false); setRevoke(null); }} />
      )}
    </>
  );
}

export function Help() {
  const { t } = useLang();
  const { clinic } = usePortal();
  return (
    <>
      <Link className="nl" to="/patient/me">‹ {t("me")}</Link>
      <h1>{t("helpTitle")}</h1>
      <div className="col" style={{ marginTop: 12 }}>
        <section className="card"><div className="k">{t("clinicNo")}</div><div className="n">{clinic}</div><div className="s">{t("clinicNoV")}: 000-000-0000</div></section>
        <section className="warn" role="note"><b style={{ fontSize: 20 }}>{t("emerg")}: 108</b><p style={{ marginTop: 4, fontSize: 16 }}>{t("emergS")}</p></section>
        <section className="card"><p>{t("helpApp")}</p></section>
      </div>
    </>
  );
}

export function Privacy() {
  const { t } = useLang();
  const L = (ks: Key[]) => <ul className="plain">{ks.map((k) => <li key={k}>{t(k)}</li>)}</ul>;
  return (
    <>
      <Link className="nl" to="/patient/me">‹ {t("me")}</Link>
      <h1>{t("pvTitle")}</h1>
      <div className="grid" style={{ marginTop: 12 }}>
        <section className="card"><div className="k">{t("pvStored")}</div>{L(["pv1", "pv2", "pv3", "pv4"])}</section>
        <section className="card"><div className="k">{t("pvWho")}</div>{L(["pw1", "pw2", "pw3"])}<p className="s">{t("pvStop")}</p></section>
      </div>
    </>
  );
}
