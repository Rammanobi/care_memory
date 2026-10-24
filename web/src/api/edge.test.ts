import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  bulkFailures, channelName, dayFromIso, decisionBody, fmtWhen, friendlyDeliveryError, mapApproval, mapAudit, mapChannels, mapConsentState, mapConsents,
  mapDistrict, mapMessage, mapPatient, mapPortalMe, mapPortalMsg, mapPortalRequest, mapQueryAnswer, mapRecord, mapRequest, mapStatus, mapTemplate, mapTimeline,
  mapUsage, mergeTasks, splitCitations, toApiToken, toUiCode,
} from "./mapping";
import type { WireMessage, WireRequest, WireReviewItem } from "./mapping";
import { ApiError, forgetSession, getMe, http, NetworkError, problemFrom, sessionState } from "./http";
import { status } from "./status";
import { parseLive, startLive, backoffMs } from "../realtime/sse";

const BANNED = /tuberculosis|\bTB\b|\bT\.B\.|isoniazid|rifampicin|rifampin|pyrazinamide|ethambutol|streptomycin|bedaquiline|linezolid|\bDOTS\b|\bHRZE\b|టీబీ|క్షయ|टीबी|क्षय/i;
const TELUGU = "నాకు దగ్గు ఎక్కువగా ఉంది, మందులు వేసుకున్నాను";
const NOW = Date.parse("2026-01-01T00:00:00Z");

const item = (o: Partial<WireReviewItem> = {}): WireReviewItem => ({ approval_id: "a1", patient_token: "P-0001", tier: "amber", title: "T", status: "pending", due_at: "2026-01-01T01:00:00Z", ...o });

