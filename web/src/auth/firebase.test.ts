import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { forgetSession, http } from "../api/http";
import { status } from "../api/status";
import { emailFor, isFirebaseMode, setFirebaseAuthForTests, type FirebaseAuthApi } from "./firebase";
import { signIn, signOut } from "./session";

const resp = (code: number, body?: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status: code, headers: { "content-type": "application/json" } });

function fakeAuth(tokens: string[] = ["tok-1", "tok-2"]) {
  const calls: string[] = [];
  let signedIn = true;
  const api: FirebaseAuthApi = {
    async signIn(email) { calls.push(`signIn:${email}`); signedIn = true; },
    async signOut() { calls.push("signOut"); signedIn = false; },
    async getIdToken(force = false) { calls.push(`token:${force}`); return signedIn ? (force ? tokens[1] : tokens[0]) : null; },
  };
  return { api, calls };
}

const callOf = (f: { mock: { calls: unknown[][] } }, n: number) => f.mock.calls[n] as unknown as [string, RequestInit];
const headersOf = (f: { mock: { calls: unknown[][] } }, n: number) => callOf(f, n)[1].headers as Record<string, string>;

beforeEach(() => {
  forgetSession(null);
  status.setOffline(false);
  status.toast(null);
  vi.stubGlobal("location", { pathname: "/", assign: vi.fn() });
  vi.stubGlobal("window", new EventTarget());
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  setFirebaseAuthForTests(null);
});

describe("auth mode", () => {
  it("defaults to local", () => {
    expect(isFirebaseMode()).toBe(false);
  });
  it("maps usernames to the synthetic email domain", () => {
    expect(emailFor("Dr.Rao", "users.example.test")).toBe("dr.rao@users.example.test");
    expect(emailFor("a@b.test", "x")).toBe("a@b.test");
  });
});

describe("local mode is unchanged", () => {
  it("sends the cookie and no Authorization header, never loads Firebase", async () => {
    const { api, calls } = fakeAuth();
    setFirebaseAuthForTests(api);
    const f = vi.fn(async () => resp(200, { ok: true }));
    vi.stubGlobal("fetch", f);
    await http("/review/queue");
    expect(callOf(f, 0)[1].credentials).toBe("include");
    expect(headersOf(f, 0).Authorization).toBeUndefined();
    expect(calls).toEqual([]);
  });
});

describe("firebase mode", () => {
  beforeEach(() => vi.stubEnv("VITE_AUTH_MODE", "firebase"));

  it("sends a bearer ID token and omits cookies", async () => {
    const { api } = fakeAuth();
    setFirebaseAuthForTests(api);
    const f = vi.fn(async () => resp(200, { ok: true }));
    vi.stubGlobal("fetch", f);
    await http("/review/queue");
    expect(callOf(f, 0)[1].credentials).toBe("omit");
    expect(headersOf(f, 0).Authorization).toBe("Bearer tok-1");
  });

  it("on 401 retries once with a forced refresh", async () => {
    const { api, calls } = fakeAuth();
    setFirebaseAuthForTests(api);
    const f = vi.fn().mockResolvedValueOnce(resp(401, {})).mockResolvedValueOnce(resp(200, { ok: 1 }));
    vi.stubGlobal("fetch", f);
    await expect(http("/review/queue")).resolves.toEqual({ ok: 1 });
    expect(headersOf(f, 1).Authorization).toBe("Bearer tok-2");
    expect(calls).toContain("token:true");
    expect(calls).not.toContain("signOut");
  });

  it("signs out of Firebase when the refreshed token is also refused", async () => {
    const { api, calls } = fakeAuth();
    setFirebaseAuthForTests(api);
    vi.stubGlobal("fetch", vi.fn(async () => resp(401, {})));
    await expect(http("/review/queue")).rejects.toMatchObject({ httpStatus: 401 });
    await Promise.resolve();
    await new Promise((r) => setTimeout(r, 0));
    expect(calls).toContain("signOut");
  });

  it("signIn uses the SDK, then asks the API for the role; signOut ends the Firebase session", async () => {
    vi.stubEnv("VITE_AUTH_EMAIL_DOMAIN", "users.example.test");
    const { api, calls } = fakeAuth();
    setFirebaseAuthForTests(api);
    const f = vi.fn(async () => resp(200, { role: "doctor" }));
    vi.stubGlobal("fetch", f);
    await expect(signIn("dr.rao", "pw-not-real")).resolves.toBe("doctor");
    expect(calls[0]).toBe("signIn:dr.rao@users.example.test");
    expect(String(callOf(f, 0)[0])).toMatch(/\/auth\/me$/);
    expect(f.mock.calls.some((c: unknown[]) => String(c[0]).includes("/auth/login"))).toBe(false);
    await signOut();
    expect(calls).toContain("signOut");
    expect(f.mock.calls.some((c: unknown[]) => String(c[0]).includes("/auth/logout"))).toBe(false);
  });
});
