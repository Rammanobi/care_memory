import { describe, expect, it } from "vitest";
import { ACCEPT, confidenceLevel, confidenceText, docPill, mapDocReview, mapPortalDoc, uploadProblemFrom, validateUpload, MAX_UPLOAD_BYTES } from "./documents";
import { mapApproval, mapRequest } from "./mapping";
import { emptyNotify, notifyReducer, parseNoticeEvent, unreadCount } from "./notify";
import { ApiError } from "./http";

const wireDoc = { id: "d1", filename: "lab.pdf", mime: "application/pdf", size: 2048, pages: 2, status: "pending_review", extraction: { doc_type: "lab_slip", fields: [{ name: "Date", value: "2026-01-02", confidence: 0.95 }, { name: "Result", value: "12", confidence: 0.4 }], text_excerpt: "Lab report" } };

describe("mapping of data.document", () => {
  it("maps a request item", () => {
    const r = mapRequest({ id: "a1", patient_code: "PT-1", kind: "Document", text: "", when: "2026-01-01T00:00:00Z", draft: "", status: "waiting", due_at: "2026-01-01T02:00:00Z", data: { document: wireDoc } }, 0);
    expect(r.document).toMatchObject({ id: "d1", filename: "lab.pdf", mime: "application/pdf", size: 2048, pages: 2, docType: "lab_slip", textExcerpt: "Lab report" });
    expect(r.document?.fields).toHaveLength(2);
    expect(r.research).toBeUndefined();
  });
  it("maps a review item and ignores junk", () => {
    const a = mapApproval({ approval_id: "u1", tier: "amber", title: "Doc", status: "pending", due_at: "", data: { document: wireDoc } }, undefined, 0);
    expect(a.document?.id).toBe("d1");
    expect(mapDocReview(null)).toBeUndefined();
    expect(mapDocReview({ filename: "x" })).toBeUndefined();
    expect(mapDocReview({ id: "z", extraction: { fields: [{ value: "no name" }, { name: "A", value: 5 }] } })?.fields).toEqual([{ name: "A", value: "5", confidence: null }]);
  });
  it("maps patient documents with status", () => {
    expect(mapPortalDoc({ id: "p1", name: "scan.jpg", status: "with your care team", created_at: "2026-02-03T10:00:00Z" })).toMatchObject({ title: "scan.jpg", date: "2026-02-03", status: "with your care team", summary: "" });
  });
});

describe("confidence", () => {
  it("levels", () => {
    expect(confidenceLevel(0.4)).toBe("low");
    expect(confidenceLevel(0.7)).toBe("medium");
    expect(confidenceLevel(0.95)).toBe("high");
    expect(confidenceLevel(40)).toBe("low");
    expect(confidenceLevel("High")).toBe("high");
    expect(confidenceLevel(null)).toBe("unknown");
    expect(confidenceText(0.95)).toBe("95%");
    expect(confidenceText(null)).toBe("unchecked");
  });
});

describe("upload validation", () => {
  const f = (name: string, type: string, size = 100) => ({ name, type, size });
  it("accepts photos, pdf and text", () => {
    expect(validateUpload(f("a.jpg", "image/jpeg"))).toBeNull();
    expect(validateUpload(f("a.pdf", "application/pdf"))).toBeNull();
    expect(validateUpload(f("a.txt", "text/plain"))).toBeNull();
    expect(validateUpload(f("a.HEIC", ""))).toBeNull();
  });
  it("refuses other types, empty and over 10 MB", () => {
    expect(validateUpload(f("a.exe", "application/octet-stream"))).toBe("upBadType");
    for (const [n, t] of [["a.svg", "image/svg+xml"], ["a.svg", ""], ["a.png", "image/svg+xml"], ["a.html", "text/html"], ["a.zip", "application/zip"], ["a.svg", "image/png"], ["a.tiff", "image/tiff"]]) expect(validateUpload(f(n, t))).toBe("upBadType");
    for (const [n, t] of [["a.png", "image/png"], ["a.jpg", "image/jpeg"], ["a.webp", "image/webp"], ["a.heic", "image/heic"], ["a.heif", "image/heif"], ["a.gif", "image/gif"], ["a.pdf", "application/pdf"], ["a.txt", "text/plain"]]) expect(validateUpload(f(n, t))).toBeNull();
    expect(validateUpload(f("a", ""))).toBe("upBadType");
    expect(validateUpload(f("a.pdf", "application/pdf", 0))).toBe("upEmpty");
    expect(validateUpload(f("a.pdf", "application/pdf", MAX_UPLOAD_BYTES + 1))).toBe("upTooBig");
    expect(validateUpload(f("a.pdf", "application/pdf", MAX_UPLOAD_BYTES))).toBeNull();
  });
  it("turns server failures into plain words", () => {
    expect(uploadProblemFrom(new ApiError(413, "x"))).toBe("upErrTooBig");
    expect(uploadProblemFrom(new ApiError(415, "x"))).toBe("upErrType");
    expect(uploadProblemFrom(new ApiError(429, "x"))).toBe("upErrBusy");
    expect(uploadProblemFrom(new ApiError(401, "x"))).toBe("upErrSignin");
    expect(uploadProblemFrom(new ApiError(500, "x"))).toBe("upErrGeneric");
    expect(uploadProblemFrom(new Error("x"), true)).toBe("upErrNet");
  });
});

describe("status pill", () => {
  it("maps the four server words", () => {
    expect(docPill("received")).toBe("received");
    expect(docPill("with your care team")).toBe("care");
    expect(docPill("added to your record")).toBe("added");
    expect(docPill("could not be used")).toBe("failed");
    expect(docPill("something new")).toBe("care");
    expect(docPill(undefined)).toBe("care");
  });
});

describe("notification reducer: patient_document", () => {
  const ev = (id: string, extra: object = {}) => ({ topic: "review", kind: "patient_document", approval_id: id, patient_code: "PT-9", category: "document", priority: "normal", ...extra });
  it("parses and adds a document notice", () => {
    expect(parseNoticeEvent(ev("a"))).toMatchObject({ kind: "document", id: "a", patientCode: "PT-9", category: "document" });
    expect(parseNoticeEvent({ kind: "patient_document" })).toBeNull();
    const s = notifyReducer(emptyNotify, { t: "event", ev: ev("a"), at: 1 });
    expect(s.notices[0]).toMatchObject({ kind: "document", toast: true, read: false });
    expect(unreadCount(s)).toBe(1);
  });
  it("dedupes and opens like a question", () => {
    let s = notifyReducer(emptyNotify, { t: "event", ev: ev("a"), at: 1 });
    s = notifyReducer(s, { t: "event", ev: ev("a"), at: 2 });
    expect(s.notices).toHaveLength(1);
    s = notifyReducer(s, { t: "open", id: "a" });
    expect(unreadCount(s)).toBe(0);
  });
});

describe("upload accept list", () => {
  it("names only the allowed types, never image/* or svg", () => {
    expect(ACCEPT).not.toMatch(/image\/\*|svg|html|zip/);
    for (const x of ["image/png", "image/jpeg", "image/webp", "image/heic", "image/heif", "image/gif", ".pdf", ".txt"]) expect(ACCEPT).toContain(x);
  });
});
