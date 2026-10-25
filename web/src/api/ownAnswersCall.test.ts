import { describe, expect, it, vi } from "vitest";

let impl: (path: string) => Promise<unknown> = async () => [];
const seen: string[] = [];
vi.mock("./http", () => ({ http: (path: string) => { seen.push(path); return impl(path); } }));
vi.mock("./index", () => ({ USE_MOCK: false }));

import { ownAnswersServer } from "./serverCalls";

describe("ownAnswersServer", () => {
  it("reads /portal/answers and returns mapped, ordered cards", async () => {
    impl = async () => [
      { topic: "advice", question: "q", answer_text: "ask your care team", as_of: null, lang: "te" },
      { topic: "next_visit", question: "Qn", answer_text: "An", as_of: "2026-10-25", lang: "te" },
      { topic: "streak", question: "Qs", answer_text: "As", as_of: "2026-10-25", lang: "te" },
    ];
    const r = await ownAnswersServer();
    expect(seen).toContain("/portal/answers");
    expect(r.cards.map((c) => c.topic)).toEqual(["streak", "next_visit"]);
    expect(r.advice?.answerText).toBe("ask your care team");
  });
  it("rejects on a server error so the screen shows its error state with a retry", async () => {
    impl = async () => { throw new Error("boom"); };
    const out = await ownAnswersServer().then(() => "ok", (e: Error) => e.message);
    expect(out).toBe("boom");
  });
});