describe("mapping: null, missing and unknown fields", () => {
  it("tolerates a review item with no token, no drivers and no detail", () => {
    const a = mapApproval(item({ patient_token: null, drivers: undefined }), undefined, NOW);
    expect(a).toMatchObject({ patientCode: "", draft: "", refs: [], why: undefined, status: "waiting", dueMin: 60 });
    expect("reply" in a).toBe(false);
  });
  it("tolerates detail with null proposal body and citations without refs", () => {
    const a = mapApproval(item(), { ...item(), proposal: { body: undefined }, citations: [{}, { ref: "" }, { id: "E-1" }] }, NOW);
    expect(a.draft).toBe("");
    expect(a.refs).toEqual(["E-1"]);
  });
  it("tolerates an empty drivers list", () => {
    expect(mapApproval(item({ drivers: [] }), undefined, NOW).why).toBeUndefined();
  });
  it("unknown approval status is treated as waiting, never approved", () => {
    expect(mapStatus("weird" as never)).toBe("waiting");
    expect(mapStatus("manual")).toBe("waiting");
    expect(mapStatus("expired")).toBe("declined");
    expect(mapApproval(item({ status: "weird" as never }), undefined, NOW).status).toBe("waiting");
  });
  it("unknown tier is passed through without throwing", () => {
    expect(mapApproval(item({ tier: "purple" as never }), undefined, NOW).lane).toBe("purple");
  });
  it("approved item carries its draft as the reply", () => {
    expect(mapApproval(item({ status: "edited" }), { ...item(), proposal: { body: "Hi" } }, NOW)).toMatchObject({ status: "approved", reply: "Hi" });
  });
  it("malformed due_at gives NaN minutes, not an exception", () => {
    expect(Number.isNaN(mapApproval(item({ due_at: "not a date" }), undefined, NOW).dueMin)).toBe(true);
    expect(Number.isNaN(mapApproval(item({ due_at: undefined as never }), undefined, NOW).dueMin)).toBe(true);
  });
  it("past due gives negative minutes", () => {
    expect(mapApproval(item({ due_at: "2025-12-31T23:00:00Z" }), undefined, NOW).dueMin).toBe(-60);
  });
  it("tokens and codes round-trip and survive odd input", () => {
    expect(toUiCode(undefined)).toBe("");
    expect(toUiCode("")).toBe("");
    expect(toUiCode("PT-1")).toBe("PT-1");
    expect(toApiToken("PT-PT-1")).toBe("P-PT-1");
    expect(toApiToken("")).toBe("");
    expect(toApiToken(toUiCode("P-0142"))).toBe("P-0142");
  });
  it("maps a request with null reply and unparseable dates", () => {
    const w: WireRequest = { id: "r", patient_code: "PT-1", kind: "Other", text: "x", when: "garbage", draft: "", status: "waiting", reply: null, due_at: "garbage" };
    const r = mapRequest(w, NOW);
    expect(r.when).toBe("garbage");
    expect(r.reply).toBeUndefined();
    expect(Number.isNaN(r.createdAt)).toBe(true);
  });
  it("maps messages with every optional field missing", () => {
    const m = mapMessage({ id: "1", code: "PT-1", at: "x", channel: "", text: "", approved_by: "", version: 1, status: "pending" } as WireMessage);
    expect(m).toMatchObject({ srcId: "", channel: "Unknown channel", status: "sent", at: "x" });
    expect("delivery" in m).toBe(false);
  });
  it("unknown message status collapses to sent, seen stays seen", () => {
    expect(mapMessage({ id: "1", code: "c", at: "x", channel: "gmail", text: "", approved_by: "", version: 1, status: "bogus" as never }).status).toBe("sent");
    expect(mapMessage({ id: "1", code: "c", at: "x", channel: "gmail", text: "", approved_by: "", version: 1, status: "seen" }).status).toBe("seen");
  });
  it("audit entries default null fields", () => {
    expect(mapAudit({ id: 7, at: "x", actor: "a", label: "l", code: null, src_id: null, version: null, note: null })).toMatchObject({ id: "7", code: "", srcId: undefined, version: undefined, note: undefined });
  });
  it("timeline: unknown kind becomes system, missing ref falls back to id", () => {
    const base = { day: 1, occurred_at: "x", type: "t", source: "s", text: "t" };
    expect(mapTimeline({ ...base, id: "u", kind: "alien" })).toMatchObject({ id: "u", kind: "system", chip: false });
    expect(mapTimeline({ ...base, id: "E-1", kind: "dose" })).toMatchObject({ chip: true });
    expect(mapTimeline({ ...base, id: "E-12x", kind: "dose" }).chip).toBe(false);
  });
  it("patient mapping keeps empty lists and unknown personId undefined", () => {
    const p = mapPatient({ code: "PT-1", sex: "F", age: 0, day: 0, base: "grn", tag: "", why: "", missed: [], no_data: 0, next_step: "", clinic: "", visit_this_week: false, quiet: false, next_visit: "", supporter: "Not linked", consent: "", changes: [] });
    expect(p.missed).toEqual([]);
    expect(p.changes).toEqual([]);
    expect(p.personId).toBeUndefined();
  });
  it("portal me with null supporter and no consents", () => {
    const me = mapPortalMe({ patient_code: "PT-1", name: "", clinic: "", day: 0, supporter: null, reminder: "", consents: {} });
    expect(me).toMatchObject({ supporter: null, pendingReminder: null });
    expect(mapConsents(undefined)).toEqual({ telegram: false, gmail: false, calendar: false });
    expect(mapConsents({ telegram: "yes" as never, other: true })).toEqual({ telegram: true, gmail: false, calendar: false });
  });
  it("record with undefined lists and unknown day status", () => {
    const r = mapRecord({ days: [{ date: "2026-01-01", status: "weird" as never, reason: null }] });
    expect(r.upcoming).toEqual([]);
    expect(r.past).toEqual([]);
    expect(r.days[0].reason).toBeUndefined();
  });
  it("record empty days", () => {
    expect(mapRecord({ days: [] }).days).toEqual([]);
  });
  it("appointment note only copied when present", () => {
    const r = mapRecord({ days: [], upcoming: [{ id: "a", kind: "visit", title: "V", when: "w", place: "p" }, { id: "b", kind: "visit", title: "V", when: "w", place: "p", note: "bring card" }] });
    expect("note" in r.upcoming[0]).toBe(false);
    expect(r.upcoming[1].note).toBe("bring card");
  });
  it("portal message: for_supporter missing is false", () => {
    expect(mapPortalMsg({ id: "m", title: "", text: "", created_at: "x", read: false }).forSupporter).toBe(false);
  });
  it("portal request keeps the signed-in code and drops null reply", () => {
    expect(mapPortalRequest({ id: "r", text: "t", kind: "k", when: "bad", status: "waiting", reply: null }, "PT-9")).toMatchObject({ patientCode: "PT-9", reply: undefined, when: "bad" });
  });
  it("district: all-null clinic cells and no suppressed list", () => {
    const d = mapDistrict({ as_of: "x", small_cell_threshold: 5, clinics: [{ id: "c", name: "n", area: "a", patients: null, adherence: null, quiet: null, pending: null }], quiet_patients: [], total_patients: null, total_pending_approvals: 0 });
    expect(d.clinics[0].suppressed).toEqual([]);
    expect(d.quiet).toEqual([]);
  });
  it("templates with odd language and body", () => {
    expect(mapTemplate({ template_id: "t", key: "k", lang: "te", body: TELUGU, status: "approved" })).toEqual({ id: "t", name: "k (te)", text: TELUGU });
  });
  it("usage tasks undefined does not throw", () => {
    expect(mergeTasks(undefined as never)).toEqual([]);
    expect(mapUsage({ mode: "GREEN", today_spend: 0, today_cap: 0, budget_used: 0, budget: 0, days: [], tasks: undefined as never, retries: 0, breaker: 0, billing: 0, provider_pct: 0 }).tasks).toEqual([]);
  });
  it("merged task pct is capped at 100 and flag precedence", () => {
    expect(mergeTasks([{ name: "A", spend: 1, pct: 80, flag: "ok" }, { name: "A", spend: 1, pct: 80, flag: "ok" }])[0]).toMatchObject({ pct: 100, spend: 2 });
  });
  it("channels: empty and unknown names", () => {
    expect(mapChannels({})).toEqual([]);
    expect(mapChannels({ carrier_pigeon: true })[0]).toEqual({ name: "Carrier_pigeon", connected: true, detail: "Connected" });
    expect(channelName("  TELEGRAM ")).toBe("Telegram");
    expect(channelName("")).toBe("Unknown channel");
  });
  it("consent word with empty or missing ledger is Pending", () => {
    expect(mapConsentState({})).toBe("Pending");
    expect(mapConsentState({ by_source_purpose: {} })).toBe("Pending");
  });
  it("granted beats withdrawn", () => {
    expect(mapConsentState({ by_source_purpose: { a: { x: "withdrawn" }, b: { y: "granted" } } })).toBe("Active");
  });
});

