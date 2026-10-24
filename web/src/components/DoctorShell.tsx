import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useCare } from "../api/CareProvider";
import { USE_MOCK } from "../api";
import { counts } from "../api/derive";
import { LogoutLink } from "../auth/session";
import { Icon, LiveDot, MockBadge } from "./ui";
import { DoctorKit } from "./doctorKit";
import { QuestionNotify, useQuestionNotify } from "./QuestionNotify";
import "../styles/doctor.css";
import "../styles/doctor2.css";

const ITEMS = [
  { to: "/doctor/today", label: "Today", icon: "home", end: true },
  { to: "/doctor", label: "Patients", icon: "people", end: false },
  { to: "/doctor/approvals", label: "Approvals", icon: "list", end: true, badge: "a" },
  { to: "/doctor/requests", label: "Requests", icon: "chat", end: true, badge: "r" },
  { to: "/doctor/ask", label: "Ask", icon: "search", end: true },
  { to: "/doctor/lens", label: "Lens", icon: "eye", end: true },
  { to: "/doctor/district", label: "District", icon: "pin", end: true },
  { to: "/doctor/admin", label: "Admin", icon: "gauge", end: true },
  { to: "/doctor/settings", label: "Settings", icon: "gear", end: true },
] as const;
const MORE = ["/doctor/more", "/doctor/ask", "/doctor/lens", "/doctor/district", "/doctor/admin", "/doctor/settings"];

export function DoctorShell() {
  return <QuestionNotify><ShellInner /></QuestionNotify>;
}

function ShellInner() {
  const { state } = useCare();
  const { unread } = useQuestionNotify();
  const loc = useLocation();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const c = state ? counts(state) : null;

  useEffect(() => setQ(params.get("q") ?? ""), [params]);

  const isOn = (to: string) => (to === "/doctor" ? loc.pathname === "/doctor" || loc.pathname.startsWith("/doctor/patients") : loc.pathname === to);
  const badge = (b?: string) => {
    if (!c || !b) return null;
    if (b === "r" && unread > 0) return <span className="badge" aria-label={`${unread} new patient ${unread === 1 ? "question" : "questions"}`}>{unread}</span>;
    const n = b === "a" ? c.pendingApprovals : c.pendingRequests;
    return n > 0 ? <span className={b === "r" ? "badge blue" : "badge"} aria-label={`${n} waiting`}>{n}</span> : null;
  };

  return (
    <div className="doc">
      <header className="top">
        <span className="brand">CareMemory</span>
        <MockBadge />
        <LiveDot />
        <span className="clinic">Anantapur Urban Clinic · Dr. A. Rao</span>
        <span className="sp" />
        <form className="search" role="search" onSubmit={(e) => { e.preventDefault(); nav(`/doctor${q ? `?q=${encodeURIComponent(q)}` : ""}`); }}>
          <Icon name="search" />
          <input aria-label="Find a patient by code" placeholder="Find a patient by code" value={q} onChange={(e) => { setQ(e.target.value); nav(`/doctor${e.target.value ? `?q=${encodeURIComponent(e.target.value)}` : ""}`, { replace: true }); }} />
        </form>
        <LogoutLink className="user" aria-label={USE_MOCK ? "Doctor account. Switch role" : "Sign out"}>{USE_MOCK ? "DR" : "Out"}</LogoutLink>
      </header>
      <div className="app">
        <nav className="nav" aria-label="Doctor sections">
          {ITEMS.map((i) => (
            <NavLink key={i.to} to={i.to} end={i.end} className={isOn(i.to) ? "on" : ""} aria-current={isOn(i.to) ? "page" : undefined}>
              <Icon name={i.icon} />{i.label}{badge("badge" in i ? i.badge : undefined)}
            </NavLink>
          ))}
        </nav>
        <DoctorKit><Outlet /></DoctorKit>
      </div>
      <p className="note">{USE_MOCK ? "Mock data only · " : ""}Nothing reaches a patient until you approve it · Risk rank is a sorting aid, not a diagnosis</p>
      <nav className="tabs" aria-label="Doctor sections (phone)">
        {ITEMS.slice(0, 4).map((i) => (
          <NavLink key={i.to} to={i.to} end={i.end} className={isOn(i.to) ? "on" : ""} aria-current={isOn(i.to) ? "page" : undefined}>
            <Icon name={i.icon} />{i.label}{badge("badge" in i ? i.badge : undefined)}
          </NavLink>
        ))}
        <NavLink to="/doctor/more" className={MORE.includes(loc.pathname) ? "on" : ""} aria-current={loc.pathname === "/doctor/more" ? "page" : undefined}>
          <Icon name="more" />More
        </NavLink>
      </nav>
    </div>
  );
}
