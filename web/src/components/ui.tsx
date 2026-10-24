import { useSyncExternalStore, type ReactNode } from "react";
import { USE_MOCK } from "../api";
import { status } from "../api/status";

const PATHS: Record<string, ReactNode> = {
  home: <path d="M3 11l9-7 9 7v9H3z" />,
  people: (<><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.5-4 3-6 6.5-6s6 2 6.5 6" /></>),
  list: <path d="M4 6h16M4 12h16M4 18h10" />,
  chat: <path d="M4 5h16v11H8l-4 4z" />,
  pin: <path d="M12 21s-7-6-7-11a7 7 0 0114 0c0 5-7 11-7 11z" />,
  search: (<><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></>),
  cal: (<><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M9 3v4M15 3v4" /></>),
  me: (<><circle cx="12" cy="8" r="4" /><path d="M4 21c1-5 4-7 8-7s7 2 8 7" /></>),
  back: <path d="M15 5l-7 7 7 7" />,
  eye: (<><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>),
  gauge: (<><path d="M4 18a8 8 0 1116 0" /><path d="M12 18l4-6" /></>),
  gear: (<><circle cx="12" cy="12" r="3" /><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" /></>),
  more: (<><circle cx="5" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="19" cy="12" r="1.6" /></>),
  mic: (<><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0014 0M12 18v3" /></>),
};

export function Icon({ name }: { name: keyof typeof PATHS | string }) {
  return (
    <svg className="ic" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      {PATHS[name]}
    </svg>
  );
}

export function LiveDot() {
  const live = useSyncExternalStore(status.subscribe, () => status.get().live);
  if (USE_MOCK) return <span className="livedot demo" title="Demo data, no server">demo</span>;
  return <span className={`livedot${live ? " on" : ""}`} role="status" aria-label={live ? "Live updates connected" : "Live updates off, checking every few seconds"} title={live ? "Live" : "Offline, refreshing every 5 s"}><i aria-hidden="true" />{live ? "live" : "polling"}</span>;
}

export function MockBadge() {
  return USE_MOCK ? <span className="mock">MOCK DATA</span> : null;
}

export function Skeleton({ h = 60, n = 1 }: { h?: number; n?: number }) {
  return (
    <div role="status" aria-label="Loading" style={{ display: "grid", gap: 10 }}>
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="skel" style={{ height: h }} />
      ))}
    </div>
  );
}
