import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { dayFromIso } from "../../api/mapping";
import { useCare } from "../../api/CareProvider";
import { useLang, type Key } from "../../components/i18n";
import { Skeleton } from "../../components/ui";
import { TOTAL_DAYS, type Appt } from "./portalTypes";
import { usePortal } from "./usePortal";
import { Empty } from "./Common";
import { Emergency } from "./parts";

function MedCalendar() {
  const { t, lang } = useLang();
  const { state } = useCare();
  const v = usePortal();
  const idxDate = v.dateAt;
  const today = state?.dose.today ?? "none";
  const status = (i: number) => (i === TOTAL_DAYS - 1 ? (today === "taken" ? "o" : today === "missed" ? "m" : "f") : v.history60[i] ?? "f");
  const months: { y: number; m: number }[] = [];
  for (let i = 0; i < TOTAL_DAYS; i++) { const d = idxDate(i); if (!months.some((x) => x.y === d.getFullYear() && x.m === d.getMonth())) months.push({ y: d.getFullYear(), m: d.getMonth() }); }
  const [mi, setMi] = useState(months.length - 1);
  const [sel, setSel] = useState<number | null>(TOTAL_DAYS - 1);
  const { y, m } = months[mi];
  const loc = lang === "te" ? "te-IN" : "en-IN";
  const first = new Date(y, m, 1);
  const lead = (first.getDay() + 6) % 7; // Monday first
  const dim = new Date(y, m + 1, 0).getDate();
  const wd = Array.from({ length: 7 }, (_, i) => new Date(2024, 0, 1 + i).toLocaleDateString(loc, { weekday: "narrow" }));
  const cells: { n: number; idx: number }[] = [];
  for (let d = 1; d <= dim; d++) {
    const diff = Math.round((new Date(y, m, d, 12).getTime() - idxDate(TOTAL_DAYS - 1).getTime()) / 864e5);
    cells.push({ n: d, idx: TOTAL_DAYS - 1 + diff });
  }
  const took = Array.from({ length: TOTAL_DAYS }, (_, i) => status(i)).filter((c) => c === "o").length;
  const missed = Array.from({ length: TOTAL_DAYS }, (_, i) => status(i)).filter((c) => c === "m").length;
  const sym = (c: string) => (c === "o" ? "✓" : c === "m" ? "✕" : "·");
  const word = (c: string): Key => (c === "o" ? "dTaken" : c === "m" ? "dMissed" : "dNone");
  const sc = sel !== null && sel >= 0 && sel < TOTAL_DAYS ? status(sel) : null;
  const reason = sel === TOTAL_DAYS - 1 ? state?.dose.reason : sel !== null ? v.reasonAt(sel) : undefined;
  return (
    <section className="card" aria-labelledby="cal-t">
      <div className="row">
        <button type="button" className="link" disabled={mi === 0} onClick={() => setMi(mi - 1)} aria-label={t("prevM")}>‹</button>
        <div className="k" id="cal-t" style={{ margin: 0 }}>{first.toLocaleDateString(loc, { month: "long", year: "numeric" })}</div>
        <button type="button" className="link" disabled={mi === months.length - 1} onClick={() => setMi(mi + 1)} aria-label={t("nextM")}>›</button>
      </div>
      <div className="cal" role="group" aria-label={t("tabMed")} style={{ marginTop: 8 }}>
        {wd.map((w, i) => <div key={i} className="h" aria-hidden="true">{w}</div>)}
        {Array.from({ length: lead }, (_, i) => <div key={`e${i}`} className="e" />)}
        {cells.map((c) => {
          const has = c.idx >= 0 && c.idx < TOTAL_DAYS;
          const s = has ? status(c.idx) : "z";
          if (!has) return <div key={c.n} className="e z" aria-hidden="true">{c.n}</div>;
          return (
            <button key={c.n} type="button" className={s} aria-pressed={sel === c.idx} aria-label={`${c.n} ${first.toLocaleDateString(loc, { month: "long" })}: ${t(word(s))}`} onClick={() => setSel(c.idx)}>
              {c.n}<small aria-hidden="true">{sym(s)}</small>
            </button>
          );
        })}
      </div>
      <div className="leg" style={{ marginTop: 8 }}>
        <span><b style={{ background: "#CDEBD8" }} />✓ {t("taken2", { n: took })}</span>
        <span><b style={{ background: "#F3C6C6" }} />✕ {t("missed2", { n: missed })}</span>
        <span><b style={{ background: "#E4DED3" }} />· {t("legToday")}</span>
      </div>
      <div className="wait" style={{ marginTop: 10, marginBottom: 0 }} role="status" aria-live="polite">
        {sc === null ? t("pickDay") : (
          <>
            <b>{idxDate(sel!).toLocaleDateString(loc, { weekday: "long", day: "numeric", month: "long" })}</b>
            <div>{sym(sc)} {t(word(sc))}{sel === TOTAL_DAYS - 1 && sc === "f" ? ` (${t("legToday")})` : ""}</div>
            {sc === "m" && reason && <div className="s">{t("toldUs", { r: reason })}</div>}
          </>
        )}
      </div>
    </section>
  );
}

