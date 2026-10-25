import { Link } from "react-router-dom";
import { useCare } from "../../api/CareProvider";
import { counts, dueAtOf, quietDays, requestLabel, waitingApprovals, waitingRequests, weekdayName } from "../../api/derive";
import { Sla } from "../../components/doctorKit";
import { Skeleton } from "../../components/ui";

export default function TodayPage() {
  const { state } = useCare();
  if (!state) {
    return (
      <main className="main wide" aria-labelledby="h-today">
        <h1 id="h-today">Today</h1>
        <div style={{ marginTop: 14 }}><Skeleton h={78} n={1} /><div style={{ height: 12 }} /><Skeleton h={120} n={3} /></div>
      </main>
    );
  }
  const c = counts(state);
  const redAps = waitingApprovals(state).filter((a) => a.lane === "red").sort((a, b) => dueAtOf(state, a) - dueAtOf(state, b));
  const deadlines = [...waitingApprovals(state).filter((a) => a.lane !== "green"), ...waitingRequests(state)].sort((a, b) => dueAtOf(state, a) - dueAtOf(state, b)).slice(0, 5);
  const visits = state.patients.filter((p) => p.nextVisit.startsWith("Today"));
  const reqs = waitingRequests(state);
  const quiet = state.patients.filter((p) => p.quiet);
  const nothing = c.all === 0;

  return (
    <main className="main wide" aria-labelledby="h-today">
      <h1 id="h-today">Today</h1>
      <div className="sub">{weekdayName()} · sim day {state.simDay} · what needs you now</div>

      <div className="tiles">
        <div className="tile r"><b>{redAps.length}</b><span>Red drafts waiting</span></div>
        <div className="tile b"><b>{reqs.length}</b><span>Requests waiting</span></div>
        <div className="tile a"><b>{quiet.length}</b><span>Patients quiet 3+ days</span></div>
        <div className="tile g"><b>{visits.length}</b><span>Visits today</span></div>
      </div>

      {nothing ? (
        <div className="empty"><b>Nothing to do today</b>No patients are on the list. Use Admin to load the sample data.</div>
      ) : (
        <div className="today-grid">
          <section className="sec" aria-labelledby="t-now">
            <h3 id="t-now">Needs me now</h3>
            {redAps.length === 0 ? <div className="empty">All red items are handled</div> : redAps.map((a) => (
              <Link key={a.id} to={`/doctor/patients/${a.patientCode}`} className="li red">
                <div><b>{a.patientCode}</b> <span className="tag t-red">RED</span><div className="sm">{a.title}</div></div>
                <Sla due={dueAtOf(state, a)} />
              </Link>
            ))}
            {redAps.length > 0 && <Link className="more" to="/doctor/approvals">Open approvals ›</Link>}
          </section>

          <section className="sec" aria-labelledby="t-dead">
            <h3 id="t-dead">Review deadlines (soonest first)</h3>
            {deadlines.length === 0 ? <div className="empty">No deadlines</div> : deadlines.map((x) => (
              <Link key={x.id} to={x.id.startsWith("rq") ? "/doctor/requests" : "/doctor/approvals"} className="li">
                <div><b>{x.patientCode}</b><div className="sm">{"title" in x ? x.title : requestLabel(x.kind)}</div></div>
                <Sla due={dueAtOf(state, x)} />
              </Link>
            ))}
          </section>

          <section className="sec" aria-labelledby="t-visit">
            <h3 id="t-visit">Visits today</h3>
            {visits.length === 0 ? <div className="empty">No visits today</div> : visits.map((p) => (
              <Link key={p.code} to={`/doctor/patients/${p.code}`} className="li">
                <div><b>{p.code}</b><div className="sm">{p.sex}, {p.age} · {p.why}</div></div>
                <span className="pc">{p.nextVisit.replace("Today ", "")}</span>
              </Link>
            ))}
          </section>

          <section className="sec" aria-labelledby="t-req">
            <h3 id="t-req">Requests waiting</h3>
            {reqs.length === 0 ? <div className="empty">No requests waiting</div> : reqs.slice(0, 4).map((r) => (
              <Link key={r.id} to="/doctor/requests" className="li">
                <div><b>{r.patientCode}</b><div className="sm">"{r.text}"</div></div>
                <span className="sm">{r.when}</span>
              </Link>
            ))}
          </section>

          <section className="sec" aria-labelledby="t-quiet">
            <h3 id="t-quiet">Quiet patients</h3>
            {quiet.length === 0 ? <div className="empty">Nobody is quiet</div> : quiet.map((p) => (
              <Link key={p.code} to={`/doctor/patients/${p.code}`} className="li">
                <div><b>{p.code}</b> <span className="tag t-amb">QUIET</span><div className="sm">{p.why}</div></div>
                <span className="sm">{quietDays(p)}</span>
              </Link>
            ))}
          </section>
        </div>
      )}
    </main>
  );
}
