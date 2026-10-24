import { describe, expect, it } from "vitest";
import { ABSTAIN_TEXT, isAbstain, parseCitations, scopedQuestion, snippetsFrom } from "./citations";
import { mapQueryAnswer } from "./mapping";

const A = "D-1a2b3c4d", B = "D-5e6f7a8b";
describe("parseCitations", () => {
  it("parses several refs in one answer", () => {
    const g = parseCitations(`One [${A}]. Two [${B}].`, new Set([A, B]));
    expect(g.filter((x) => x.t === "ref")).toEqual([{ t: "ref", ref: A, known: true }, { t: "ref", ref: B, known: true }]);
    expect(g.map((x) => (x.t === "text" ? x.v : "")).join("")).toBe("One . Two .");
  });
  it("parses adjacent refs and comma lists", () => {
    expect(parseCitations(`x [${A}][${B}]`, { [A]: 1 }).filter((x) => x.t === "ref")).toEqual([{ t: "ref", ref: A, known: true }, { t: "ref", ref: B, known: false }]);
    expect(parseCitations(`x [${A}, ${B}]`).filter((x) => x.t === "ref").map((x) => (x.t === "ref" ? x.ref : ""))).toEqual([A, B]);
  });
  it("flags an unknown ref", () => {
    expect(parseCitations(`x [${A}]`, new Set([B]))[1]).toEqual({ t: "ref", ref: A, known: false });
  });
  it("returns plain text when there are no refs", () => {
    expect(parseCitations("Nothing here [1] [E-0431].")).toEqual([{ t: "text", v: "Nothing here [1] [E-0431]." }]);
    expect(parseCitations("")).toEqual([]);
  });
});

describe("record answers", () => {
  it("detects the abstain line", () => {
    expect(isAbstain(ABSTAIN_TEXT)).toBe(true);
    expect(isAbstain(" Not in the record yet.\n")).toBe(true);
    expect(isAbstain("Something else.")).toBe(false);
  });
  it("keeps evidence rows and prefixes the patient code", () => {
    const rows = [{ ref: A, date: "2026-03-03", kind: "event", snippet: "Missed." }, { x: 1 }];
    expect(snippetsFrom(rows)).toEqual({ [A]: { date: "2026-03-03", kind: "event", snippet: "Missed." } });
    expect(scopedQuestion("PT-0142", " why? ")).toBe("PT-0142: why?");
    expect(scopedQuestion(null, "why?")).toBe("why?");
  });
  it("maps a wire answer with D refs and an abstain", () => {
    const r = mapQueryAnswer({ answer_text: `Missed [${A}].`, numbers_verified: true, tool_calls_used: [{ n: 1, tool: "search_patient_memory", row_count: 1, result_preview: [{ ref: A, date: "d", kind: "daily", snippet: "s" }] }] });
    expect(r.record?.cites[A].kind).toBe("daily");
    expect(r.record?.abstain).toBe(false);
    expect(mapQueryAnswer({ answer_text: ABSTAIN_TEXT, numbers_verified: true }).record?.abstain).toBe(true);
  });
});
