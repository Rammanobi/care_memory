import { describe, expect, it } from "vitest";
import { mapPortalMe, mapSupporterView } from "../../api/mapping";
import type { PortalSlice } from "../../api/types";
import { buildLiveView } from "./liveView";

const noop = () => undefined;
// Strings that exist only in the sample data (sampleData.ts, mocks/data.ts).
const SAMPLE = ["Ravi", "Lakshmi", "PT-0142", "Anantapur", "Wed 6 pm", "Fri 10 am", "sister", "Forgot to take it", "Can you remind me", "000-000-0000", "Welcome to CareMemory"];

describe("live patient view never shows sample data", () => {
  it("is empty when the server sent nothing", () => {
    const v = buildLiveView(undefined, noop);
    const dump = JSON.stringify({ ...v, reasons: [0, 30, 59].map((i) => v.reasonAt(i)), week: v.sup.week("none") });
    for (const s of SAMPLE) expect(dump).not.toContain(s);
    expect(v).toMatchObject({ live: true, empty: false, name: "", code: "", clinic: "", day: 0, supporter: null, history60: "", recordReady: false, nextVisitText: null, upcoming: [], past: [], pastRequests: [], clinicPhone: null });
    expect(v.reminder).toMatchObject({ current: null, pending: null });
    expect(v.messages).toEqual([]);
    expect(v.sup.allowed).toBe(false);
  });
  it("uses only what /portal/* sent: no relation, no reminder, no visit", () => {
    const me = mapPortalMe({ patient_code: "PT-0900", name: "Asha", clinic: "Test Clinic", day: 3, supporter: { name: "Mina", relation: null }, reminder: null, pending_reminder: null, consents: {} });
    expect(me.supporter).toEqual({ name: "Mina", relation: null });
    expect(me.reminder).toBeNull();
    const p: PortalSlice = { me, consents: { telegram: false, gmail: false, calendar: false }, streak: 0, nextVisit: null, history: "", markedBy: null, record: null, inbox: [] };
    const v = buildLiveView(p, noop);
    expect(v).toMatchObject({ name: "Asha", code: "PT-0900", day: 3, nextVisitText: null, recordReady: false });
    expect(v.supporter?.relation).toBeNull();
    expect(v.reminder.current).toBeNull();
  });
  it("falls back from nextVisit to the first upcoming visit the server listed, else nothing", () => {
    const base: PortalSlice = { consents: { telegram: false, gmail: false, calendar: false }, streak: 0, nextVisit: null, history: "", markedBy: null, record: { days: [], upcoming: [{ id: "a", kind: "lab", title: "Lab", when: "Mon", place: "X" }, { id: "b", kind: "visit", title: "V", when: "Tue 4 pm", place: "X" }], past: [] }, inbox: [] };
    expect(buildLiveView(base, noop).nextVisitText).toBe("Tue 4 pm");
    expect(buildLiveView({ ...base, nextVisit: "Thu 9 am" }, noop).nextVisitText).toBe("Thu 9 am");
    expect(buildLiveView({ ...base, record: { days: [], upcoming: [], past: [] } }, noop).nextVisitText).toBeNull();
  });
  it("Supporter view: relation optional, not allowed stays closed", () => {
    const sv = mapSupporterView({ patient_code: "PT-0900", patient_name: "Asha", supporter_name: "Mina", relation: null, allowed: false, today: "none", week: "", messages: [] });
    expect(sv.relation).toBeNull();
    const v = buildLiveView({ consents: { telegram: false, gmail: false, calendar: false }, streak: 0, nextVisit: null, history: "", markedBy: null, record: null, inbox: [], supporter: sv }, noop);
    expect(v.sup).toMatchObject({ patientName: "Asha", supporterName: "Mina", relation: null, allowed: false });
    expect(v.sup.week("none")).toEqual([]);
  });
});

describe("live screens do not import sample data", () => {
  const raw = import.meta.glob(["./*.ts", "./*.tsx", "../Supporter/*.tsx"], { query: "?raw", import: "default", eager: true }) as Record<string, string>;
  const live = Object.entries(raw).filter(([f]) => !/sampleData|mockView|\.test\./.test(f));
  it("covers the live screens", () => expect(live.length).toBeGreaterThanOrEqual(10));
  it.each(live)("%s has no sampleData import", (_f, src) => {
    expect(src).not.toMatch(/from\s+["'][^"']*sampleData["']/);
  });
});
