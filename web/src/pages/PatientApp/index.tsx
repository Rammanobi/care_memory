import { Link } from "react-router-dom";
import { useCare } from "../../api/CareProvider";
import { useLang } from "../../components/i18n";
import { Skeleton } from "../../components/ui";
import { DoseCard, Emergency, History, Medicines, NewRequest, RequestList } from "./parts";
import { useMessages, fmtMsgDay } from "./Messages";
import { usePortal } from "./usePortal";
import { doseLine } from "./portalTypes";
import { AboutMyRecord } from "./AboutMyRecord";
import RecordPage from "./Record";
import MePage from "./Me";

function Loading() {
  return <div className="col" style={{ marginTop: 16 }}><Skeleton h={150} /><Skeleton h={80} /><Skeleton h={110} /></div>;
}

function Next3() {
  const { state } = useCare();
  const { t } = useLang();
  const v = usePortal();
  const today = state?.dose.today ?? "none";
  const visit = v.upcoming.find((a) => a.kind === "visit");
  const lab = v.upcoming.find((a) => a.kind === "lab");
  const items = [
    { k: "m", icon: "1", title: t("itemMed"), sub: doseLine(today, v.supporterMarked, t) },
    ...(v.empty ? [] : [
      ...(visit ? [{ k: "v", icon: "2", title: t("visit"), sub: `${visit.when} · ${visit.place}` }] : []),
      ...(lab ? [{ k: "l", icon: "3", title: t("lab"), sub: `${lab.when} · ${lab.place}` }] : []),
    ]),
  ];
  return (
    <section className="card" aria-labelledby="n3">
      <div className="k" id="n3">{t("next3")}</div>
      {items.map((x, i) => (
        <div key={x.k} className={`med${i === 0 ? " first" : ""}`}><div className="pl y" aria-hidden="true">{x.icon}</div><div style={{ minWidth: 0 }}><b>{x.title}</b><span>{x.sub}</span></div></div>
      ))}
    </section>
  );
}

function LatestMessage() {
  const { t, lang } = useLang();
  const { list } = useMessages();
  const m = list[0];
  if (!m) return null;
  return (
    <div className="card msg">
      <small>{t("latestMsg")} · {fmtMsgDay(m, lang)}</small>
      <b>{m.title}</b><div>{m.text}</div>
      <Link to="/patient/messages" className="link" style={{ display: "inline-flex", alignItems: "center", paddingLeft: 0 }}>{t("allMsgs")} ›</Link>
    </div>
  );
}

export function Home() {
  const { state } = useCare();
  const { t } = useLang();
  const v = usePortal();
  const streak = v.streak;
  return (
    <>
      <h1>{t("morning")}, {v.name}</h1>
      {v.day > 0 && <div className="sub">{t("dayOf", { n: v.day })}</div>}
      {!state ? <Loading /> : (
        <div className="grid">
          <div className="col">
            <DoseCard />
            <Next3 />
            <div className="two">
              <div className="card"><div className="k">{t("nextVisit")}</div><div className="n">{v.nextVisitText ?? t("nothingSched")}</div>{v.clinic && <div className="s">{v.clinic}</div>}</div>
              <div className="card"><div className="k">{t("streak")}</div><div className="n">{t("daysRow", { n: streak })}</div><div className="s">{t("inARow")}</div></div>
            </div>
            {!v.empty && <AboutMyRecord />}
            <LatestMessage />
            <History />
            {v.showMedicines && <Medicines />}
          </div>
          <div className="col">
            <section className="card">
              <div className="k">{t("askTitle")}</div>
              <div className="s" style={{ marginBottom: 8 }}>{t("readsFirst")}</div>
              <RequestList limit={2} />
              <Link to="/patient/ask" className="link" style={{ display: "inline-flex", alignItems: "center" }}>{t("askNav")} ›</Link>
            </section>
            <NewRequest />
            <Emergency />
          </div>
        </div>
      )}
    </>
  );
}

export function Ask() {
  const { state } = useCare();
  const { t } = useLang();
  return (
    <>
      <h1>{t("askTitle")}</h1>
      <div className="sub">{t("readsFirst")}</div>
      {!state ? <Loading /> : (
        <div className="grid">
          <div className="col">
            <section className="card" aria-labelledby="myreq"><div className="k" id="myreq">{t("reqHist")}</div><RequestList /></section>
          </div>
          <div className="col"><NewRequest /><Emergency /></div>
        </div>
      )}
    </>
  );
}

export const Record = RecordPage;
export const Me = MePage;
