import { describe, expect, it } from "vitest";
import { mapApproval, mapPortalMsg, mapPortalRequest, mapRequest, type WireRequest } from "./mapping";
import { ApiError } from "./http";
import { bannedTerms, briefParts, friendlyDecisionError, mapOrigin, mapQuestionStatus, mapResearch, patientPill, sortQuestions, waitTone } from "./questions";
import { EXTRA } from "../components/i18nExtra";

const wire = (extra: Partial<WireRequest> = {}): WireRequest => ({
  id: "a1", patient_code: "PT-0001", kind: "Question", text: "", when: "2026-10-25T09:00:00Z", draft: "", status: "waiting", due_at: "2026-10-25T13:00:00Z",
  data: {
    text: "Can I eat curd?",
    origin: { channel: "telegram", question_excerpt: "Can I eat curd?" },
    research: { status: "ready", category: "food", priority: "high", brief: [{ text: "No allergy on record.", refs: ["E-0412"] }], suggested_reply: "Yes, curd is fine.", confidence: "high", model: "m", cost_usd: 0.002, reason: "" },
  },
  ...extra,
});

describe("research / origin mapping", () => {
  it("maps a doctor request item", () => {
    const r = mapRequest(wire(), Date.parse("2026-10-25T09:00:00Z"));
    expect(r.text).toBe("Can I eat curd?"); // from data.text
    expect(r.draft).toBe("Yes, curd is fine."); // prefilled from suggested_reply
    expect(r.origin).toEqual({ channel: "telegram", excerpt: "Can I eat curd?" });
    expect(r.research).toMatchObject({ status: "ready", category: "food", priority: "high", confidence: "high", suggestedReply: "Yes, curd is fine.", costUsd: 0.002 });
    expect(r.research?.brief).toEqual([{ text: "No allergy on record.", refs: ["E-0412"] }]);
  });
  it("falls back to calm defaults for unknown values and drops bad brief rows", () => {
    const x = mapResearch({ status: "weird", category: "x", priority: "!!", brief: [{ text: "" }, { text: "ok", refs: [1, "E-1"] }, null as never] });
    expect(x).toMatchObject({ status: "pending", category: "other", priority: "normal", suggestedReply: "" });
    expect(x?.brief).toEqual([{ text: "ok", refs: ["E-1"] }]);
    expect(mapResearch(null)).toBeUndefined();
    expect(mapOrigin({})).toBeUndefined();
    expect(mapOrigin({ channel: "portal" })).toEqual({ channel: "portal", excerpt: "" });
  });
  it("leaves plain requests without research or origin", () => {
    const r = mapRequest({ ...wire(), data: undefined, text: "Move my visit" }, 0);
    expect(r.research).toBeUndefined();
    expect(r.origin).toBeUndefined();
  });
  it("review items carry research too", () => {
    const a = mapApproval({ approval_id: "x", patient_token: "P-1", tier: "amber", title: "t", status: "pending", due_at: "2026-10-25T13:00:00Z", data: wire().data }, undefined, 0);
    expect(a.research?.status).toBe("ready");
    expect(a.origin?.channel).toBe("telegram");
  });
});

describe("patient question status", () => {
  it("maps waiting|answered (and older approved|declined)", () => {
    expect(mapQuestionStatus("waiting")).toBe("waiting");
    expect(mapQuestionStatus("answered")).toBe("approved");
    expect(mapQuestionStatus("approved")).toBe("approved");
    expect(mapQuestionStatus("rejected")).toBe("declined");
    expect(mapQuestionStatus("???")).toBe("waiting");
    expect(mapQuestionStatus(undefined)).toBe("waiting");
  });
  it("pill: waiting, replied, call", () => {
    expect(patientPill("waiting")).toBe("waiting");
    expect(patientPill("answered")).toBe("replied");
    expect(patientPill("approved")).toBe("replied");
    expect(patientPill("declined")).toBe("call");
  });
  it("portal request and reply link", () => {
    const r = mapPortalRequest({ id: "1", text: "q", kind: "Question", when: "2026-10-25T09:00:00Z", status: "answered", reply: "ok" }, "PT-1");
    expect(r.status).toBe("approved");
    expect(r.reply).toBe("ok");
    const m = mapPortalMsg({ id: "m", title: "t", text: "x", created_at: "2026-10-25T09:00:00Z", read: false, in_reply_to: { approval_id: "a1", question_excerpt: "Can I eat curd?" } });
    expect(m.inReplyTo).toEqual({ approvalId: "a1", excerpt: "Can I eat curd?" });
    expect(mapPortalMsg({ id: "m", title: "t", text: "x", created_at: "", read: true }).inReplyTo).toBeUndefined();
  });
  it("never carries research to the patient side", () => {
    const r = mapPortalRequest({ id: "1", text: "q", kind: "Q", when: "2026-10-25T09:00:00Z", status: "waiting", ...({ data: wire().data } as object) }, "PT-1");
    expect(JSON.stringify(r)).not.toMatch(/research|brief|suggested|confidence/i);
  });
  it("patient-facing strings use no TB or medicine words", () => {
    const keys = ["docReplied", "inReplyTo", "qLoadErr", "qLoadErrS", "tryAgain", "waitingS"] as const;
    for (const k of keys) for (const s of EXTRA[k]) expect(s).not.toMatch(/\btb\b|tubercul|isoniazid|rifamp|pyrazin|ethambutol|streptomycin/i);
    for (const k of keys) expect(EXTRA[k][1].length).toBeGreaterThan(0);
  });
});

describe("doctor reply helpers", () => {
  it("lifts inline citations out of brief text", () => {
    expect(briefParts({ text: "Missed dose [E-0412, D-1a2b3c4d].", refs: ["E-0412", "B-1"] })).toEqual({ text: "Missed dose.", refs: ["E-0412", "B-1", "D-1a2b3c4d"] });
  });
  it("flags banned words", () => {
    expect(bannedTerms("Keep taking your TB medicine, isoniazid daily")).toEqual(["tb", "isoniazid"]);
    expect(bannedTerms("Please come on Friday. Bring the strip.")).toEqual([]);
    expect(bannedTerms("tablet")).toEqual([]);
  });
  it("turns server refusals into plain words", () => {
    expect(friendlyDecisionError(new ApiError(422, "banned_term", "isoniazid", "banned_term"))).toMatch(/cannot be sent to patients/);
    expect(friendlyDecisionError(new ApiError(409, "Conflict"))).toMatch(/already answered/);
    expect(friendlyDecisionError(new Error("fetch failed"))).toMatch(/could not be reached/);
    expect(friendlyDecisionError(new ApiError(500, "Server error", "boom"))).toMatch(/boom/);
  });
  it("SLA colours depend on urgency", () => {
    const m = 60000;
    expect(waitTone(5 * m, "urgent")).toBe("ok");
    expect(waitTone(15 * m, "urgent")).toBe("soon");
    expect(waitTone(31 * m, "urgent")).toBe("late");
    expect(waitTone(31 * m, "normal")).toBe("ok");
    expect(waitTone(5 * 60 * m, "normal")).toBe("late");
  });
  it("sorts urgent first, then oldest", () => {
    const mk = (id: string, p: "normal" | "high" | "urgent", at: number) => ({ id, createdAt: at, research: { status: "ready", category: "other", priority: p, brief: [], suggestedReply: "" } as never });
    expect(sortQuestions([mk("a", "normal", 1), mk("b", "urgent", 9), mk("c", "high", 2), mk("d", "normal", 0)]).map((x) => x.id)).toEqual(["b", "c", "d", "a"]);
  });
});
