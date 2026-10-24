import { LogoutLink } from "../../auth/session";
import { useEffect, useState } from "react";
import { Link, Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { useLang, type Key } from "../../components/i18n";
import { Icon, LiveDot, MockBadge } from "../../components/ui";
import { useExtras } from "../../api/patientExtras";
import { USE_MOCK } from "../../api";
import { usePortal } from "./usePortal";
import "../../styles/patient.css";
import "./extra.css";

const ITEMS: { to: string; side: Key; tab: Key; icon: string; end?: boolean }[] = [
  { to: "/patient", side: "home", tab: "home", icon: "home", end: true },
  { to: "/patient/record", side: "record", tab: "record", icon: "cal" },
  { to: "/patient/messages", side: "messages", tab: "messages", icon: "list" },
  { to: "/patient/ask", side: "askNav", tab: "askTab", icon: "chat" },
  { to: "/patient/me", side: "me", tab: "me", icon: "me" },
];

export function LangToggle() {
  const { lang, setLang } = useLang();
  return (
    <div className="langtog" role="group" aria-label="Language">
      <button type="button" aria-pressed={lang === "te"} onClick={() => setLang("te")} lang="te">తెలుగు</button>
      <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>English</button>
    </div>
  );
}

/** Gentle banner shown when the phone has no internet (or the demo switch is on). */
export function OfflineBanner() {
  const { t } = useLang();
  const [ex] = useExtras();
  const [net, setNet] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const on = () => setNet(true), off = () => setNet(false);
    window.addEventListener("online", on); window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);
  if (net && !(USE_MOCK && ex.offline)) return null; // the offline demo switch exists in mock mode only
  return <div className="banner" role="status"><b>{t("offT")}.</b> {t("offS")}</div>;
}

export function useUnread() {
  const v = usePortal();
  return v.messages.filter((m) => !v.isRead(m.id)).length;
}

export function PatientShell() {
  const { t } = useLang();
  const [ex] = useExtras();
  const loc = useLocation();
  const unread = useUnread();
  const welcome = loc.pathname === "/patient/welcome";
  if (!ex.onboarded && !welcome) return <Navigate to="/patient/welcome" replace />;
  const cls = `pat${ex.largeText ? " lt" : ""}`;
  if (welcome) return <div className={cls}><main className="welcome"><Outlet /></main></div>;
  const badge = (k: string) => (k === "messages" && unread > 0 ? <span className="nb" aria-label={t("newN", { n: unread })}>{unread}</span> : null);
  return (
    <div className={cls}>
      <div className="shell">
        <nav className="side" aria-label="Main">
          <div className="logo">CareMemory</div>
          {ITEMS.map((i) => (
            <NavLink key={i.to} to={i.to} end={i.end} className={({ isActive }) => (isActive ? "on" : "")}><Icon name={i.icon} />{t(i.side)}{badge(i.side)}</NavLink>
          ))}
          <div className="lang"><LangToggle /><MockBadge /><LiveDot /><LogoutLink style={{ minHeight: 44, display: "inline-flex", alignItems: "center", textDecoration: "underline" }}>{t("switchRole")}</LogoutLink></div>
        </nav>
        <div>
          <header className="top"><span className="l">CareMemory</span><LangToggle /><MockBadge /><LiveDot /></header>
          <main>
            <OfflineBanner />
            <Outlet />
            <p className="disc">{t("disc")}</p>
          </main>
        </div>
      </div>
      <nav className="tabs" aria-label="Main (phone)">
        {ITEMS.map((i) => (
          <NavLink key={i.to} to={i.to} end={i.end} className={({ isActive }) => (isActive ? "on" : "")}><Icon name={i.icon} /><span>{t(i.tab)}</span>{badge(i.tab)}</NavLink>
        ))}
      </nav>
    </div>
  );
}