describe("mapping: empty lists, long text, Telugu", () => {
  it("mapQueryAnswer with empty text and no tool calls", () => {
    expect(mapQueryAnswer({ answer_text: "", numbers_verified: false })).toEqual({ sentences: [], sources: [], verified: false, refused: false });
  });
  it("mapQueryAnswer only citations", () => {
    expect(mapQueryAnswer({ answer_text: "[1] [2]", numbers_verified: true }).sentences).toEqual([]);
  });
  it("mapQueryAnswer singular and plural record labels, long text", () => {
    const long = "A fact. ".repeat(2000) + "[1]";
    const a = mapQueryAnswer({ answer_text: long, numbers_verified: true, tool_calls_used: [{ n: 1, tool: "x_y", row_count: 0 }, { n: 2, tool: "z", row_count: 1 }] });
    expect(a.sentences.length).toBeGreaterThan(1000);
    expect(a.sources.map((s) => s.label)).toEqual(["x y: 0 records", "z: 1 record"]);
  });
  it("mapQueryAnswer keeps Telugu sentences", () => {
    const a = mapQueryAnswer({ answer_text: `${TELUGU}. Next one [1].`, numbers_verified: true });
    expect(a.sentences[0].text).toContain("దగ్గు");
  });
  it("very long draft text is kept whole and citations stripped", () => {
    const body = "Please take your tablets. ".repeat(5000) + "[E-0001]";
    const { clean, refs } = splitCitations(body);
    expect(refs).toEqual(["E-0001"]);
    expect(clean.length).toBeGreaterThan(100000);
    expect(clean).not.toContain("[E-");
  });
  it("citation tokens: duplicates collapse, lookalikes stay", () => {
    expect(splitCitations("a [E-1] b [E-1]").refs).toEqual(["E-1"]);
    expect(splitCitations("a [X-1] [E-] [e-1]")).toEqual({ clean: "a [X-1] [E-] [e-1]", refs: [] });
    expect(splitCitations("")).toEqual({ clean: "", refs: [] });
  });
  it("Telugu text passes through mapping unchanged", () => {
    const m = mapMessage({ id: "1", code: "PT-1", at: "2026-01-01T10:00:00Z", channel: "telegram", text: TELUGU, approved_by: "డాక్టర్", version: 1, status: "sent" });
    expect(m.text).toBe(TELUGU);
    expect(m.approvedBy).toBe("డాక్టర్");
    const a = mapApproval(item(), { ...item(), proposal: { body: TELUGU } }, NOW);
    expect(a.draft).toBe(TELUGU);
    expect(decisionBody("approved", TELUGU)).toEqual({ action: "edit", edited: { body: TELUGU } });
  });
  it("decisionBody: empty edit text is a plain approve", () => {
    expect(decisionBody("approved", "")).toEqual({ action: "approve" });
  });
  it("duplicate ids are kept by pure mappers (dedupe happens in the adapter)", () => {
    const rows = [item(), item()].map((i) => mapApproval(i, undefined, NOW));
    expect(rows.map((r) => r.id)).toEqual(["a1", "a1"]);
  });
  it("bulk failures: empty, all ok, unknown code", () => {
    expect(bulkFailures([])).toEqual([]);
    expect(bulkFailures([{ approval_id: "a", ok: true }])).toEqual([]);
    expect(bulkFailures([{ approval_id: "a", ok: false }])).toEqual([{ id: "a", message: "Not approved" }]);
    expect(bulkFailures([{ approval_id: "a", error_code: "zzz" }])).toEqual([{ id: "a", message: "zzz" }]);
  });
});

