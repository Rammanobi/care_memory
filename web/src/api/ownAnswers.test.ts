import { describe, expect, it } from "vitest";
import { asOfWhen, mapOwnAnswers, type WireOwnAnswer } from "./mapping";
import { EXTRA } from "../components/i18nExtra";
import { sampleOwnAnswers } from "../mocks/ownAnswers";

const w = (topic: string, extra: Partial<WireOwnAnswer> = {}): WireOwnAnswer => ({ topic, question: `Q ${topic}`, answer_text: `A ${topic}`, numbers: { n: 3 }, as_of: "2026-10-25", lang: "en", ...extra });

describe("mapOwnAnswers", () => {
  it("maps fields to camelCase and drops numbers", () => {
    const { cards } = mapOwnAnswers([w("streak")]);
    expect(cards).toEqual([{ topic: "streak", question: "Q streak", answerText: "A streak", asOf: "2026-10-25", lang: "en" }]);
  });
  it("orders cards by topic, whatever order the server sent", () => {
    const r = mapOwnAnswers([w("last_refill"), w("advice"), w("next_visit"), w("streak"), w("missed_week"), w("taken_week")]);
    expect(r.cards.map((c) => c.topic)).toEqual(["taken_week", "missed_week", "streak", "next_visit", "last_refill"]);
  });
  it("history replaces the three dose cards and keeps its server text as is", () => {
    const text = "There is not enough history yet. Keep sending your daily check-in.";
    const r = mapOwnAnswers([w("history", { answer_text: text }), w("next_visit"), w("last_refill"), w("advice")]);
    expect(r.cards.map((c) => c.topic)).toEqual(["history", "next_visit", "last_refill"]);
    expect(r.cards[0].answerText).toBe(text);
  });
  it("keeps advice as a separate footer, never as a chip", () => {
    const r = mapOwnAnswers([w("advice", { answer_text: "For any question about your medicines, food or symptoms, ask your care team." }), w("streak")]);
    expect(r.advice?.answerText).toMatch(/ask your care team/);
    expect(r.cards.some((c) => c.topic === "advice")).toBe(false);
  });
  it("handles no advice, empty, null and bad rows", () => {
    expect(mapOwnAnswers([w("streak")]).advice).toBeNull();
    expect(mapOwnAnswers([])).toEqual({ cards: [], advice: null });
    expect(mapOwnAnswers(null)).toEqual({ cards: [], advice: null });
    const r = mapOwnAnswers([w("streak", { answer_text: " " }), w("mystery"), w("next_visit", { question: "" })]);
    expect(r.cards).toEqual([]);
  });
  it("sample cards: 5 questions plus advice, no drug or TB wording", () => {
    const r = mapOwnAnswers(sampleOwnAnswers());
    expect(r.cards.map((c) => c.topic)).toEqual(["taken_week", "missed_week", "streak", "next_visit", "last_refill"]);
    expect(r.advice).not.toBeNull();
    expect(JSON.stringify(r)).not.toMatch(/\bTB\b|tubercul/i);
  });
});

describe("asOfWhen", () => {
  const now = new Date(2026, 9, 25, 9);
  it("today, yesterday, older, unreadable", () => {
    expect(asOfWhen("2026-10-25", now)).toEqual({ kind: "today" });
    expect(asOfWhen("2026-10-25T03:00:00+00:00", now)).toEqual({ kind: "today" });
    expect(asOfWhen("2026-10-24", now)).toEqual({ kind: "yesterday" });
    expect(asOfWhen("2026-10-20", now)?.kind).toBe("date");
    expect(asOfWhen(null, now)).toBeNull();
    expect(asOfWhen("soon", now)).toBeNull();
  });
});

describe("strings", () => {
  it("every About-my-record label has EN and TE", () => {
    for (const k of Object.keys(EXTRA).filter((x) => x.startsWith("om"))) {
      const [en, te] = (EXTRA as Record<string, readonly string[]>)[k];
      expect(en.length).toBeGreaterThan(0);
      expect(te.length).toBeGreaterThan(0);
    }
    expect(EXTRA.omError[0]).toBe("Could not load your record summary. Try again.");
  });
});
