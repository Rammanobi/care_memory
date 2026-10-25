import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useCare } from "../../api/CareProvider";
import type { UsageMode } from "../../api";
import { Skeleton } from "../../components/ui";
import { USE_MOCK } from "../../api";
import { fmtAt, newestFirst } from "../../api/derive";
import { nextChange, spendDomainMax } from "./logic";

const MODES: { m: UsageMode; cls: string; title: string; text: string }[] = [
  { m: "GREEN", cls: "g", title: "GREEN under 70%", text: "Full AI: planning, drafting, Ask box." },
  { m: "AMBER", cls: "a", title: "AMBER 70 to 90%", text: "Cheaper model, fewer helper agents, shorter drafts. Owner is alerted." },
  { m: "RED", cls: "r", title: "RED over 90% or billing error", text: "Template-only mode. Rules and approved messages still work. Doctor gate unchanged." },
];
const SAY: Record<UsageMode, [string, string]> = {
  GREEN: ["Normal mode.", "Full AI drafting is on."],
  AMBER: ["Saving mode.", "Cheaper model and shorter drafts. Owner is alerted."],
  RED: ["Template-only mode.", "Approved messages and rules still work. The doctor gate is unchanged."],
};
const usd = (n: number) => `$${n.toFixed(2)}`;

export default function AdminPage() {
  const { state, dispatch, reset } = useCare();
  const [jitter, setJitter] = useState(0);
  useEffect(() => {
    const i = setInterval(() => setJitter((j) => (j + 1) % 7), 2500);
    return () => clearInterval(i);
  }, []);
  if (!state) return <main className="main wide"><h1>Admin and demo control</h1><div style={{ marginTop: 14 }}><Skeleton h={120} n={3} /></div></main>;
  const u = state.usage;
  const pct = u.todayCap ? Math.round((u.todaySpend / u.todayCap) * 100) : 0;
  const bpct = u.budget ? Math.round((u.budgetUsed / u.budget) * 100) : 0;
  const usageFailed = !USE_MOCK && !!state.loadErrors?.includes("usage");
  const prov = Math.min(99, u.providerPct + (jitter % 4) - 1);
  const audit = newestFirst(state.audit, (a) => a.at, state.simDay).slice(0, 10);
  const cls = u.mode === "GREEN" ? "g" : u.mode === "AMBER" ? "a" : "r";
  return (
    <main className="main wide" aria-labelledby="h-admin">
      <h1 id="h-admin">Admin and demo control</h1>
      <div className="sub">Usage and caps: what the AI has used, what is left, and what the system does when the cap gets close</div>

      <div className="capstate">
        <span className={`state ${cls}`}>{u.mode}</span>
        <div><b>{SAY[u.mode][0]}</b> {SAY[u.mode][1]}<br /><span className="sub" data-testid="next-change">{nextChange(u.mode, u.todayCap)}</span></div>
        <div className="seg" role="group" aria-label="Set the state for the demo">
          {MODES.map((x) => <button key={x.m} type="button" className={u.mode === x.m ? "on" : ""} aria-pressed={u.mode === x.m} onClick={() => dispatch({ t: "usageMode", mode: x.m })}>{x.m}</button>)}
        </div>
      </div>

      <div className="grid3">
        <div className="card"><div className="k">Today's cap</div><div className="n">{usd(u.todaySpend)} <small>of {usd(u.todayCap)}</small></div>
          <div className={`bar ${cls}`}><i style={{ width: `${pct}%` }} /><b style={{ left: "70%" }} /><b style={{ left: "90%" }} /></div>
          <div className="ticks"><span>0</span><span>70% amber</span><span>90% red</span><span>cap</span></div></div>
        <div className="card"><div className="k">Whole event budget</div><div className="n">${u.budgetUsed} <small>of ${u.budget}</small></div>
          <div className={`bar ${bpct > 75 ? "a" : "g"}`}><i style={{ width: `${bpct}%` }} /><b style={{ left: "75%" }} /></div>
          <div className="ticks"><span>0</span><span>demo reserve locked from 75%</span></div></div>
        <div className="card"><div className="k">Provider limits</div><div className="n">{u.mode === "RED" ? "Close" : "OK"} <small>{u.mode === "RED" ? "429 seen 12 min ago" : "no 429 in last hour"}</small></div>
          <div className="bar g"><i style={{ width: `${prov}%` }} /></div>
          <div className="ticks"><span>requests this minute: {prov}% of limit</span></div></div>
      </div>

      <div className="two">
        <section className="card"><div className="k">Spend by task type today</div>
          {usageFailed && <div className="empty"><b>Could not load usage</b>The server did not answer for /admin/usage.</div>}
          {u.tasks.map((t, n) => (
            <div key={`${t.name}-${n}`} className="trow"><span>{t.name}</span><div className={`bar ${t.flag === "watch" ? "a" : "g"}`}><i style={{ width: `${t.pct}%` }} /></div><span>{usd(t.spend)}</span><span className={`tag ${t.flag === "watch" ? "t-amb" : "t-grn"}`}>{t.flag}</span></div>
          ))}
        </section>
        <section className="card"><div className="k">Safety stops</div>
          <div className="trow two"><span>Runs stopped by circuit breaker</span><b>{u.breaker}</b></div>
          <div className="trow two"><span>Retries today</span><b>{u.retries}</b></div>
          <div className="trow two"><span>Billing errors (402)</span><b>{u.billing}</b></div>
          <div className="trow two"><span>Offline replay ready</span><b style={{ color: "var(--green)" }}>Yes</b></div>
        </section>
      </div>

      <section className="card" aria-label="Spend for the last 14 days">
        <div className="k">Spend, last 14 days ($ per day, cap {usd(u.todayCap)})</div>
        <div style={{ width: "100%", height: 190 }}>
          <ResponsiveContainer>
            <BarChart data={u.days} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid stroke="#E6DFD3" vertical={false} />
              <XAxis dataKey="d" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, spendDomainMax(u.days.map((x) => x.spend), u.todayCap)]} tick={{ fontSize: 11 }} />
              <Tooltip />
              <ReferenceLine y={u.todayCap * 0.7} stroke="#F59E0B" strokeDasharray="4 3" />
              <ReferenceLine y={u.todayCap * 0.9} stroke="#B91C1C" strokeDasharray="4 3" />
              <Bar dataKey="spend" fill="#0F766E" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="card" aria-label="Audit log" style={{ marginTop: 14 }}>
        <div className="k">Audit log (latest decisions)</div>
        {audit.length === 0 ? <div className="empty" data-testid="audit-empty"><b>No entries yet</b>Decisions and drafts are logged here.</div> : (
          <div className="tbl-wrap"><table className="tbl">
            <thead><tr><th>When</th><th>Patient</th><th>Who</th><th>What</th></tr></thead>
            <tbody>{audit.map((a) => <tr key={a.id}><td>{fmtAt(a.at, state.simDay)}</td><td>{a.code}</td><td>{a.actor}</td><td>{a.action}</td></tr>)}</tbody>
          </table></div>
        )}
      </section>

      <div className="legend">
        {MODES.map((x) => <div key={x.m} className={`lg ${x.cls}${u.mode === x.m ? " cur" : ""}`}><b>{x.title}</b>{u.mode === x.m && " (now)"}<br />{x.text}</div>)}
      </div>

      <div className="two" style={{ marginTop: 14 }}>
        <section className="card">
          <div className="k">Demo control</div>
          <div className="ctl"><span>Sim day <b>{state.simDay}</b></span>
            <button type="button" className="btn ed" onClick={() => dispatch({ t: "simDay", value: Math.max(1, state.simDay - 1) })} aria-label="Go back one day">- 1 day</button>
            <button type="button" className="btn ed" onClick={() => dispatch({ t: "simDay", value: state.simDay + 1 })} aria-label="Go forward one day">+ 1 day</button>
            <button type="button" className="btn ed" onClick={() => dispatch({ t: "simDay", value: state.simDay + 7 })}>+ 7 days</button></div>
          <div className="ctl">
            <button type="button" className="btn rj" onClick={reset}>Reset demo data</button>
            <button type="button" className="btn ed" onClick={() => dispatch({ t: "empty" })}>Show empty screens</button>
          </div>
          <div className="sub">Reset restores about 20 sample patients and their messages. "Show empty screens" clears every list so the empty states can be checked (Reset brings the data back).</div>
        </section>
        <section className="card">
          <div className="k">Channel status</div>
          {state.channels.length === 0 && <div className="sm">Not connected: the server reported no channel state.</div>}
          {state.channels.map((c) => (
            <div key={c.name} className="trow two"><span><b>{c.name}</b><div className="sm">{c.detail}</div></span>
              {USE_MOCK
                ? <button type="button" className={`pill${c.connected ? " on" : ""}`} aria-pressed={c.connected} onClick={() => dispatch({ t: "channel", name: c.name, connected: !c.connected })}>{c.connected ? "● Connected" : "○ Not connected"}</button>
                : <span className={`pill${c.connected ? " on" : ""}`}>{c.connected ? "● Connected" : "○ Not connected"}</span>}</div>
          ))}
        </section>
      </div>
    </main>
  );
}
