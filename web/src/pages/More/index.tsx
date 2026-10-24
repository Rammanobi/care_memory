import { Link } from "react-router-dom";
import { Icon } from "../../components/ui";

const LINKS = [
  { to: "/doctor/ask", label: "Ask", help: "Ask a question about your patients", icon: "search" },
  { to: "/doctor/lens", label: "Memory Lens", help: "See what the system knew on day 3 and day 60", icon: "eye" },
  { to: "/doctor/district", label: "District", help: "Clinics, adherence and quiet patients", icon: "pin" },
  { to: "/doctor/admin", label: "Admin and demo", help: "Usage, caps and demo controls", icon: "gauge" },
  { to: "/doctor/settings", label: "Settings", help: "Alerts, templates and consent", icon: "gear" },
];

export default function MorePage() {
  return (
    <main className="main wide" aria-labelledby="h-more">
      <h1 id="h-more">More</h1>
      <div className="sub">Everything else</div>
      <div className="morelist">
        {LINKS.map((l) => (
          <Link key={l.to} to={l.to} className="li"><Icon name={l.icon} /><div><b>{l.label}</b><div className="sm">{l.help}</div></div><span className="go" aria-hidden="true">›</span></Link>
        ))}
      </div>
    </main>
  );
}
