import { describe, expect, it } from "vitest";
import { nextChange, spendDomainMax } from "./logic";

describe("admin logic", () => {
  it("next change depends on the mode", () => {
    expect(nextChange("GREEN", 10)).toMatch(/70%/);
    expect(nextChange("AMBER", 10)).toMatch(/90%/);
    expect(nextChange("RED", 10)).toMatch(/until the cap resets/);
    expect(nextChange("RED", 10)).not.toMatch(/70%|90%/);
  });
  it("chart domain follows the data and the cap", () => {
    expect(spendDomainMax([2, 3, 4.4], 10)).toBe(10);
    expect(spendDomainMax([2, 12.2], 10)).toBe(13);
    expect(spendDomainMax([], 0)).toBe(1);
  });
});
