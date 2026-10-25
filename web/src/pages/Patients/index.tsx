import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useCare } from "../../api/CareProvider";
import { counts, matches, missedLabel, stripCells, type FilterKey } from "../../api/derive";
import { Skeleton } from "../../components/ui";
import { PatientDetail } from "../Patient/PatientDetail";

export default function PatientsPage() {
  const { state } = useCare();
  const [params, setParams] = useSearchParams();
  const id = params.get("sel") ?? undefined;
  const q = (params.get("q") ?? "").trim().toLowerCase();
  const [filter, setFilter] = useState<FilterKey>("all");
  const c = useMemo(() => (state ? counts(state) : null), [state]);

  const rows = c ? c.rows.filter((r) => matches(r, filter) && r.p.code.toLowerCase().includes(q)) : [];
  const selected = id ?? c?.rows[0]?.p.code;

  // On a tablet the detail sits under the list: bring it into view when a row is opened.
  useEffect(() => {
    if (id && window.innerWidth > 720 && window.innerWidth <= 1180) {
      document.querySelector(".side")?.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  }, [id]);

  const pills: { k: FilterKey; label: string; n?: number }[] = [
    { k: "all", label: "All", n: c?.all },
    { k: "needs", label: "Needs me", n: c?.needs },
    { k: "requests", label: "Requests", n: c?.requests },
    { k: "quiet", label: "Quiet", n: c?.quiet },
    { k: "visit", label: "Visit this week", n: c?.visit },
  ];

  return (
    <>
      <main className="main" aria-labelledby="h-patients">
        <h1 id="h-patients">All patients</h1>
        <div className="sub">{c ? `${c.all} on treatment` : "Loading"} · who needs you first</div>

        {!state || !c ? (
          <div style={{ marginTop: 14 }}><Skeleton h={78} n={1} /><div style={{ height: 12 }} /><Skeleton h={60} n={5} /></div>
        ) : (
          <>
            <div className="tiles">
              <div className="tile r"><b>{c.red}</b><span>Patients to act on now</span></div>
              <div className="tile b"><b>{c.requests}</b><span>Patients with a request</span></div>
              <div className="tile a"><b>{c.quiet}</b><span>Patients quiet 3+ days</span></div>
              <div className="tile g"><b>{c.track}</b><span>Patients on track</span></div>
            </div>
            <div className="sm" data-testid="tile-note">Each tile counts patients out of {c.all}. Tiles overlap and do not add up to {c.all}.</div>
            <div className="pills" role="group" aria-label="Filter patients">
              {pills.map((p) => (
                <button key={p.k} type="button" className={`pill${filter === p.k ? " on" : ""}`} aria-pressed={filter === p.k} onClick={() => setFilter(p.k)}>
                  {p.label} {p.n}
                </button>
              ))}
            </div>

            {c.all === 0 ? (
              <div className="empty"><b>No patients yet</b>Patients appear here once the clinic adds them.</div>
            ) : rows.length === 0 ? (
              <div className="empty"><b>No patients match</b>Try another filter{q ? " or clear the search" : ""}.</div>
            ) : (
              <div className="list" role="list" aria-label="Patients">
                <div className="hdr" aria-hidden="true"><span>Patient</span><span>Why it is here</span><span>Last 20 days</span><span>Next step</span><span></span></div>
                {rows.map((r) => (
                  <Link
                    key={r.p.code}
                    role="listitem"
                    to={`/doctor?${new URLSearchParams({ ...(q ? { q } : {}), sel: r.p.code })}`}
                    data-k
                    className={`row ${r.level}${selected === r.p.code ? " sel" : ""}`}
                    aria-current={selected === r.p.code ? "true" : undefined}
                    aria-label={`${r.p.code}, ${r.tag}, ${r.p.why}. Open details`}
                  >
                    <div className="pc">{r.p.code}<small>{r.p.sex}, {r.p.age} · day {r.p.day}</small></div>
                    <div><span className={`tag ${r.tagClass}`}>{r.tag}</span>{r.p.why}</div>
                    <div>
                      <div className="strip" aria-hidden="true">{stripCells(r.p).map((k, i) => <i key={i} className={k} />)}</div>
                      <span className="sm">{missedLabel(r.p)}</span>
                    </div>
                    <div className="act">{r.next}</div>
                    <div className="go" aria-hidden="true">Open ›</div>
                  </Link>
                ))}
              </div>
            )}
          </>
        )}
      </main>
      {state && selected && <PatientDetail code={selected} open={!!id} onClose={() => { const n = new URLSearchParams(params); n.delete("sel"); setParams(n); }} />}
    </>
  );
}
