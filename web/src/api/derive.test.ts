import { describe, expect, it } from "vitest";
import { atStamp, confText, counts, fmtAt, missedLabel, newestFirst, quietDays, requestLabel, suppress, weekdayName } from "./derive";
import { makeSeed } from "../mocks/seed";

describe("timeline order", () => {
  it("sorts newest first by day then time", () => {
    const rows = ["Day 56 · 08:10", "Day 59 · 08:10", "Day 59 · 18:30", "Day 40 · 08:05", "Day 58 · 10:05"].map((at) => ({ at }));
    expect(newestFirst(rows, (r) => r.at).map((r) => r.at)).toEqual(["Day 59 · 18:30", "Day 59 · 08:10", "Day 58 · 10:05", "Day 56 · 08:10", "Day 40 · 08:05"]);
  });
  it("puts today, yesterday and old days on one day line with one format", () => {
    expect(atStamp("today 07:58", 60)).toEqual({ day: 60, min: 478 });
    expect(fmtAt("yesterday 12:20", 60)).toBe("Day 59 · 12:20");
    expect(fmtAt("2 days ago 10:30", 60)).toBe("Day 58 · 10:30");
    expect(fmtAt("last week 09:00", 60)).toBe("Day 53 · 09:00");
    expect(fmtAt("Day 47 · 8:30", 60)).toBe("Day 47 · 08:30");
  });
  it("seed audit for PT-0142 is sorted newest first", () => {
    const s = makeSeed();
    const a = newestFirst(s.audit.filter((x) => x.code === "PT-0142"), (x) => x.at, 60).map((x) => fmtAt(x.at, 60));
    expect(a).toEqual([...a].sort().reverse().sort((x, y) => atStamp(y).day - atStamp(x).day || atStamp(y).min - atStamp(x).min));
    expect(a.every((x) => /^Day \d+ · \d\d:\d\d$/.test(x))).toBe(true);
  });
});

describe("labels", () => {
  it("maps raw request kinds", () => {
    expect(requestLabel("Question")).toBe("Patient question");
    expect(requestLabel("dose")).toBe("Dose question");
    expect(requestLabel("Reminder time")).toBe("Reminder time change");
  });
  it("renders confidence in words", () => {
    expect(confText("High")).toBe("High confidence");
    expect(confText("Low")).toBe("Low confidence");
    expect(confText("Seen once")).toBe("Seen once");
    expect(confText("Unknown")).toBe("Not known yet");
    expect(confText("Seen once")).not.toMatch(/confidence/);
  });
  it("uses a real weekday", () => {
    expect(weekdayName(new Date("2026-10-25T12:00:00"))).toBe("Sunday");
  });
});

describe("counts and quiet days", () => {
  const s = makeSeed();
  it("derives quiet days from noData only", () => {
    const p = s.patients.find((x) => x.code === "PT-0198")!;
    expect(quietDays(p)).toBe("6 days");
    expect(p.why).toContain("6 days");
    expect(missedLabel(p)).toBe("no data for 6 days");
    for (const q of s.patients.filter((x) => x.quiet)) expect(q.why).toContain(`${q.noData} days`);
  });
  it("counts patients, and requests apart", () => {
    const c = counts(s);
    expect(c.all).toBe(20);
    expect(c.requests).toBeLessThanOrEqual(c.all);
    expect(c.pendingRequests).toBeGreaterThanOrEqual(c.requests);
  });
  it("suppresses counts of 1 to 4", () => {
    expect(suppress(0)).toBe(0);
    expect(suppress(1)).toBeNull();
    expect(suppress(4)).toBeNull();
    expect(suppress(5)).toBe(5);
  });
});

describe("seed data", () => {
  const s = makeSeed();
  it("has two document requests, one with no fields", () => {
    const docs = s.requests.filter((r) => r.document);
    expect(docs).toHaveLength(2);
    expect(docs.some((r) => r.document!.fields.length === 0)).toBe(true);
    const conf = new Set(docs.flatMap((r) => r.document!.fields.map((f) => f.confidence)));
    expect(conf).toEqual(new Set(["high", "medium", "low"]));
  });
  it("keeps drug names out of every approved reply", () => {
    for (const r of [...s.requests, ...s.approvals]) if (r.status === "approved") expect(r.reply ?? "").not.toMatch(/paracetamol/i);
    for (const m of s.messages) expect(m.text).not.toMatch(/paracetamol|\bdal\b|\beggs\b/i);
  });
  it("research brief claims match the evidence they cite", () => {
    const q = s.requests.find((r) => r.id === "rq-q1")!;
    for (const b of q.research!.brief) for (const ref of b.refs) expect(s.evidence.find((e) => e.id === ref)).toBeTruthy();
    expect(s.evidence.find((e) => e.id === "E-0447")!.text).toMatch(/headache/);
    expect(q.research!.brief[0].refs).toEqual(["E-0447"]);
  });
  it("gives the visit request its own evidence", () => {
    const r = s.requests.find((x) => x.id === "rq-1")!;
    expect(r.refs).toContain("E-0446");
    expect(s.evidence.find((e) => e.id === "E-0446")!.text).toMatch(/visit/);
  });
});