describe("dates", () => {
  const now = new Date(2026, 0, 15, 12, 0);
  it("malformed or empty dates are returned as given", () => {
    expect(fmtWhen("", now)).toBe("");
    expect(fmtWhen("tomorrow-ish", now)).toBe("tomorrow-ish");
    expect(fmtWhen("2026-13-45", now)).toBe("2026-13-45");
  });
  it("same day shows Today, other days show the weekday", () => {
    expect(fmtWhen(new Date(2026, 0, 15, 9, 5).toISOString(), now)).toBe("Today 09:05");
    expect(fmtWhen(new Date(2026, 0, 14, 23, 59).toISOString(), now)).toBe("Wed 23:59");
  });
  it("dayFromIso keeps the calendar day and tolerates junk", () => {
    expect(dayFromIso("2026-02-28").getDate()).toBe(28);
    expect(dayFromIso("2024-02-29").getMonth()).toBe(1);
    expect(() => dayFromIso("")).not.toThrow();
    expect(() => dayFromIso("abc")).not.toThrow();
  });
});

describe("delivery text", () => {
  it("null, empty and mixed-case codes", () => {
    expect(friendlyDeliveryError(null)).toBe("");
    expect(friendlyDeliveryError(undefined)).toBe("");
    expect(friendlyDeliveryError("")).toBe("");
    expect(friendlyDeliveryError("  SKIPPED:QUIET_HOURS ")).toMatch(/quiet hours/);
    expect(friendlyDeliveryError("blocked_by_user")).toBe("blocked by user");
  });
  it("raw underscore codes are never shown for the known skip reasons", () => {
    for (const k of ["no_consent", "quiet_hours", "no_channel", "banned_term", "something_new"]) {
      expect(friendlyDeliveryError(`skipped:${k}`)).not.toMatch(/_|skipped:/);
    }
  });
});

describe("banned terms never appear in patient-facing mapped strings", () => {
  const strings = () => [
    ...["no_consent", "quiet_hours", "no_channel", "banned_term", "other_thing"].map((k) => friendlyDeliveryError(`skipped:${k}`)),
    ...["red_not_bulk", "amber_not_viewed", "already_decided", "not_found", "reason_required", "banned_term"].flatMap((c) => bulkFailures([{ approval_id: "x", error_code: c }]).map((b) => b.message)),
    ...["telegram", "tg", "gmail", "email", "calendar", "sms", "whatsapp", "app", "portal", "", "zzz"].map(channelName),
    ...mapChannels({ telegram: true, gmail: false }).flatMap((c) => [c.name, c.detail]),
    decisionBody("declined").reason as string,
  ];
  it("helper-produced strings are clean", () => {
    for (const s of strings()) expect(s, s).not.toMatch(BANNED);
  });
  it("the check itself catches the terms (sanity)", () => {
    for (const bad of ["TB", "tuberculosis", "Rifampicin", "isoniazid", "DOTS", "టీబీ", "T.B."]) expect(bad).toMatch(BANNED);
    for (const ok of ["Tablets", "Stable", "dots on the map".replace("dots", "dot")]) expect(ok).not.toMatch(BANNED);
  });
  it("mapped patient-facing fields are clean when the server text is clean", () => {
    const me = mapPortalMe({ patient_code: "PT-1", name: "Ravi", clinic: "Anantapur Urban Clinic", day: 3, reminder: "8:00 am", consents: {} });
    const msg = mapPortalMsg({ id: "m", title: "Reminder", text: "Please take your medicine", created_at: "x", read: false });
    for (const s of [me.name, me.clinic, me.reminder, msg.title, msg.text]) expect(s).not.toMatch(BANNED);
  });
});