function ApptRow({ a, first }: { a: Appt; first: boolean }) {
  const { t } = useLang();
  return (
    <div className={`med${first ? " first" : ""}`}>
      <div className="pl y" aria-hidden="true">{a.kind === "visit" ? "V" : "L"}</div>
      <div style={{ minWidth: 0 }}><b>{a.kind === "visit" ? t("visit") : t("lab")}</b><span>{a.when} · {a.place}</span>{a.note && <span>✓ {a.note}</span>}</div>
    </div>
  );
}

function VisitsLabs() {
  const { t } = useLang();
  const v = usePortal();
  if (v.empty || (v.upcoming.length === 0 && v.past.length === 0)) return <Empty title={t("noVis")} body={t("noVisS")} />;
  return (
    <>
      <section className="card"><div className="k">{t("upc")}</div>{v.upcoming.map((a, i) => <ApptRow key={a.id} a={a} first={i === 0} />)}</section>
      <section className="card"><div className="k">{t("past")}</div>{v.past.map((a, i) => <ApptRow key={a.id} a={a} first={i === 0} />)}</section>
    </>
  );
}

const KIND: Record<string, string> = { visit_summary: "Visit summary", lab_slip: "Lab slip", letter: "Letter", other: "Document" };

function Documents() {
  const { t, lang } = useLang();
  const v = usePortal();
  const [open, setOpen] = useState<string | null>(null);
  const docs = v.documents;
  if (docs === null || docs.length === 0) return <Empty title={t("noDoc")} body={t("noDocS")} />;
  return (
    <section className="card">
      {docs.map((d, i) => (
        <div key={d.id} className={`med${i === 0 ? " first" : ""}`} style={{ display: "block" }}>
          <div className="row">
            <div style={{ minWidth: 0 }}><b>{d.title}</b><span style={{ display: "block" }}>{KIND[d.kind] ?? KIND.other} · {dayFromIso(d.date).toLocaleDateString(lang === "te" ? "te-IN" : "en-IN", { day: "numeric", month: "short", year: "numeric" })}</span></div>
            <button type="button" className="link" aria-expanded={open === d.id} onClick={() => setOpen(open === d.id ? null : d.id)}>{open === d.id ? t("docClose") : t("docOpen")}</button>
          </div>
          {open === d.id && <div className="wait" style={{ marginTop: 8 }} role="region" aria-label={d.title}>{d.summary}</div>}
        </div>
      ))}
    </section>
  );
}

export default function RecordPage() {
  const { state } = useCare();
  const { t } = useLang();
  const pv = usePortal();
  const day = pv.day;
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") ?? "med";
  const tabs: [string, Key][] = [["med", "tabMed"], ["vis", "tabVis"], ["doc", "tabDoc"]];
  return (
    <>
      <div className="row"><h1>{t("recTitle")}</h1><button type="button" className="link noprint" onClick={() => window.print()}>{t("printPg")}</button></div>
      {day > 0 && <div className="sub">{t("dayOf", { n: day })}</div>}
      <div className="tabbar" role="tablist" aria-label={t("recTitle")}>
        {tabs.map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setSp({ tab: k }, { replace: true })}>{t(l)}</button>)}
      </div>
      {!state ? <div className="col"><Skeleton h={300} /><Skeleton h={80} /></div> : (
        <div className="col" role="tabpanel">
          {tab === "med" && (pv.recordReady ? <MedCalendar /> : <Empty title={t("recNA")} />)}
          {tab === "vis" && <VisitsLabs />}
          {tab === "doc" && <Documents />}
          <Emergency />
        </div>
      )}
    </>
  );
}
