import { describe, expect, it } from "vitest";
import type { CareState } from "../../api/types";
import { DEFAULTS } from "../../api/patientExtras";
import { EXTRA } from "../../components/i18nExtra";
import { sampleOwnAnswers } from "../../mocks/ownAnswers";
import { buildMockView } from "./mockView";
import { doseLine, fmtTime, reasonText } from "./portalTypes";

const noop = () => undefined;
const st = (today: "none" | "taken" | "missed", requests: unknown[] = []) => ({ dose: { today }, requests }) as unknown as CareState;
const req = (o: Record<string, unknown>) => ({ id: "r1", patientCode: "PT-0142", kind: "Question", text: "Which foods should I eat?", when: "today, just now", draft: "d", status: "approved", reply: "Please ask at the clinic.", ...o });
const X = EXTRA as Record<string, readonly string[]>;
const tEn = (k: string) => (k === "notTaken" ? "Not taken yet" : X[k]?.[0] ?? k);
const tTe = (k: string) => X[k]?.[1] ?? k;

describe("Home 'Next 3 things' dose line", () => {
  it("shows Done only when taken; a missed dose is shown as missed", () => {
    expect(doseLine("taken", false, tEn)).toBe("✓ Done");
    expect(doseLine("taken", true, tEn)).toContain("marked by Supporter");
    expect(doseLine("missed", false, tEn)).toBe("✕ Missed today");
    expect(doseLine("missed", false, tEn)).not.toContain("Done");
    expect(doseLine("none", false, tEn)).toBe("Not taken yet");
  });
});

describe("consent: Share with my Supporter drives the Supporter view", () => {
  it("on: Supporter may see the week and messages", () => {
    const v = buildMockView(st("none"), DEFAULTS, noop);
    expect(v.sup.allowed).toBe(true);
    expect(v.sup.week("none")).toHaveLength(7);
    expect(v.sup.messages.length).toBeGreaterThan(0);
    expect(v.shareSupporter?.on).toBe(true);
  });
  it("off: allowed is false and nothing is passed to the Supporter", () => {
    const v = buildMockView(st("none"), { ...DEFAULTS, shareSupporter: false }, noop);
    expect(v.sup.allowed).toBe(false);
    expect(v.sup.week("taken")).toEqual([]);
    expect(v.sup.messages).toEqual([]);
    expect(v.shareSupporter?.on).toBe(false);
  });
  it("keeps the telegram consent as the patient set it", () => {
    expect(buildMockView(st("none"), { ...DEFAULTS, consents: { ...DEFAULTS.consents, telegram: false } }, noop).consents.telegram).toBe(false);
  });
});

describe("replies to questions asked in the patient app reach Messages", () => {
  it("threads an approved reply under the question, with no origin on the request", () => {
    const v = buildMockView(st("none", [req({})]), DEFAULTS, noop);
    const m = v.messages[0];
    expect(m.id).toBe("ans-r1");
    expect(m.text).toBe("Please ask at the clinic.");
    expect(m.inReplyTo?.excerpt).toContain("Which foods");
    expect(m.title).toBe("Reply from your doctor");
  });
  it("skips waiting, other patients' and archived items", () => {
    const v = buildMockView(st("none", [req({ id: "a", status: "waiting" }), req({ id: "b", patientCode: "PT-0001" }), req({ id: "c", archived: true })]), DEFAULTS, noop);
    expect(v.messages.some((m) => m.id.startsWith("ans-"))).toBe(false);
  });
  it("the reply title is Telugu when the language is Telugu", () => {
    const v = buildMockView(st("none", [req({})]), DEFAULTS, noop, "te");
    expect(v.messages[0].title).toBe(EXTRA.replyTitle[1]);
  });
});

describe("Telugu sample set", () => {
  const te = buildMockView(st("none"), DEFAULTS, noop, "te");
  const en = buildMockView(st("none"), DEFAULTS, noop, "en");
  const latin = /[A-Za-z]{4,}/;
  it("picks Telugu texts by language and keeps ids", () => {
    expect(te.messages.map((m) => m.id)).toEqual(en.messages.map((m) => m.id));
    for (const m of te.messages) { expect(m.title).not.toMatch(latin); expect(m.text).not.toMatch(latin); }
    for (const a of [...te.upcoming, ...te.past]) { expect(a.when).not.toMatch(latin); expect(a.place).not.toMatch(latin); }
    for (const r of te.pastRequests) { expect(r.text).not.toMatch(latin); expect(r.when).not.toMatch(latin); }
    for (const m of te.medicines ?? []) { expect(m.label).not.toMatch(latin); expect(m.when).not.toMatch(latin); }
    expect(en.messages[0].title).toBe("Bring your medicine strip");
  });
  it("has no placeholder clinic number", () => {
    expect(en.clinicPhone).toBe("");
    expect(te.clinicPhone).toBe("");
  });
  it("formats times and reasons in Telugu, stored values stay English", () => {
    expect(fmtTime("7:00 pm", "en")).toBe("7:00 pm");
    expect(fmtTime("7:00 pm", "te")).toBe("రాత్రి 7:00");
    expect(fmtTime("8:00 am", "te")).toBe("ఉదయం 8:00");
    expect(fmtTime("odd", "te")).toBe("odd");
    expect(reasonText("Ran out of tablets", tTe)).toBe(EXTRA.mrRanOut[1]);
    expect(reasonText("free text", tEn)).toBe("free text");
  });
});

describe("About my record sample answers match the Home cards", () => {
  const text = (lang: "en" | "te", f: Parameters<typeof sampleOwnAnswers>[1]) => Object.fromEntries(sampleOwnAnswers(lang, f).map((a) => [a.topic, a.answer_text]));
  it("uses the streak and next visit shown on Home, in both languages", () => {
    for (const lang of ["en", "te"] as const) {
      const v = buildMockView(st("taken"), DEFAULTS, noop, lang);
      const a = text(lang, { streak: v.streak, nextVisit: v.nextVisitText ?? "", week: v.sup.week("taken") });
      expect(a.streak).toContain(String(v.streak));
      expect(a.streak).not.toContain(" 6 ");
      expect(a.next_visit).toContain(v.nextVisitText);
      expect(sampleOwnAnswers(lang).every((x) => x.lang === lang)).toBe(true);
    }
  });
  it("the week counts follow the same last-7-days strip", () => {
    const a = text("en", { streak: 12, nextVisit: "x", week: ["o", "o", "m", "o", "o", "o", "o"] });
    expect(a.missed_week).toBe("You missed 1 dose in the last 7 days.");
    expect(a.taken_week).toBe("You took 6 of 7 doses in the last 7 days.");
    expect(text("en", { streak: 1, nextVisit: "x", week: ["o", "o", "o", "o", "o", "o", "o"] }).missed_week).toMatch(/did not miss/);
  });
  it("Telugu answers are Telugu and have no drug or disease-name wording", () => {
    const all = sampleOwnAnswers("te");
    for (const a of all) { expect(a.question).not.toMatch(/[A-Za-z]{4,}/); expect(a.answer_text).not.toMatch(/\bTB\b|tubercul/i); }
    expect(all.some((a) => /[ఀ-౿]/.test(a.answer_text ?? ""))).toBe(true);
  });
});
