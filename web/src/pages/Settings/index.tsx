import { useEffect, useState } from "react";
import { isLive, consentStatesServer } from "../../api/serverCalls";
import { useCare } from "../../api/CareProvider";
import type { Settings } from "../../api";
import { clinicName } from "../../api/derive";
import { Skeleton } from "../../components/ui";

const PREFS: { k: keyof Settings; label: string; help: string }[] = [
  { k: "notifyRed", label: "Tell me about RED items at once", help: "A pop-up and a message when a red draft is ready" },
  { k: "notifyRequests", label: "Tell me when a patient asks something", help: "One alert per request" },
  { k: "digest", label: "Daily summary at 8 am", help: "One short list instead of many alerts" },
  { k: "quiet", label: "Quiet hours, 9 pm to 6 am", help: "Only RED items break through" },
  { k: "sound", label: "Play a sound", help: "Off by default in the clinic" },
];

export default function SettingsPage() {
  const { state, dispatch } = useCare();
  const [srv, setSrv] = useState<Record<string, string>>({});
  const ids = state?.patients.map((p) => p.personId).filter((x): x is string => !!x) ?? [];
  const idKey = ids.join(",");
  useEffect(() => {
    if (!isLive || !idKey) return;
    let alive = true;
    consentStatesServer(idKey.split(",")).then((r) => alive && setSrv(r));
    return () => { alive = false; };
  }, [idKey]);
  if (!state) return <main className="main wide"><h1>Settings</h1><div style={{ marginTop: 14 }}><Skeleton h={80} n={3} /></div></main>;
  const consentOf = (p: { personId?: string; consent: string }) => (p.personId && srv[p.personId]) || p.consent; // /consents/{person_id} wins over the list field
  const consentCount = (v: string) => state.patients.filter((p) => consentOf(p) === v).length;
  return (
    <main className="main wide" aria-labelledby="h-set">
      <h1 id="h-set">Settings</h1>
      <div className="sub">Alerts, approved message templates and patient consent</div>
      <div className="two">
        <section className="sec">
          <h3>Notifications</h3>
          {PREFS.map((p) => (
            <label key={p.k} className="chk sw">
              <input type="checkbox" checked={state.settings[p.k]} onChange={(e) => dispatch({ t: "setting", key: p.k, value: e.target.checked })} />
              <span><b>{p.label}</b><span className="sm">{p.help}</span></span>
            </label>
          ))}
        </section>
        <section className="sec">
          <h3>Approved message templates (read only)</h3>
          {state.templates.map((t) => <div key={t.id} className="tpl"><b>{t.name}</b><div className="sm">{t.text}</div></div>)}
        </section>
      </div>
      {state.serverSettings && (
        <section className="sec" aria-labelledby="h-thr">
          <h3 id="h-thr">Clinic rules (read only) <span className="tag t-grn" data-testid="settings-version">version {state.serverSettings.version}</span></h3>
          <div className="kv">
            {Object.entries(state.serverSettings.values).map(([k, v]) => <div key={k}><span>{k.replace(/_/g, " ")}</span><b>{String(v)}</b></div>)}
          </div>
          <div className="sm">Changes are made by an administrator. The version number guards against two people saving at once.</div>
        </section>
      )}
      <section className="sec">
        <h3>Consent overview</h3>
        <div className="pills" aria-label="Consent totals">
          <span className="tag t-grn">Active {consentCount("Active")}</span>
          <span className="tag t-amb">Pending {consentCount("Pending")}</span>
          <span className="tag t-red">Withdrawn {consentCount("Withdrawn")}</span>
        </div>
        {state.patients.length === 0 ? <div className="empty"><b>No patients</b>Consent shows here once patients are added.</div> : (
          <div className="tbl-wrap"><table className="tbl">
            <thead><tr><th>Patient</th><th>Clinic</th><th>Patient consent</th><th>Supporter</th></tr></thead>
            <tbody>{state.patients.map((p) => { const c = consentOf(p); return (
              <tr key={p.code}><td><b>{p.code}</b></td><td>{clinicName(state, p.clinic)}</td>
                <td><span className={`tag ${c === "Active" ? "t-grn" : c === "Pending" ? "t-amb" : "t-red"}`}>{c === "Active" ? "✓ " : c === "Pending" ? "… " : "✕ "}{c}</span></td>
                <td>{p.supporter}{c === "Withdrawn" && <span className="sm"> (paused)</span>}</td></tr>
            ); })}</tbody>
          </table></div>
        )}
      </section>
    </main>
  );
}
