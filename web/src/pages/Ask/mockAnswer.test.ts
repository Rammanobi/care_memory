import { describe, expect, it } from "vitest";
import { makeSeed } from "../../mocks/seed";
import { ABSTAIN_TEXT } from "../../api/citations";
import { cap, mockReply, PATIENT_CHIPS } from "./mockAnswer";

const s = makeSeed();
describe("mock Ask matcher", () => {
  it("abstains on free text with no keyword match", () => {
    for (const scope of [null, "PT-0142"]) {
      const r = mockReply("Is the patient taking alcohol?", scope, s);
      expect(r.record?.abstain).toBe(true);
      expect(r.record?.text).toBe(ABSTAIN_TEXT);
      expect(r.sentences).toEqual([]);
    }
    expect(mockReply("Tell me a joke", null, s).record?.abstain).toBe(true);
    expect(mockReply("Is PT-0142 taking alcohol?", null, s).record?.abstain).toBe(true);
  });
  it("still answers the flagged question", () => {
    const r = mockReply("Why is PT-0142 flagged?", null, s);
    expect(r.record).toBeUndefined();
    expect(r.sentences.length).toBeGreaterThan(1);
    expect(r.sentences.every((x) => x.text[0] === x.text[0].toUpperCase())).toBe(true);
    expect(mockReply("Why is this one flagged?", "PT-0142", s).sentences[0].text).toContain("PT-0142");
  });
  it("answers list questions", () => {
    expect(mockReply("Who has gone quiet?", null, s).sentences[0].text).toMatch(/quiet/);
  });
  it("uses no gendered pronoun in patient chips and capitalises", () => {
    expect(PATIENT_CHIPS.join(" ")).not.toMatch(/\b(her|his|she|he)\b/i);
    expect(cap("no chemist refill")).toBe("No chemist refill");
  });
});
