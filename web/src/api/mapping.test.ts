import { describe, expect, it } from "vitest";
import { bulkFailures, mapConsentState, mapDistrict, mapDocument, mapMedicine, mapMessage, mapPatient, dayFromIso, decisionBody, mapApproval, mapConsents, mapPortalMe, mapPortalMsg, mapPortalRequest, mapQueryAnswer, mapRecord, mapServerSettings, mapStatus, mapSupporterView, mapTimeline, mapUsage, toApiToken, toUiCode } from "./mapping";
import { problemFrom } from "./http";

describe("mapping", () => {
  it("converts person tokens and UI codes", () => {
    expect(toUiCode("P-0142")).toBe("PT-0142");
    expect(toApiToken("PT-0142")).toBe("P-0142");
    expect(toUiCode(null)).toBe("");
  });
  it("maps statuses", () => {
    expect(mapStatus("pending")).toBe("waiting");
    expect(mapStatus("edited")).toBe("approved");
    expect(mapStatus("rejected")).toBe("declined");
  });
  it("maps a review item with detail", () => {
    const now = Date.parse("2026-01-01T00:00:00Z");
    const a = mapApproval(
      { approval_id: "u1", patient_token: "P-0142", tier: "red", title: "Card", status: "pending", due_at: "2026-01-01T02:00:00Z", drivers: [{ label: "Misses Thursdays" }] },
      { approval_id: "u1", tier: "red", title: "Card", status: "pending", due_at: "", proposal: { body: "Hello" }, citations: [{ ref: "E-0412" }] },
      now,
    );
    expect(a).toMatchObject({ id: "u1", patientCode: "PT-0142", lane: "red", draft: "Hello", dueMin: 120, refs: ["E-0412"], why: "Misses Thursdays", status: "waiting" });
  });
  it("builds decision bodies (reject always has a reason)", () => {
    expect(decisionBody("approved")).toEqual({ action: "approve" });
    expect(decisionBody("approved", "x")).toEqual({ action: "edit", edited: { body: "x" } });
    expect(decisionBody("declined")).toMatchObject({ action: "reject", reason: expect.any(String) });
  });
  it("maps usage to camelCase", () => {
    expect(mapUsage({ mode: "GREEN", today_spend: 1, today_cap: 2, budget_used: 3, budget: 4, days: [], tasks: [], retries: 0, breaker: 0, billing: 5, provider_pct: 6 })).toMatchObject({ todaySpend: 1, providerPct: 6 });
  });
  it("parses api.Problem, also nested under detail", () => {
    expect(problemFrom(422, { title: "T", code: "reason_required" })).toMatchObject({ httpStatus: 422, code: "reason_required" });
    expect(problemFrom(409, { detail: { title: "Done", code: "already_decided" } }).code).toBe("already_decided");
    expect(problemFrom(500, null).title).toBe("HTTP 500");
  });
  it("maps /portal/me and consents", () => {
    const me = mapPortalMe({ patient_code: "PT-0142", name: "Ravi", clinic: "Anantapur Urban Clinic", day: 60, supporter: { name: "Lakshmi", relation: "sister" }, reminder: "8:00 am", pending_reminder: null, consents: { telegram: true } });
    expect(me).toMatchObject({ code: "PT-0142", name: "Ravi", reminder: "8:00 am", pendingReminder: null, supporter: { name: "Lakshmi", relation: "sister" } });
    expect(mapConsents({ telegram: true })).toEqual({ telegram: true, gmail: false, calendar: false });
  });
  it("maps the record (dose days, visits and labs)", () => {
    const r = mapRecord({ days: [{ date: "2026-08-31", status: "missed", reason: "Forgot to take it" }, { date: "2026-09-01", status: "taken" }], upcoming: [{ id: "a", kind: "visit", title: "Clinic visit", when: "Wed 6 pm", place: "Anantapur" }], past: [] });
    expect(r.days[0]).toMatchObject({ status: "missed", reason: "Forgot to take it" });
    expect(r.days[1].reason).toBeUndefined();
    expect(r.upcoming[0]).toMatchObject({ kind: "visit", when: "Wed 6 pm" });
    const d = dayFromIso("2026-09-01");
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 8, 1]);
  });
  it("maps inbox messages and the Supporter view", () => {
    expect(mapPortalMsg({ id: "m", title: "T", text: "x", created_at: "2026-10-25T11:30:00Z", read: false, for_supporter: true })).toMatchObject({ id: "m", read: false, forSupporter: true, at: "2026-10-25T11:30:00Z" });
    expect(mapSupporterView({ patient_code: "PT-0142", patient_name: "Ravi", supporter_name: "Lakshmi", relation: "sister", allowed: true, today: "none", week: "oooooof", messages: [] })).toMatchObject({ patientName: "Ravi", supporterName: "Lakshmi", allowed: true, week: "oooooof" });
  });
  it("maps a patient's own request with the signed-in patient code", () => {
    const r = mapPortalRequest({ id: "r1", text: "Hi", kind: "Other", when: "2026-10-25T03:42:00Z", status: "approved", reply: "Done" }, "PT-0142");
    expect(r).toMatchObject({ id: "r1", patientCode: "PT-0142", status: "approved", reply: "Done" });
    expect(mapPortalRequest({ id: "r2", text: "Hi", kind: "Other", when: "2026-10-25T03:42:00Z", status: "waiting", reply: null }, "PT-0142").reply).toBeUndefined();
  });
  it("maps timeline rows (only evidence refs get a chip)", () => {
    const base = { day: 60, occurred_at: "2026-10-25T03:30:00Z", type: "x", source: "console", text: "t" };
    expect(mapTimeline({ ...base, id: "B-0102", kind: "dose", ref: "B-0102" })).toMatchObject({ id: "B-0102", chip: true, kind: "dose", reporter: "console" });
    expect(mapTimeline({ ...base, id: "22a8-uuid", kind: "needs_human", ref: null })).toMatchObject({ chip: false, kind: "system" });
  });
  it("splits a query answer into cited sentences and keeps the server's number check", () => {
    const a = mapQueryAnswer({
      answer_text: "2 red drafts are waiting [1]. PT-0087: Approve call today [2].", numbers_verified: true,
      tool_calls_used: [{ n: 1, tool: "list_approvals", row_count: 2 }, { n: 2, tool: "get_patient", row_count: 1 }],
    });
    expect(a.sentences).toEqual([{ text: "2 red drafts are waiting.", refs: ["1"] }, { text: "PT-0087: Approve call today.", refs: ["2"] }]);
    expect(a.sources[0]).toEqual({ n: 1, label: "list approvals: 2 records" });
    expect(a.sources[1].label).toContain("1 record");
    expect(a.verified).toBe(true);
    expect(mapQueryAnswer({ answer_text: "x", numbers_verified: false, refused: true }).refused).toBe(true);
  });
  it("maps server settings with the version", () => {
    expect(mapServerSettings({ version: 3, values: { risk_high: 0.5 }, channels: { telegram: true }, updated_at: null })).toEqual({ version: 3, values: { risk_high: 0.5 }, channels: { telegram: true }, updatedAt: undefined });
  });
  it("lists bulk decisions that need a single retry", () => {
    expect(bulkFailures([{ approval_id: "a", error_code: null }, { approval_id: "b", error_code: "amber_not_viewed" }])).toEqual([{ id: "b", message: "Open this Amber item before approving it" }]);
  });
  it("reports bulk failures with the server message first", () => {
    expect(bulkFailures([{ approval_id: "a", ok: true }, { approval_id: "r", ok: false, error_code: "red_not_bulk", message: "Red one at a time" }, { approval_id: "x", ok: false, error_code: "weird" }]))
      .toEqual([{ id: "r", message: "Red one at a time" }, { id: "x", message: "weird" }]);
  });
  it("maps district with suppressed cells and quiet patients", () => {
    const d = mapDistrict({ as_of: "2026-01-01", small_cell_threshold: 5, clinics: [{ id: "c1", name: "A", area: "x", patients: null, adherence: 80, quiet: null, pending: 2, suppressed: ["patients", "quiet"] }], quiet_patients: [{ code: "PT-0001", clinic: "A", why: "w", adherence: 40, no_data: 6 }], total_patients: null, total_pending_approvals: 2 });
    expect(d.clinics[0]).toMatchObject({ patients: null, suppressed: ["patients", "quiet"] });
    expect(d.quiet[0]).toEqual({ code: "PT-0001", clinic: "A", why: "w", adherence: 40, noData: 6 });
    expect(d).toMatchObject({ threshold: 5, totalPatients: null, totalPending: 2 });
  });
  it("maps documents, medicines, person_id and delivery", () => {
    expect(mapDocument({ id: "d", title: "T", kind: "letter", date: "2026-01-02", summary: "S" })).toEqual({ id: "d", title: "T", kind: "letter", date: "2026-01-02", summary: "S" });
    expect(mapMedicine({ id: "m", label: "Morning tablets", when: "8 am" }).note).toBeNull();
    const m = mapMessage({ id: "1", code: "PT-1", at: "2026-01-01T10:00:00Z", channel: "telegram", text: "hi", approved_by: "Dr", version: 1, status: "sent", delivery: "failed", delivery_error: "blocked" });
    expect(m).toMatchObject({ delivery: "failed", deliveryError: "blocked" });
    expect(mapMessage({ id: "1", code: "PT-1", at: "2026-01-01T10:00:00Z", channel: "t", text: "", approved_by: "", version: 1, status: "sent" }).delivery).toBeUndefined();
    expect(mapPatient({ code: "PT-1", sex: "M", age: 1, day: 1, base: "grn", tag: "", why: "", missed: [], no_data: 0, next_step: "", clinic: "c", visit_this_week: false, quiet: false, next_visit: "", supporter: "Linked", consent: "Active", changes: [], person_id: "u-1" }).personId).toBe("u-1");
  });
  it("derives one consent word from the ledger state", () => {
    expect(mapConsentState({ by_source_purpose: { telegram: { reminders: "granted" }, gmail: { x: "withdrawn" } } })).toBe("Active");
    expect(mapConsentState({ by_source_purpose: { telegram: { reminders: "withdrawn" } } })).toBe("Withdrawn");
    expect(mapConsentState({ by_source_purpose: { telegram: { reminders: "never" } } })).toBe("Pending");
  });
});
