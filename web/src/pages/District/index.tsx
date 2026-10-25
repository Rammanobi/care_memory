import { useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useCare } from "../../api/CareProvider";
import { adherencePct, clinicStats, quietDays, suppress } from "../../api/derive";
import { Skeleton } from "../../components/ui";

export default function DistrictPage() {
  const { state } = useCare();
  const [f, setF] = useState("all");
  if (!state) return <main className="main wide"><h1>District</h1><div style={{ marginTop: 14 }}><Skeleton h={200} n={2} /></div></main>;
  const d = state.district;
  type Row = { id: string; name: string; area: string; patients: number | null; adherence: number | null; quiet: number | null; pending: number | null; hidden: string[] };
  const stats: Row[] = d
    ? d.clinics.map((c) => ({ ...c, hidden: c.suppressed }))
    : clinicStats(state).map((c) => {
      // Same rule as the server: a count of 1 to 4 is hidden, and so is the adherence of a clinic that small.
      const patients = suppress(c.patients), quiet = suppress(c.quiet), pending = suppress(c.pending);
      const hidden = [patients === null && "patients", quiet === null && "quiet", pending === null && "pending"].filter((x): x is string => !!x);
      return { id: c.id, name: c.name, area: c.area, patients, adherence: patients === null ? null : c.adherence, quiet, pending, hidden: patients === null ? [...hidden, "adherence"] : hidden };
    });
  const shown = f === "all" ? stats : stats.filter((c) => c.id === f);
  const clinicOf = (name: string) => state.clinics.find((c) => c.name === name || c.id === name)?.id;
  const quietList = d
    ? d.quiet.filter((q) => f === "all" || clinicOf(q.clinic) === f).map((q) => ({ code: q.code, why: q.why, adherence: q.adherence, noData: q.noData }))
    : state.patients.filter((p) => p.quiet && (f === "all" || p.clinic === f)).map((p) => ({ code: p.code, why: p.why, adherence: adherencePct(p), noData: p.noData }));
  const total = f === "all" && d ? d.totalPatients : shown.some((c) => c.patients === null) ? null : shown.reduce((a, c) => a + (c.patients ?? 0), 0);
  const anyHidden = shown.some((c) => c.hidden.length > 0) || (d ? d.totalPatients === null : false);
  const empty = d ? d.clinics.length === 0 : state.patients.length === 0;
  const cell = (v: number | null, s = "") => (v === null ? <span className="tag t-amb" title={`Counts below ${d?.threshold ?? 5} are hidden to protect privacy`}>under {d?.threshold ?? 5}, hidden</span> : `${v}${s}`);
  return (
    <main className="main wide" aria-labelledby="h-dist">
      <h1 id="h-dist">District</h1>
      <div className="sub">{state.clinics.length} clinics · {total === null ? `under ${d?.threshold ?? 5}, hidden` : total} patients · adherence is the share of the last 20 days with a dose logged</div>
      <div className="pills" role="group" aria-label="Filter by clinic" style={{ marginTop: 10 }}>
        <button type="button" className={`pill${f === "all" ? " on" : ""}`} aria-pressed={f === "all"} onClick={() => setF("all")}>All clinics</button>
        {state.clinics.map((c) => <button key={c.id} type="button" className={`pill${f === c.id ? " on" : ""}`} aria-pressed={f === c.id} onClick={() => setF(c.id)}>{c.name}</button>)}
      </div>
      {anyHidden && <div className="sub" role="note" data-testid="suppress-note">To protect privacy, any count of 1 to {(d?.threshold ?? 5) - 1} is shown as "under {d?.threshold ?? 5}, hidden". The same applies to the figures that would reveal it.</div>}
      {empty ? <div className="empty"><b>No clinic data</b>Load the sample data from Admin.</div> : (
        <>
          <div className="two">
            <section className="sec">
              <h3>Clinics</h3>
              <div className="tbl-wrap"><table className="tbl">
                <thead><tr><th>Clinic</th><th>Patients</th><th>Adherence</th><th>Quiet</th><th>Pending approvals</th></tr></thead>
                <tbody>{shown.map((c) => (
                  <tr key={c.id}><td><b>{c.name}</b><div className="sm">{c.area}</div></td><td>{cell(c.patients)}</td>
                    <td>{c.adherence === null ? cell(null) : <><b>{c.adherence}%</b> <span className={`tag ${c.adherence >= 85 ? "t-grn" : c.adherence >= 75 ? "t-amb" : "t-red"}`}>{c.adherence >= 85 ? "GOOD" : c.adherence >= 75 ? "WATCH" : "LOW"}</span></>}</td>
                    <td>{cell(c.quiet)}</td><td>{cell(c.pending)}</td></tr>
                ))}</tbody>
              </table></div>
            </section>
            <section className="sec" aria-label="Adherence by clinic chart">
              <h3>Adherence by clinic (%)</h3>
              <div style={{ width: "100%", height: 230 }}>
                <ResponsiveContainer>
                  <BarChart data={shown.map((c) => ({ name: c.name.split(" ")[0], adherence: c.adherence, ok: (c.adherence ?? 0) >= 85 }))} margin={{ top: 18, right: 8, left: -18, bottom: 0 }}>
                    <CartesianGrid stroke="#E6DFD3" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Bar dataKey="adherence" radius={[6, 6, 0, 0]}>
                      {shown.map((c) => <Cell key={c.id} fill={(c.adherence ?? 0) >= 85 ? "#15803D" : (c.adherence ?? 0) >= 75 ? "#F59E0B" : "#B91C1C"} />)}
                      <LabelList dataKey="adherence" position="top" fontSize={12} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          </div>
          <section className="sec">
            <h3>Quiet patients {f === "all" ? "in the district" : "in this clinic"}</h3>
            {quietList.length === 0 ? <div className="empty">Nobody is quiet</div> : quietList.map((p) => (
              <Link key={p.code} to={`/doctor/patients/${p.code}`} className="li">
                <div><b>{p.code}</b> <span className="tag t-amb">QUIET</span><div className="sm">{p.why} · adherence {p.adherence}%</div></div>
                <span className="sm">{quietDays(p)}</span>
              </Link>
            ))}
          </section>
        </>
      )}
    </main>
  );
}
