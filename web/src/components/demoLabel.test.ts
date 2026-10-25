import { describe, expect, it } from "vitest";
import { hideDemoLabel } from "./ui";

describe("hideDemoLabel", () => {
  it("hides in cloud builds", () => {
    expect(hideDemoLabel({ VITE_AUTH_MODE: "firebase" }, "app.web.app")).toBe(true);
    expect(hideDemoLabel({ VITE_HIDE_DEMO_LABEL: "1" }, "app.web.app")).toBe(true);
  });
  it("keeps it by default and on localhost", () => {
    expect(hideDemoLabel({}, "app.web.app")).toBe(false);
    expect(hideDemoLabel({ VITE_AUTH_MODE: "firebase" }, "localhost")).toBe(false);
    expect(hideDemoLabel({ VITE_HIDE_DEMO_LABEL: "1" }, "127.0.0.1")).toBe(false);
  });
});
