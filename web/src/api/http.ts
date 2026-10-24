import { status } from "./status";

export const API_BASE = ((import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8080").replace(/\/$/, "");

/** api.Problem (RFC 7807 style) as thrown by the adapter. */
export class ApiError extends Error {
  constructor(public httpStatus: number, public title: string, public detail?: string, public code?: string) {
    super(detail || title);
  }
}
export class NetworkError extends Error {}

interface Opts {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | undefined>;
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const RETRYABLE = new Set([502, 503, 504]);

export function problemFrom(httpStatus: number, body: unknown): ApiError {
  const b = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
  const p = (b.detail && typeof b.detail === "object" ? b.detail : b) as Record<string, unknown>; // FastAPI may nest the problem under `detail`
  const title = typeof p.title === "string" ? p.title : typeof b.detail === "string" ? b.detail : `HTTP ${httpStatus}`;
  return new ApiError(httpStatus, title, typeof p.detail === "string" ? p.detail : undefined, typeof p.code === "string" ? p.code : undefined);
}

export function buildUrl(path: string, query?: Opts["query"]): string {
  const u = new URL(API_BASE + path);
  for (const [k, v] of Object.entries(query ?? {})) if (v !== undefined) u.searchParams.set(k, String(v));
  return u.toString();
}

/**
 * Session knowledge shared by the route guard, the adapter and the live-update loop.
 * signedIn: null = not asked yet, true/false = answered by /auth/me. Logged-out visits then stop polling and stop opening /stream.
 */
export const sessionState: { signedIn: boolean | null; me: unknown; inflight: Promise<unknown> | null } = { signedIn: null, me: null, inflight: null };
export function forgetSession(signedIn: boolean | null = null) {
  sessionState.signedIn = signedIn;
  sessionState.me = null;
  sessionState.inflight = null;
}
/** One GET /auth/me per session: concurrent callers share the request, later callers share the answer. 401 = signed out (no retry until sign-in). */
export function getMe<T = { role: string }>(): Promise<T> {
  if (sessionState.signedIn === false) return Promise.reject(new ApiError(401, "Not signed in"));
  if (sessionState.me) return Promise.resolve(sessionState.me as T);
  if (!sessionState.inflight) {
    sessionState.inflight = http<T>("/auth/me")
      .then((m) => {
        const was = sessionState.signedIn;
        sessionState.me = m;
        sessionState.signedIn = true;
        if (was !== true && typeof window !== "undefined") window.dispatchEvent(new Event("cm-session-up"));
        return m;
      })
      .catch((e) => {
        if (e instanceof ApiError && e.httpStatus === 401) sessionState.signedIn = false;
        throw e;
      })
      .finally(() => {
        sessionState.inflight = null;
      });
  }
  return sessionState.inflight as Promise<T>;
}

/** Only idempotent GETs are retried (network errors and 502/503/504). */
export async function http<T>(path: string, o: Opts = {}): Promise<T> {
  const method = (o.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json" };
  let body: string | undefined;
  if (o.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(o.body);
  }
  if (method !== "GET") headers["X-CM-Client"] = "web";
  const attempts = method === "GET" ? 3 : 1;
  let lastErr: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetch(buildUrl(path, o.query), { method, headers, body, credentials: "include" });
      status.setOffline(false);
      if (res.status === 401 && path !== "/auth/login") sessionState.signedIn = false;
      if (res.status === 401 && path !== "/auth/login" && path !== "/auth/me") {
        status.toast("Your session ended. Please sign in again.");
        if (location.pathname !== "/") location.assign("/");
      }
      if (RETRYABLE.has(res.status) && i < attempts - 1) {
        await sleep(300 * 2 ** i);
        continue;
      }
      if (res.status === 204) return undefined as T;
      const ct = res.headers.get("content-type") ?? "";
      const data = ct.includes("json") ? await res.json().catch(() => null) : null;
      if (!res.ok) throw problemFrom(res.status, data);
      return data as T;
    } catch (e) {
      if (e instanceof ApiError) throw e;
      lastErr = e;
      if (i < attempts - 1) await sleep(300 * 2 ** i);
    }
  }
  status.setOffline(true);
  throw new NetworkError(lastErr instanceof Error ? lastErr.message : "Network error");
}