describe("source scan: no banned wording in patient-facing UI strings", () => {
  it("web/src (non-test) has no TB or drug words in string literals", () => {
    const mods = import.meta.glob(["../**/*.ts", "../**/*.tsx", "!../**/*.test.ts", "!../**/*.test.tsx"], { query: "?raw", import: "default", eager: true }) as Record<string, string>;
    const files = Object.keys(mods);
    expect(files.length).toBeGreaterThan(10);
    const hits: string[] = [];
    const re = /tuberculosis|\bTB\b|isoniazid|rifampicin|rifampin|pyrazinamide|ethambutol|streptomycin|bedaquiline|linezolid|టీబీ|क्षय|క్షయ|टीबी/i;
    for (const f of files) {
      mods[f].split("\n").forEach((line: string, i: number) => {
        if (re.test(line)) hits.push(`${f}:${i + 1}`);
      });
    }
    expect(hits).toEqual([]);
  });
});

describe("http adapter: errors and network failure", () => {
  const assign = vi.fn();
  const resp = (code: number, body?: unknown, ct = "application/json") =>
    new Response(body === undefined ? null : typeof body === "string" ? body : JSON.stringify(body), { status: code, headers: ct ? { "content-type": ct } : {} });

  beforeEach(() => {
    vi.useFakeTimers();
    forgetSession(null);
    status.setOffline(false);
    status.toast(null);
    assign.mockReset();
    vi.stubGlobal("location", { pathname: "/review", assign });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
  const settle = async <T,>(p: Promise<T>) => {
    const r = p.then((v) => ({ v }), (e) => ({ e }));
    await vi.runAllTimersAsync();
    return r;
  };

  it("401 on a data route marks signed out, toasts and redirects home", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resp(401, { title: "Unauthorized" })));
    const r = (await settle(http("/review/queue"))) as { e: ApiError };
    expect(r.e).toBeInstanceOf(ApiError);
    expect(r.e.httpStatus).toBe(401);
    expect(sessionState.signedIn).toBe(false);
    expect(status.get().toast).toMatch(/session ended/i);
    expect(assign).toHaveBeenCalledWith("/");
  });
  it("401 on /auth/me does not toast or redirect", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resp(401, { title: "Unauthorized" })));
    await settle(http("/auth/me"));
    expect(assign).not.toHaveBeenCalled();
    expect(status.get().toast).toBeNull();
  });
  it("401 on login (wrong password) leaves the session state alone and does not redirect", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resp(401, { title: "Bad credentials", code: "bad_login" })));
    const r = (await settle(http("/auth/login", { method: "POST", body: {} }))) as { e: ApiError };
    expect(r.e.code).toBe("bad_login");
    expect(sessionState.signedIn).toBeNull();
    expect(assign).not.toHaveBeenCalled();
  });
  it("no redirect loop when already on the sign-in page", async () => {
    vi.stubGlobal("location", { pathname: "/", assign });
    vi.stubGlobal("fetch", vi.fn(async () => resp(401, {})));
    await settle(http("/patients"));
    expect(assign).not.toHaveBeenCalled();
  });
  it("403 is an ApiError, not retried, session stays signed in", async () => {
    forgetSession(true);
    const f = vi.fn(async () => resp(403, { title: "Forbidden", code: "role_not_allowed" }));
    vi.stubGlobal("fetch", f);
    const r = (await settle(http("/admin/usage"))) as { e: ApiError };
    expect(r.e).toMatchObject({ httpStatus: 403, code: "role_not_allowed" });
    expect(f).toHaveBeenCalledTimes(1);
    expect(sessionState.signedIn).toBe(true);
    expect(status.get().offline).toBe(false);
  });
  it("404 with an HTML body still yields an ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resp(404, "<html>nope</html>", "text/html")));
    const r = (await settle(http("/nope"))) as { e: ApiError };
    expect(r.e).toMatchObject({ httpStatus: 404, title: "HTTP 404" });
  });
  it("500 is not retried and is not shown as offline", async () => {
    const f = vi.fn(async () => resp(500, { title: "Boom" }));
    vi.stubGlobal("fetch", f);
    const r = (await settle(http("/x"))) as { e: ApiError };
    expect(r.e.httpStatus).toBe(500);
    expect(f).toHaveBeenCalledTimes(1);
    expect(status.get().offline).toBe(false);
  });
  it("500 with invalid JSON body does not crash", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resp(500, "{not json")));
    const r = (await settle(http("/x"))) as { e: ApiError };
    expect(r.e).toMatchObject({ httpStatus: 500, title: "HTTP 500" });
  });
  it("502 on GET is retried up to 3 times, then surfaces", async () => {
    const f = vi.fn(async () => resp(502, {}));
    vi.stubGlobal("fetch", f);
    const r = (await settle(http("/x"))) as { e: ApiError };
    expect(f).toHaveBeenCalledTimes(3);
    expect(r.e.httpStatus).toBe(502);
  });
  it("502 then 200 recovers", async () => {
    const f = vi.fn().mockResolvedValueOnce(resp(503, {})).mockResolvedValueOnce(resp(200, { ok: 1 }));
    vi.stubGlobal("fetch", f);
    const r = (await settle(http<{ ok: number }>("/x"))) as { v: { ok: number } };
    expect(r.v).toEqual({ ok: 1 });
  });
  it("POST is never retried on 503", async () => {
    const f = vi.fn(async () => resp(503, {}));
    vi.stubGlobal("fetch", f);
    await settle(http("/review/1/decision", { method: "POST", body: { action: "approve" } }));
    expect(f).toHaveBeenCalledTimes(1);
  });
  it("POST sends the client header and JSON body, GET does not", async () => {
    const f = vi.fn(async () => resp(204));
    vi.stubGlobal("fetch", f);
    await settle(http("/a", { method: "POST", body: { t: TELUGU } }));
    await settle(http("/b"));
    const [, post] = f.mock.calls[0] as unknown as [string, RequestInit];
    const [, get] = f.mock.calls[1] as unknown as [string, RequestInit];
    expect((post.headers as Record<string, string>)["X-CM-Client"]).toBe("web");
    expect(JSON.parse(post.body as string).t).toBe(TELUGU);
    expect((get.headers as Record<string, string>)["X-CM-Client"]).toBeUndefined();
    expect(post.credentials).toBe("include");
  });
  it("204 returns undefined", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resp(204)));
    expect(((await settle(http("/x"))) as { v: unknown }).v).toBeUndefined();
  });
  it("network failure on GET retries then throws NetworkError and flags offline; success clears it", async () => {
    const f = vi.fn(async () => { throw new TypeError("Failed to fetch"); });
    vi.stubGlobal("fetch", f);
    const r = (await settle(http("/x"))) as { e: Error };
    expect(r.e).toBeInstanceOf(NetworkError);
    expect(f).toHaveBeenCalledTimes(3);
    expect(status.get().offline).toBe(true);
    vi.stubGlobal("fetch", vi.fn(async () => resp(200, {})));
    await settle(http("/x"));
    expect(status.get().offline).toBe(false);
  });
  it("network failure on POST is not retried", async () => {
    const f = vi.fn(async () => { throw new TypeError("Failed to fetch"); });
    vi.stubGlobal("fetch", f);
    const r = (await settle(http("/x", { method: "POST", body: {} }))) as { e: Error };
    expect(f).toHaveBeenCalledTimes(1);
    expect(r.e).toBeInstanceOf(NetworkError);
  });
  it("non-Error rejection still becomes a NetworkError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw "weird"; }));
    const r = (await settle(http("/x", { method: "DELETE" }))) as { e: Error };
    expect(r.e).toBeInstanceOf(NetworkError);
    expect(r.e.message).toBe("Network error");
  });
  it("undefined query values are not sent; others are url-encoded", async () => {
    const f = vi.fn(async () => resp(200, {}));
    vi.stubGlobal("fetch", f);
    await settle(http("/x", { query: { a: undefined, b: "x y", c: 0 } }));
    const url = (f.mock.calls[0] as unknown as [string])[0];
    expect(url).toContain("b=x+y");
    expect(url).toContain("c=0");
    expect(url).not.toContain("a=");
  });
  it("problemFrom edge shapes", () => {
    expect(problemFrom(400, undefined).title).toBe("HTTP 400");
    expect(problemFrom(400, "text" as never).title).toBe("HTTP 400");
    expect(problemFrom(400, { detail: "plain string" }).title).toBe("plain string");
    expect(problemFrom(422, { detail: { title: 5, code: 7 } })).toMatchObject({ title: "HTTP 422", code: undefined });
    expect(problemFrom(409, { title: "T", detail: "d" }).message).toBe("d");
    expect(problemFrom(400, { detail: { title: TELUGU } }).title).toBe(TELUGU);
  });
  it("getMe: concurrent callers share one request; logged-out answer is remembered without refetch", async () => {
    const f = vi.fn(async () => resp(401, {}));
    vi.stubGlobal("fetch", f);
    const [a, b] = await Promise.all([settle(getMe()), settle(getMe())]);
    expect((a as { e: ApiError }).e.httpStatus).toBe(401);
    expect((b as { e: ApiError }).e.httpStatus).toBe(401);
    expect(f).toHaveBeenCalledTimes(1);
    const c = (await settle(getMe())) as { e: ApiError };
    expect(c.e.httpStatus).toBe(401);
    expect(f).toHaveBeenCalledTimes(1); // no 401 storm
  });
  it("getMe: success is cached and announces the session once", async () => {
    const ev = vi.fn();
    vi.stubGlobal("window", { dispatchEvent: ev });
    const f = vi.fn(async () => resp(200, { role: "doctor" }));
    vi.stubGlobal("fetch", f);
    expect(((await settle(getMe())) as { v: { role: string } }).v.role).toBe("doctor");
    await settle(getMe());
    expect(f).toHaveBeenCalledTimes(1);
    expect(ev).toHaveBeenCalledTimes(1);
  });
  it("getMe: a 500 does not mark the user signed out and can be retried", async () => {
    const f = vi.fn().mockResolvedValueOnce(resp(500, {})).mockResolvedValueOnce(resp(200, { role: "patient" }));
    vi.stubGlobal("fetch", f);
    await settle(getMe());
    expect(sessionState.signedIn).toBeNull();
    expect(((await settle(getMe())) as { v: { role: string } }).v.role).toBe("patient");
  });
});

