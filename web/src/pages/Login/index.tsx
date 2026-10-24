import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { USE_MOCK } from "../../api";
import { ApiError } from "../../api/http";
import { fetchMe, homeFor, signIn } from "../../auth/session";
import { MockBadge } from "../../components/ui";

/** Mock mode: role switcher. Http mode: username and password against POST /auth/login. */
export default function Login() {
  return USE_MOCK ? <RoleSwitcher /> : <SignIn />;
}

function RoleSwitcher() {
  return (
    <main className="login">
      <div className="box">
        <h1>CareMemory <MockBadge /></h1>
        <p>Choose who you are. This is a demo screen, there is no password.</p>
        <Link to="/doctor" className="choice">I am a doctor<small>See patients, approve messages, answer requests</small></Link>
        <Link to="/patient" className="choice">I am a patient<small>My medicine, my visits, ask my care team</small></Link>
        <Link to="/supporter" className="choice">I am a family helper (Supporter)<small>See today's status, tap taken, ask the clinic</small></Link>
      </div>
    </main>
  );
}

function SignIn() {
  const nav = useNavigate();
  const [user, setUser] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchMe().then((m) => m && nav(homeFor(m.role), { replace: true }));
  }, [nav]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      nav(homeFor(await signIn(user.trim(), pw)), { replace: true });
    } catch (x) {
      setErr(x instanceof ApiError ? (x.httpStatus === 429 ? "Too many attempts. Wait a minute and try again." : x.httpStatus === 401 ? "Wrong username or password." : x.message) : "Cannot reach the server. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <form className="box" onSubmit={submit}>
        <h1>CareMemory</h1>
        <p>Sign in with your username and password.</p>
        <label>Username<input autoComplete="username" value={user} onChange={(e) => setUser(e.target.value)} required style={{ display: "block", width: "100%", minHeight: 44, margin: "4px 0 12px", padding: "0 10px" }} /></label>
        <label>Password<input type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} required style={{ display: "block", width: "100%", minHeight: 44, margin: "4px 0 12px", padding: "0 10px" }} /></label>
        {err && <p role="alert" style={{ color: "#b3261e" }}>{err}</p>}
        <button className="choice" type="submit" disabled={busy || !user || !pw}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
    </main>
  );
}
