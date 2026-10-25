import { useEffect, useState, type ComponentProps, type ReactNode } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { USE_MOCK } from "../api";
import { resetHttpSession } from "../api/httpAdapter";
import { forgetSession, getMe, http } from "../api/http";
import { emailFor, firebaseAuth, isFirebaseMode } from "./firebase";

export interface Me {
  role: string;
  username?: string | null;
  display_name?: string | null;
  clinic_id?: string | null;
}

/** Where each backend role lands after sign-in. */
export function homeFor(role: string): string {
  if (role === "patient") return "/patient";
  if (role === "supporter") return "/supporter";
  if (role === "sts" || role === "dto") return "/doctor/district";
  return "/doctor";
}

/** Which roles may open which area. Admin may open every area (demo). */
const ALLOWED: Record<string, string[]> = {
  doctor: ["doctor", "admin", "sts", "dto"],
  patient: ["patient", "admin"],
  supporter: ["supporter", "admin"],
};
export const canOpen = (area: keyof typeof ALLOWED, role: string) => ALLOWED[area].includes(role);

export async function signIn(username: string, password: string): Promise<string> {
  resetHttpSession();
  if (isFirebaseMode()) {
    // VITE_AUTH_MODE=firebase: sign in at Firebase, then the API decides the role (claims checked against the DB).
    await (await firebaseAuth()).signIn(emailFor(username), password);
    forgetSession(null);
    const me = await getMe<{ role: string }>();
    window.dispatchEvent(new Event("cm-session"));
    return me.role;
  }
  const out = await http<{ role: string }>("/auth/login", { method: "POST", body: { username, password } });
  forgetSession(null); // the next /auth/me is the first of the new session
  window.dispatchEvent(new Event("cm-session"));
  return out.role;
}

export async function signOut(): Promise<void> {
  try {
    if (isFirebaseMode()) await (await firebaseAuth()).signOut();
    else await http("/auth/logout", { method: "POST" });
  } finally {
    resetHttpSession();
    forgetSession(false);
    window.dispatchEvent(new Event("cm-session"));
  }
}

export async function fetchMe(): Promise<Me | null> {
  try {
    return await getMe<Me>();
  } catch {
    return null;
  }
}

/** Route guard. Mock mode lets everything through (the role switcher is the only gate). */
export function RequireRole({ area, children }: { area: keyof typeof ALLOWED; children: ReactNode }) {
  const [me, setMe] = useState<Me | null | undefined>(USE_MOCK ? null : undefined);
  useEffect(() => {
    if (USE_MOCK) return;
    let alive = true;
    fetchMe().then((m) => alive && setMe(m));
    return () => {
      alive = false;
    };
  }, []);
  if (USE_MOCK) return <>{children}</>;
  if (me === undefined) return <div role="status" aria-label="Loading" style={{ padding: 24 }}>Loading…</div>;
  if (!me) return <Navigate to="/" replace />;
  if (!canOpen(area, me.role)) return <Navigate to={homeFor(me.role)} replace />;
  return <>{children}</>;
}

/** The old "switch role" link. In http mode it signs out instead. */
export function LogoutLink({ children, ...rest }: Omit<ComponentProps<typeof Link>, "to">) {
  const nav = useNavigate();
  if (USE_MOCK) return <Link to="/" {...rest}>{children}</Link>;
  return (
    <Link
      to="/"
      {...rest}
      onClick={(e) => {
        e.preventDefault();
        signOut().finally(() => nav("/", { replace: true }));
      }}
    >
      {children}
    </Link>
  );
}