describe("SSE: parsing, reconnect, logged-out", () => {
  class FakeES {
    static all: FakeES[] = [];
    onopen: (() => void) | null = null;
    onmessage: ((m: unknown) => void) | null = null;
    onerror: (() => void) | null = null;
    closed = false;
    listeners: Record<string, (m: unknown) => void> = {};
    constructor(public url: string, public opts?: unknown) { FakeES.all.push(this); }
    addEventListener(t: string, f: (m: unknown) => void) { this.listeners[t] = f; }
    close() { this.closed = true; }
  }
  beforeEach(() => {
    vi.useFakeTimers();
    FakeES.all = [];
    vi.stubGlobal("EventSource", FakeES);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("parseLive: heartbeats, arrays, null, numbers, nested and Telugu", () => {
    expect(parseLive(undefined)).toBeNull();
    expect(parseLive(null)).toBeNull();
    expect(parseLive(5)).toBeNull();
    expect(parseLive("   ")).toBeNull();
    expect(parseLive("null")).toBeNull();
    expect(parseLive("{bad")).toBeNull();
    expect(parseLive('{"topic":"x"}', "review")?.topic).toBe("x");
    expect(parseLive("{}", "channels")?.topic).toBe("channels");
    expect(parseLive(`{"ref":"${TELUGU}"}`)?.ref).toBe(TELUGU);
  });
  it("backoff never exceeds 30 s even for huge attempt counts", () => {
    expect(backoffMs(1000)).toBe(30000);
    expect(backoffMs(0)).toBe(1000);
  });
  it("opens with credentials against the right topics", () => {
    const stop = startLive(vi.fn(), () => true);
    expect(FakeES.all[0].url).toContain("topics=review,channels");
    expect(FakeES.all[0].opts).toEqual({ withCredentials: true });
    stop();
  });
  it("a malformed event still triggers a refetch (null payload)", () => {
    const cb = vi.fn();
    const stop = startLive(cb, () => true);
    FakeES.all[0].onmessage?.({ data: "garbage" });
    vi.advanceTimersByTime(200);
    expect(cb).toHaveBeenCalledWith(null);
    stop();
  });
  it("repeated errors keep backing off and never open two connections at once", () => {
    const stop = startLive(vi.fn(), () => true);
    FakeES.all[0].onerror?.();
    FakeES.all[0].onerror?.(); // double error on the same source must not double-schedule
    vi.advanceTimersByTime(1000);
    expect(FakeES.all).toHaveLength(2);
    FakeES.all[1].onerror?.();
    vi.advanceTimersByTime(2000);
    expect(FakeES.all).toHaveLength(3);
    FakeES.all[2].onerror?.();
    vi.advanceTimersByTime(3900);
    expect(FakeES.all).toHaveLength(3);
    vi.advanceTimersByTime(200);
    expect(FakeES.all).toHaveLength(4);
    stop();
  });
  it("backoff resets after a successful open", () => {
    const stop = startLive(vi.fn(), () => true);
    FakeES.all[0].onerror?.();
    vi.advanceTimersByTime(1000);
    FakeES.all[1].onerror?.();
    vi.advanceTimersByTime(2000);
    FakeES.all[2].onopen?.();
    FakeES.all[2].onerror?.();
    vi.advanceTimersByTime(1000);
    expect(FakeES.all).toHaveLength(4); // back to 1 s
    stop();
  });
  it("stopping cancels a pending reconnect", () => {
    const stop = startLive(vi.fn(), () => true);
    FakeES.all[0].onerror?.();
    stop();
    vi.advanceTimersByTime(60000);
    expect(FakeES.all).toHaveLength(1);
  });
  it("logged out: no stream, no polling, no reconnect timers", () => {
    const cb = vi.fn();
    const stop = startLive(cb, () => false);
    vi.advanceTimersByTime(120000);
    expect(FakeES.all).toHaveLength(0);
    expect(cb).not.toHaveBeenCalled();
    stop();
  });
  it("session-up event opens the stream once the user is signed in", () => {
    let signedIn = false;
    const listeners: Record<string, () => void> = {};
    vi.stubGlobal("window", { addEventListener: (n: string, f: () => void) => (listeners[n] = f), removeEventListener: vi.fn() });
    const stop = startLive(vi.fn(), () => signedIn);
    expect(FakeES.all).toHaveLength(0);
    signedIn = true;
    listeners["cm-session-up"]();
    expect(FakeES.all).toHaveLength(1);
    stop();
  });
  it("logging out mid-session closes the stream and does not reopen it", () => {
    let signedIn = true;
    const listeners: Record<string, () => void> = {};
    vi.stubGlobal("window", { addEventListener: (n: string, f: () => void) => (listeners[n] = f), removeEventListener: vi.fn() });
    const stop = startLive(vi.fn(), () => signedIn);
    FakeES.all[0].onopen?.();
    signedIn = false;
    listeners["cm-session"]();
    expect(FakeES.all[0].closed).toBe(true);
    expect(FakeES.all).toHaveLength(1);
    expect(status.get().live).toBe(false);
    stop();
  });
  it("no EventSource support: polling still works, no crash", () => {
    vi.unstubAllGlobals();
    vi.stubGlobal("EventSource", undefined);
    const cb = vi.fn();
    const stop = startLive(cb, () => true);
    vi.advanceTimersByTime(5100);
    expect(cb).toHaveBeenCalledTimes(1);
    stop();
  });
  it("hidden tab skips the poll", () => {
    vi.stubGlobal("document", { visibilityState: "hidden" });
    const cb = vi.fn();
    const stop = startLive(cb, () => true);
    vi.advanceTimersByTime(20000);
    expect(cb).not.toHaveBeenCalled();
    stop();
  });
});
