import { useState } from "react";
import { useCare } from "../../api/CareProvider";
import { confText } from "../../api/derive";
import { EvChip } from "../../components/doctorKit";
import { Skeleton } from "../../components/ui";

export default function LensPage() {
  const { state } = useCare();
  const [day, setDay] = useState<3 | 60>(3);
  const snaps = state?.lens ?? [];
  const snap = snaps.find((s) => s.day === day);
  const other = snaps.find((s) => s.day !== day);
  return (
    <main className="main wide" aria-labelledby="h-lens">
      <h1 id="h-lens">Memory Lens</h1>
      <div className="sub">The same kind of patient, seen early and late. Shows what the system knew at each point.</div>
      {!state ? <div style={{ marginTop: 14 }}><Skeleton h={120} n={2} /></div> : snaps.length === 0 ? (
        <div className="empty" style={{ marginTop: 14 }}><b>No twin patients loaded</b>The twin pair PT-0900 and PT-0901 appears with the sample data.</div>
      ) : (
        <>
          <div className="pills" role="group" aria-label="Choose the day" style={{ marginTop: 12 }}>
            {([3, 60] as const).map((d) => (
              <button key={d} type="button" className={`pill${day === d ? " on" : ""}`} aria-pressed={day === d} onClick={() => setDay(d)}>
                Day {d} · {state.lens.find((s) => s.day === d)?.code}
              </button>
            ))}
          </div>
          {snap && (
            <div className="lens-grid">
              <section className="sec" aria-label={`What the system knew on day ${snap.day}`}>
                <h3>Day {snap.day} · {snap.code}</h3>
                <div className="q">{snap.known}</div>
                <h4>Beliefs</h4>
                {snap.beliefs.map((b) => <div key={b.id} className="li static"><div><EvChip id={b.id} /> {b.text}</div><span className={`conf ${b.conf === "High" ? "hi" : "lo"}`}>{b.conf === "High" ? "● " : "○ "}{confText(b.conf)}</span></div>)}
                <h4>Conflicts</h4>
                {snap.conflicts.length === 0 ? <div className="q">None found. Too little data to compare sources.</div> : snap.conflicts.map((c) => <div key={c.id} className="li static"><div><EvChip id={c.id} /> {c.text}</div></div>)}
              </section>
              <section className="sec" aria-label="Risk range">
                <h3>Risk, shown as a range</h3>
                <div className="range" role="img" aria-label={`Risk between ${snap.risk[0]} and ${snap.risk[1]} out of 100`}>
                  <i style={{ left: `${snap.risk[0]}%`, width: `${snap.risk[1] - snap.risk[0]}%` }} />
                </div>
                <div className="ticks"><span>0</span><span>50</span><span>100</span></div>
                <p className="atext"><b>{snap.risk[0]} to {snap.risk[1]}</b> out of 100. {snap.risk[1] - snap.risk[0] > 30 ? "A wide range: the system is unsure because it has little data." : "A narrow range: the system has enough data to be fairly sure."}</p>
                {other && <div className="q">On day {other.day} the range for {other.code} is {other.risk[0]} to {other.risk[1]}.</div>}
              </section>
            </div>
          )}
        </>
      )}
    </main>
  );
}
