import { useState } from "react";
import { useCare } from "../../api/CareProvider";
import type { PatientRequest } from "../../api";
import { patientProfile } from "../../mocks/data";
import { usePortal } from "./usePortal";
import { useLang, type Key } from "../../components/i18n";
import { Icon } from "../../components/ui";
import { USE_MOCK } from "../../api";
import { JUST_NOW, REASONS, whenText, type ReqState } from "./portalTypes";
import { excerpt } from "../../api/questions";

export const ME = patientProfile.code;

export function useMyRequests() {
  const { state } = useCare();
  // http mode: /portal/requests only returns the patient's own, stamped with the signed-in code
  if (!USE_MOCK) return state?.requests ?? [];
  return (state?.requests ?? []).filter((r) => r.patientCode === (state?.portal?.me?.code ?? ME));
}

export function DoseCard() {
  const { state, dispatch } = useCare();
  const { t } = useLang();
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState<Key | null>(null);
  const v = usePortal();
  const today = state?.dose.today ?? "none";

  return (
    <section className={`card big${today === "taken" ? " done" : ""}`} aria-labelledby="dose-t">
      <div className="t" id="dose-t">{t("todayMed")}</div>
      <div className="v" aria-live="polite">
        {today === "none" ? t("notTaken") : today === "taken" ? `✓ ${t("taken")}` : t("missedToday")}
      </div>
      {today === "taken" && v.supporterMarked && <div className="s" style={{ marginBottom: 8 }}><span className="badge a">{t("marked")}</span></div>}
      {today === "none" && !asking && (
        <>
          <button type="button" className="btn" onClick={() => { v.clearMark(); dispatch({ t: "dose", value: { today: "taken" } }); }}>{t("tookIt")}</button>
          <div className="s" style={{ textAlign: "center", marginTop: 8 }}>
            {t("missQ")} <button type="button" className="link" onClick={() => setAsking(true)}>{t("tellUs")}</button>
          </div>
        </>
      )}
      {today === "none" && asking && (
        <div className="tellus">
          <div className="k" id="why">{t("whyMissed")}</div>
          <div className="chips" role="group" aria-labelledby="why">
            {REASONS.map((r) => (
              <button key={r.chip} type="button" className="chip" aria-pressed={reason === r.chip} onClick={() => setReason(r.chip)}>{t(r.chip)}</button>
            ))}
          </div>
          <button type="button" className="btn" disabled={!reason} onClick={() => { dispatch({ t: "dose", value: { today: "missed", reason: REASONS.find((r) => r.chip === reason)?.en } }); setAsking(false); }}>{t("sendMiss")}</button>
          <button type="button" className="btn ghost" onClick={() => setAsking(false)}>{t("cancel")}</button>
        </div>
      )}
      {today !== "none" && v.canUndo && (
        <div style={{ textAlign: "center" }}>
          <button type="button" className="link" onClick={() => { v.clearMark(); dispatch({ t: "dose", value: { today: "none" } }); }}>{t("undo")}</button>
        </div>
      )}
    </section>
  );
}

export function History({ big }: { big?: boolean }) {
  const { state } = useCare();
  const { t } = useLang();
  const v = usePortal();
  const today = state?.dose.today ?? "none";
  const cells = (v.live ? v.history60.slice(-30) : patientProfile.history).split("").map((c, i, a) => (i === a.length - 1 ? (today === "taken" ? "o" : today === "missed" ? "m" : "f") : c));
  const took = cells.filter((c) => c === "o").length;
  const missed = cells.filter((c) => c === "m").length;
  if (v.live && cells.length === 0) return <section className="card"><div className="k">{t("last30")}</div><div className="s">{t("noHist")}</div></section>;
  return (
    <section className="card">
      <div className="k">{t("last30")}</div>
      <div className="dots" role="img" aria-label={`${t("last30")}: ${t("taken2", { n: took })}, ${t("missed2", { n: missed })}`} style={big ? { gap: 6 } : undefined}>
        {cells.map((c, i) => <i key={i} className={c === "m" ? "m" : c === "f" ? "f" : ""} style={big ? { height: 34 } : undefined} />)}
      </div>
      <div className="leg">
        <span><b style={{ background: "var(--green)" }} />{t("taken2", { n: took })}</span>
        <span><b style={{ background: "#E9B3B3" }} />{t("missed2", { n: missed })}</span>
        <span><b style={{ background: "#E4DED3" }} />{t("legToday")}</span>
      </div>
    </section>
  );
}

export function Medicines() {
  const { t } = useLang();
  const v = usePortal();
  const rows = v.medicines ? v.medicines.map((m) => ({ key: m.id, name: m.label, how: m.note ? `${m.when} · ${m.note}` : m.when })) : patientProfile.medicines.map((m) => ({ key: m.name, name: m.name, how: m.how }));
  return (
    <section className="card">
      <div className="k">{t("myMeds")}</div>
      {rows.length === 0 && <div className="s" data-testid="meds-empty">{t("noMeds")}</div>}
      {rows.map((m, i) => (
        <div key={m.key} className={`med${i === 0 ? " first" : ""}`}><div className="pl" aria-hidden="true">{i + 1}</div><div><b>{m.name}</b><span>{m.how}</span></div></div>
      ))}
      <div className="s" style={{ marginTop: 6 }}>{t("medsRead")}</div>
    </section>
  );
}

export function Emergency() {
  const { t } = useLang();
  return (
    <div className="warn" role="note"><b>{t("unwellB")}</b> {t("unwellT")} <b>108</b>.</div>
  );
}

