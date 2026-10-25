import { describe, expect, it } from "vitest";
import { evidenceKind, keysFor, shortcutAllowed } from "./doctorKit";
import { bannedTerms } from "../api/questions";

// The server's list, copied from cm/api/suppress.py BANNED_TERMS and cm/core/banned_lexicon.py. Keep in step with both.
const SERVER_TERMS = [
  "tb", "tuberculosis", "mdr", "xdr", "dots", "isoniazid", "rifampicin", "rifampin", "ethambutol", "pyrazinamide", "streptomycin", "bedaquiline", "linezolid",
  "delamanid", "pretomanid", "rifapentine", "moxifloxacin", "levofloxacin", "cycloserine", "clofazimine", "hrze", "rhze", "ethionamide", "akt", "fdc",
];

describe("client banned list matches the server", () => {
  it.each(SERVER_TERMS)("flags %s", (t) => {
    expect(bannedTerms(`Please do not stop ${t} now`)).toEqual([t]);
    expect(bannedTerms(t.toUpperCase())).toEqual([t]);
  });
  it("flags T.B. and leaves ordinary words alone", () => {
    expect(bannedTerms("the T.B. clinic")).toEqual(["tb"]);
    expect(bannedTerms("Come on Friday, bring the strip and a tablet. Don't be late.")).toEqual([]);
  });
});

describe("keyboard shortcut guard", () => {
  const card = (cls: string[]) => ({ closest: (sel: string) => (cls.includes(sel.replace(".", "")) ? {} : null) });
  it("ignores A and D on question and document cards", () => {
    expect(shortcutAllowed("a", card(["qcard"]))).toBe(false);
    expect(shortcutAllowed("d", card(["qcard", "dcard"]))).toBe(false);
  });
  it("keeps E on question cards and A/D on approval drafts", () => {
    expect(shortcutAllowed("e", card(["qcard"]))).toBe(true);
    expect(shortcutAllowed("a", card([]))).toBe(true);
    expect(shortcutAllowed("d", card([]))).toBe(true);
  });
  it("shows only the shortcuts relevant to the page", () => {
    const keys = (p: string) => keysFor(p).map((k) => k[0]);
    expect(keys("/doctor/ask")).toEqual(["?", "Esc"]);
    expect(keys("/doctor/approvals")).toContain("A");
    expect(keys("/doctor/today")).not.toContain("A");
    expect(keys("/doctor/requests")).toContain("Ctrl+Enter");
  });
});

describe("evidence drawer kind label", () => {
  it("uses the snippet kind, not the id letter", () => {
    expect(evidenceKind("D-1a2b3c4d", { kind: "event" })).toBe("Event");
    expect(evidenceKind("D-1a2b3c4d", { kind: "daily" })).toBe("Daily summary");
    expect(evidenceKind("D-1a2b3c4d", { kind: "weekly" })).toBe("Weekly summary");
    expect(evidenceKind("D-1a2b3c4d", { kind: "document" })).toBe("Document");
  });
  it("falls back to the id letter without a snippet", () => {
    expect(evidenceKind("E-0412")).toBe("Event");
    expect(evidenceKind("X-1")).toBe("Source");
  });
});
