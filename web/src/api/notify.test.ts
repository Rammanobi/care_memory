import { describe, expect, it } from "vitest";
import { emptyNotify, notifyReducer, parseQuestionEvent, titleWithCount, unreadCount, urgentOpen, type NotifyAction } from "./notify";

const ev = (id: string, priority = "normal", extra: object = {}) => ({ topic: "review", kind: "patient_question", approval_id: id, patient_code: "PT-1", category: "medicine", priority, ...extra });
const run = (...a: NotifyAction[]) => a.reduce(notifyReducer, emptyNotify);

describe("notification reducer", () => {
  it("ignores other events", () => {
    expect(parseQuestionEvent({ kind: "approval_decided", approval_id: "a" })).toBeNull();
    expect(parseQuestionEvent({ kind: "patient_question" })).toBeNull();
    expect(run({ t: "event", ev: { kind: "x" }, at: 1 })).toBe(emptyNotify);
  });
  it("adds a notice and counts unread", () => {
    const s = run({ t: "event", ev: ev("a"), at: 1 }, { t: "event", ev: ev("b", "high"), at: 2 });
    expect(unreadCount(s)).toBe(2);
    expect(s.notices[0]).toMatchObject({ id: "b", priority: "high", category: "medicine", patientCode: "PT-1", toast: true });
  });
  it("dedupes the same approval_id (SSE reconnect)", () => {
    const s = run({ t: "event", ev: ev("a"), at: 1 }, { t: "event", ev: ev("a"), at: 5 });
    expect(s.notices).toHaveLength(1);
    expect(s.notices[0].at).toBe(1);
  });
  it("upgrades a repeated notice to urgent", () => {
    const s = run({ t: "event", ev: ev("a"), at: 1 }, { t: "hide", id: "a" }, { t: "event", ev: ev("a", "urgent"), at: 2 });
    expect(s.notices[0]).toMatchObject({ priority: "urgent", toast: true });
    expect(s.notices).toHaveLength(1);
  });
  it("urgent toast persists until opened; normal can be hidden", () => {
    let s = run({ t: "event", ev: ev("u", "urgent"), at: 1 }, { t: "event", ev: ev("n"), at: 2 });
    s = notifyReducer(s, { t: "hide", id: "u" });
    s = notifyReducer(s, { t: "dismiss", id: "u" });
    s = notifyReducer(s, { t: "hide", id: "n" });
    expect(s.notices.find((n) => n.id === "u")?.toast).toBe(true);
    expect(s.notices.find((n) => n.id === "n")).toMatchObject({ toast: false, read: false }); // hidden, still unread
    s = notifyReducer(s, { t: "pageSeen" });
    expect(unreadCount(s)).toBe(1); // the urgent one still waits
    expect(urgentOpen(s)).toBe(true);
    s = notifyReducer(s, { t: "open", id: "u" });
    expect(unreadCount(s)).toBe(0);
    expect(urgentOpen(s)).toBe(false);
    expect(s.notices.every((n) => !n.toast)).toBe(true);
  });
  it("answered elsewhere clears the notice", () => {
    const s = run({ t: "event", ev: ev("u", "urgent"), at: 1 }, { t: "resolved", ids: ["u"] });
    expect(unreadCount(s)).toBe(0);
    expect(s.notices[0].toast).toBe(false);
  });
  it("falls back for unknown category and priority", () => {
    expect(parseQuestionEvent(ev("a", "wild", { category: "zzz" }))).toMatchObject({ category: "other", priority: "normal" });
  });
  it("tab title", () => {
    expect(titleWithCount("CareMemory", 3)).toBe("(3) CareMemory");
    expect(titleWithCount("CareMemory", 0)).toBe("CareMemory");
  });
});
