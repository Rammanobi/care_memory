import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backoffMs, parseLive, startLive } from "./sse";
import { status } from "../api/status";

class FakeES {
  static all: FakeES[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((m: unknown) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  listeners: Record<string, (m: unknown) => void> = {};
  constructor(public url: string) { FakeES.all.push(this); }
  addEventListener(t: string, f: (m: unknown) => void) { this.listeners[t] = f; }
  close() { this.closed = true; }
}

describe("parseLive", () => {
  it("parses event data and falls back to the event name as topic", () => {
    expect(parseLive('{"type":"approval_decided","ref":"r1","patient_id":"p"}', "review")).toMatchObject({ type: "approval_decided", topic: "review", ref: "r1" });
    expect(parseLive("not json")).toBeNull();
    expect(parseLive("")).toBeNull();
  });
  it("backs off exponentially up to 30 s", () => {
    expect([0, 1, 2, 3, 9].map(backoffMs)).toEqual([1000, 2000, 4000, 8000, 30000]);
  });
});

describe("startLive", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeES.all = [];
    vi.stubGlobal("EventSource", FakeES);
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("refetches on review and channels events and marks live", () => {
    const cb = vi.fn();
    const stop = startLive(cb, () => true);
    const es = FakeES.all[0];
    expect(es.url).toContain("/stream?topics=review,channels");
    es.onopen?.();
    expect(status.get().live).toBe(true);
    es.listeners.review({ data: '{"type":"approval_decided","topic":"review","ref":"x","patient_id":null}' });
    es.listeners.channels({ data: '{"type":"message_sent"}' });
    vi.advanceTimersByTime(200);
    expect(cb).toHaveBeenCalledTimes(1); // two events in one burst are debounced to one refetch
    expect(cb.mock.calls[0][0]).toMatchObject({ topic: "channels" });
    stop();
    expect(es.closed).toBe(true);
    expect(status.get().live).toBe(false);
  });

  it("does nothing while logged out: no /stream, no polling", () => {
    const cb = vi.fn();
    const stop = startLive(cb, () => false);
    vi.advanceTimersByTime(60000);
    expect(FakeES.all.length).toBe(0);
    expect(cb).not.toHaveBeenCalled();
    stop();
  });

  it("polls every 5 s without SSE and every 30 s with it", () => {
    const cb = vi.fn();
    const stop = startLive(cb, () => true);
    vi.advanceTimersByTime(5100);
    expect(cb).toHaveBeenCalledTimes(1);
    FakeES.all[0].onopen?.();
    cb.mockClear();
    vi.advanceTimersByTime(29000);
    expect(cb).not.toHaveBeenCalled();
    vi.advanceTimersByTime(2000);
    expect(cb).toHaveBeenCalledTimes(1);
    stop();
  });

  it("reconnects with backoff after an error and resets once open", () => {
    const stop = startLive(vi.fn(), () => true);
    FakeES.all[0].onerror?.();
    expect(status.get().live).toBe(false);
    expect(FakeES.all).toHaveLength(1);
    vi.advanceTimersByTime(1000);
    expect(FakeES.all).toHaveLength(2);
    FakeES.all[1].onerror?.();
    vi.advanceTimersByTime(1500);
    expect(FakeES.all).toHaveLength(2); // second wait is 2 s
    vi.advanceTimersByTime(600);
    expect(FakeES.all).toHaveLength(3);
    stop();
  });
});

describe("cloud (firebase) mode", () => {
  beforeEach(() => { vi.useFakeTimers(); FakeES.all = []; vi.stubGlobal("EventSource", FakeES); vi.stubEnv("VITE_AUTH_MODE", "firebase"); });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

  it("never opens /stream and polls every 5 s", () => {
    const cb = vi.fn();
    const stop = startLive(cb, () => true);
    expect(FakeES.all.length).toBe(0);
    vi.advanceTimersByTime(10100);
    expect(cb).toHaveBeenCalledTimes(2);
    stop();
  });

  it("pauses while the tab is hidden", () => {
    const cb = vi.fn();
    vi.stubGlobal("document", { visibilityState: "hidden", addEventListener: vi.fn(), removeEventListener: vi.fn() });
    const stop = startLive(cb, () => true);
    vi.advanceTimersByTime(20000);
    expect(cb).not.toHaveBeenCalled();
    stop();
  });
});
