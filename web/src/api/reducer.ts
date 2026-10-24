import { makeEmpty, usageFor } from "../mocks/seed";
import type { Action, CareState } from "./types";

const clock = () => new Date().toTimeString().slice(0, 5);
const ACTOR = "Dr. A. Rao";

/** Pure-ish state transition (stamps the time of a decision), shared by the optimistic UI update and the mock adapter. */
export function applyAction(s: CareState, a: Action): CareState {
  switch (a.t) {
    case "dose":
      return { ...s, dose: a.value };
    case "newRequest":
      return s.requests.some((r) => r.id === a.req.id) ? s : { ...s, requests: [{ createdAt: Date.now(), ...a.req }, ...s.requests] };
    case "decideRequest":
      return decide(s, "requests", [a.id], a.decision, a.text);
    case "decideApprovals":
      return decide(s, "approvals", a.ids, a.decision, a.text);
    case "undo": {
      const ids = a.ids;
      const back = <T extends { id: string; status: string; reply?: string }>(l: T[]): T[] => l.map((x) => (ids.includes(x.id) && x.status !== "waiting" ? { ...x, status: "waiting", reply: undefined } : x));
      return {
        ...s,
        requests: back(s.requests),
        approvals: back(s.approvals),
        messages: s.messages.filter((m) => !ids.includes(m.srcId)),
        audit: [...ids.filter((id) => s.audit.some((x) => x.srcId === id)).map((id) => ({ id: `au-u-${id}-${Date.now()}`, code: s.audit.find((x) => x.srcId === id)!.code, at: `today ${clock()}`, actor: ACTOR, action: "Undid the decision (within 10 seconds)", srcId: id })), ...s.audit],
      };
    }
    case "seen":
      return { ...s, messages: s.messages.map((m) => (m.srcId === a.srcId && m.status === "sent" ? { ...m, status: "seen" } : m)) };
    case "addNote":
      return { ...s, notes: [a.note, ...s.notes] };
    case "usageMode":
      return { ...s, usage: usageFor(a.mode) };
    case "simDay":
      return { ...s, simDay: a.value };
    case "channel":
      return { ...s, channels: s.channels.map((c) => (c.name === a.name ? { ...c, connected: a.connected, detail: a.connected ? "Connected (mock)" : "Not connected (mock)" } : c)) };
    case "setting":
      return { ...s, settings: { ...s.settings, [a.key]: a.value } };
    case "empty":
      return makeEmpty();
    // Portal actions only exist in http mode (state.portal is set); in mock mode they are no-ops.
    case "markRead":
      return s.portal ? { ...s, portal: { ...s.portal, inbox: s.portal.inbox.map((m) => (m.id === a.id ? { ...m, read: true } : m)) } } : s;
    case "consent":
      return s.portal ? { ...s, portal: { ...s.portal, consents: { ...s.portal.consents, [a.key]: a.value } } } : s;
    case "reminder":
      return s.portal?.me ? { ...s, portal: { ...s.portal, me: { ...s.portal.me, pendingReminder: a.time } } } : s;
  }
}

function decide(s: CareState, key: "requests" | "approvals", ids: string[], decision: "approved" | "declined", text?: string): CareState {
  const list = s[key] as { id: string; patientCode: string; status: string; draft: string; title?: string; kind?: string }[];
  const hit = list.filter((x) => ids.includes(x.id) && x.status === "waiting");
  if (hit.length === 0) return s;
  const at = `today ${clock()}`;
  const next = list.map((x) => {
    if (!hit.includes(x)) return x;
    const body = text ?? x.draft;
    return { ...x, status: decision, draft: body, reply: decision === "approved" ? body : undefined };
  });
  const messages = [...s.messages];
  const audit = [...s.audit];
  hit.forEach((x) => {
    const body = text ?? x.draft;
    const edited = body !== x.draft;
    const version = edited ? 2 : 1;
    if (decision === "approved") {
      messages.unshift({ id: `m-${x.id}-${Date.now()}`, srcId: x.id, code: x.patientCode, at, channel: key === "requests" ? "Patient app" : "Telegram", text: body, approvedBy: ACTOR, version, status: "sent" });
    }
    audit.unshift({ id: `au-${x.id}-${Date.now()}`, code: x.patientCode, at, actor: ACTOR, action: decision === "declined" ? "Declined draft" : edited ? "Edited then approved" : "Approved draft", srcId: x.id, version, note: x.title ?? x.kind });
  });
  return { ...s, [key]: next, messages, audit } as CareState;
}
