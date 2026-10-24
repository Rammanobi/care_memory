import { useEffect, useState, type ComponentProps, type ReactNode } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { USE_MOCK } from "../api";
import { resetHttpSession } from "../api/httpAdapter";
import { http } from "../api/http";

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
  const out = await http<{ role: string }>("/auth/login", { method: "POST", body: { username, password } });
  window.dispatchEvent(new Event("cm-session"));
  return out.role;
}

export async function signOut(): Promise<void> {
  try {
    await http("/auth/logout", { method: "POST" });
  } finally {
    resetHttpSession();
    window.dispatchEvent(new Event("cm-session"));
  }
}

export async function fetchMe(): Promise<Me | null> {
  try {
    return await http<Me>("/auth/me");
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