function Steps({ status }: { status: PatientRequest["status"] }) {
  const { t } = useLang();
  const done = status !== "waiting";
  return (
    <div className="steps" aria-label={done ? "Step 3 of 3: reply received" : "Step 2 of 3: doctor is reviewing"}>
      <i>✓</i>{t("sent")}<u />
      <i className={done ? "" : "cur"}>{done ? "✓" : "2"}</i>{t("reviews")}<u />
      <i className={done ? "" : "w"}>{done ? "✓" : "3"}</i>{t("reply")}
    </div>
  );
}

export function StatusChip({ s }: { s: ReqState }) {
  const { t } = useLang();
  // text label plus symbol, never colour alone
  return s === "waiting" ? <span className="badge w">◔ {t("waiting")}</span> : s === "approved" ? <span className="badge a">✓ {t("docReplied")}</span> : <span className="badge c">☎ {t("stCall")}</span>;
}

/** A chip-only request is stored with the English chip label for the doctor; the patient sees it in their language. */
const shownText = (text: string, t: (k: Key) => string) => { const c = CHIPS.find((x) => x.en === text); return c ? t(c.k) : text; };

export function RequestList({ limit }: { limit?: number }) {
  const { t } = useLang();
  const { state } = useCare();
  const mine = useMyRequests();
  const v = usePortal();
  const live = mine.filter((r) => !r.archived).map((r) => ({ id: r.id, text: r.text, when: r.when, status: r.status as ReqState, reply: r.reply, live: true }));
  const all = v.empty ? [] : [...live, ...v.pastRequests.map((r) => ({ ...r, live: false }))];
  const shown = limit ? all.slice(0, limit) : all;
  if (shown.length === 0 && state?.loadErrors?.includes("requests")) {
    return (
      <div className="empty" role="alert" style={{ padding: 16 }}>
        <b>{t("qLoadErr")}</b>{t("qLoadErrS")}
        <div><button type="button" className="btn ghost" style={{ marginTop: 8 }} onClick={() => window.dispatchEvent(new Event("cm-session"))}>{t("tryAgain")}</button></div>
      </div>
    );
  }
  if (shown.length === 0) return <div className="empty" style={{ padding: 16 }}><b>{t("noReq")}</b></div>;
  return (
    <div aria-live="polite">
      {shown.map((r) => (
        <div key={r.id} className={r.status === "waiting" ? "wait" : r.status === "approved" ? "ok" : "no"} style={{ overflowWrap: "anywhere" }}>
          <div className="row"><StatusChip s={r.status} /><span className="s">{whenText(r.when, t)}</span></div>
          <div style={{ marginTop: 4 }}>"{shownText(r.text, t)}"</div>
          {r.status === "approved" && r.reply && <div style={{ marginTop: 4 }}><b>{t("reply")}:</b> {r.reply}<div className="s inrep">{t("inReplyTo")} "{excerpt(shownText(r.text, t))}"</div></div>}
          {r.status === "declined" && <div style={{ marginTop: 4 }}>{t("stCallS")}</div>}
          {r.status === "waiting" && <div className="s" style={{ marginTop: 4 }}>{t("waitingS")}</div>}
          {r.status === "waiting" && <Steps status={r.status} />}
        </div>
      ))}
    </div>
  );
}

const CHIPS: { k: Key; en: string; draft: string }[] = [
  { k: "cChange", en: "Change visit", draft: "We have noted your request to change your visit. We will confirm the new time." },
  { k: "cRemind", en: "Reminder time", draft: "Your reminder time will be changed as you asked." },
  { k: "cRefill", en: "Refill help", draft: "We will help you get your refill. A nurse will call you." },
  { k: "cOther", en: "Other", draft: "Thank you for your message. Your care team will reply soon." },
];

export function NewRequest() {
  const { dispatch } = useCare();
  const { t } = useLang();
  const v = usePortal();
  // No chip is chosen at first: sending needs a chosen chip or some typed words, so an empty tap cannot send "Change visit".
  const [chip, setChip] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [ok, setOk] = useState(false);

  const send = () => {
    const c = CHIPS[chip ?? CHIPS.length - 1];
    if (chip === null && !text.trim()) return;
    const msg = text.trim() || c.en;
    dispatch({
      t: "newRequest",
      req: { id: `rq-${Date.now()}`, patientCode: v.code || (USE_MOCK ? ME : ""), kind: c.en, text: msg, when: JUST_NOW, draft: c.draft, status: "waiting" },
    });
    setText("");
    setChip(null);
    setOk(true);
    setTimeout(() => setOk(false), 4000);
  };

  return (
    <section className="card" id="ask-box" aria-labelledby="nr">
      <div className="k" id="nr">{t("newReq")}</div>
      <div className="chips" role="group" aria-label={t("newReq")}>
        {CHIPS.map((c, i) => (
          <button key={c.k} type="button" className="chip" aria-pressed={chip === i} onClick={() => setChip(chip === i ? null : i)}>{t(c.k)}</button>
        ))}
      </div>
      <div style={{ position: "relative" }}>
        <label className="sr-only" htmlFor="msg">{t("typeHere")}</label>
        <textarea id="msg" className="box" placeholder={t("typeHere")} value={text} maxLength={500} onChange={(e) => setText(e.target.value)} />
      </div>
      <div style={{ display: "flex", gap: 10 }}>
        <button type="button" className="btn ghost" style={{ width: 54, flex: "none" }} disabled aria-label={t("mic")} title={t("mic")}><Icon name="mic" /></button>
        <button type="button" className="btn" disabled={chip === null && !text.trim()} onClick={send}>{t("sendDoc")}</button>
      </div>
      <div className="s" role="status" style={{ marginTop: 8, minHeight: 20 }}>{ok ? `✓ ${t("sentOk")}` : ""}</div>
    </section>
  );
}
