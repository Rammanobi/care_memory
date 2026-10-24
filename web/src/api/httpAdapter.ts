import { makeEmpty } from "../mocks/seed";
import { startLive } from "../realtime/sse";
import { ApiError, http } from "./http";
import { status } from "./status";
import {
  bulkFailures, decisionBody, mapDistrict, mapDocument, mapMedicine, type WireBulkItem, type WireDistrict, mapApproval, mapAudit, mapConsents, mapMessage, mapPatient, mapPortalMe, mapPortalMsg, mapPortalRequest, mapRecord, mapRequest, mapServerSettings, mapSupporterView, mapTemplate, mapUsage, toApiToken,
  type WireAudit, type WirePortalMe, type WirePortalMsg, type WirePortalRequest, type WireRecord, type WireSupporterView, type WireToday, type WireMessage, type WireRequest, type WireReviewDetail, type WireReviewItem, type WireTemplate, type WireUiPatient, type WireUsage,
} from "./mapping";
import { applyAction } from "./reducer";
import type { Action, CareApi, CareState, Evidence, LensSnap, Note } from "./types";

let cache: CareState = makeEmpty();
let role = "";

/** Optional slices: a 4xx (role not allowed, route missing) leaves the previous value. Network errors still throw. */
const opt = async <T,>(p: Promise<T>): Promise<T | undefined> => {
  try {
    return await p;
  } catch (e) {
    if (e instanceof ApiError) return undefined;
    throw e;
  }
};

async function loadDoctor(): Promise<CareState> {
  const now = Date.now();
  const queue = await http<{ items: WireReviewItem[] }>("/review/queue", { query: { limit: 100 } });
  const [pat, reqs, ev, notes, lens, msgs, clinics, usage, audit, tpl, tiles, sset, dist] = await Promise.all([
    opt(http<{ items: WireUiPatient[] }>("/patients", { query: { limit: 200 } })),
    opt(http<WireRequest[]>("/requests")),
    opt(http<Evidence[]>("/evidence")),
    opt(http<Note[]>("/notes")),
    opt(http<LensSnap[]>("/lens")),
    opt(http<WireMessage[]>("/messages")),
    opt(http<{ id: string; name: string; area: string }[]>("/clinics")),
    opt(http<WireUsage>("/admin/usage")),
    opt(http<{ items: WireAudit[] }>("/admin/audit", { query: { limit: 100 } })),
    opt(http<WireTemplate[]>("/templates", { query: { status: "approved" } })),
    opt(http<{ sim_day: number }>("/dashboard/tiles")),
    opt(http<Parameters<typeof mapServerSettings>[0]>("/admin/settings")),
    opt(http<WireDistrict>("/dashboard/district")),
  ]);
  const details = new Map<string, WireReviewDetail>();
  await Promise.all(
    queue.items.filter((i) => i.status === "pending").slice(0, 40).map(async (i) => {
      const d = await opt(http<WireReviewDetail>(`/review/${i.approval_id}`));
      if (d) details.set(i.approval_id, d);
    }),
  );
  return (cache = {
    ...cache,
    seededAt: now,
    simDay: tiles?.sim_day ?? cache.simDay,
    clinics: clinics ?? cache.clinics,
    patients: pat ? pat.items.map(mapPatient) : cache.patients,
    approvals: queue.items.map((i) => mapApproval(i, details.get(i.approval_id), now)),
    requests: reqs ? reqs.map((r) => mapRequest(r, now)) : cache.requests,
    evidence: ev ?? cache.evidence,
    notes: notes ?? cache.notes,
    lens: lens ?? cache.lens,
    messages: msgs ? msgs.map(mapMessage) : cache.messages,
    usage: usage ? mapUsage(usage) : cache.usage,
    audit: audit ? audit.items.map(mapAudit) : cache.audit,
    templates: tpl ? tpl.map(mapTemplate) : cache.templates,
    serverSettings: sset ? mapServerSettings(sset) : cache.serverSettings,
    district: dist ? mapDistrict(dist) : cache.district,
  });
}

async function loadPortal(): Promise<CareState> {
  const now = Date.now();
  if (role === "supporter") {
    const v = await opt(http<WireSupporterView>("/portal/supporter/checkin"));
    const prev = cache.portal;
    return (cache = {
      ...cache,
      seededAt: now,
      dose: v ? { today: v.today } : cache.dose,
      portal: v
        ? { consents: prev?.consents ?? mapConsents(undefined), streak: 0, nextVisit: null, history: "", markedBy: v.marked_by ?? null, record: null, inbox: v.messages.map(mapPortalMsg), supporter: mapSupporterView(v) }
        : prev,
    });
  }
  const [me, today, rec, reqs, inbox, cons, docs, meds] = await Promise.all([
    opt(http<WirePortalMe>("/portal/me")),
    opt(http<WireToday>("/portal/today")),
    opt(http<WireRecord>("/portal/record")),
    opt(http<WirePortalRequest[]>("/portal/requests")),
    opt(http<WirePortalMsg[]>("/portal/inbox")),
    opt(http<Record<string, boolean>>("/portal/consents")),
    opt(http<Parameters<typeof mapDocument>[0][]>("/portal/documents")),
    opt(http<Parameters<typeof mapMedicine>[0][]>("/portal/medicines")),
  ]);
  const prev = cache.portal;
  const mePart = me ? mapPortalMe(me) : prev?.me;
  const code = mePart?.code ?? "";
  return (cache = {
    ...cache,
    seededAt: now,
    dose: today ? { today: today.today, reason: today.reason ?? undefined } : cache.dose,
    requests: reqs ? reqs.map((r) => mapPortalRequest(r, code)) : cache.requests,
    portal: {
      me: mePart,
      consents: cons ? mapConsents(cons) : me ? mapConsents(me.consents) : prev?.consents ?? mapConsents(undefined),
      streak: today?.streak ?? prev?.streak ?? 0,
      nextVisit: today ? today.next_visit ?? null : prev?.nextVisit ?? null,
      history: today?.history ?? prev?.history ?? "",
      markedBy: today ? today.marked_by ?? null : prev?.markedBy ?? null,
      record: rec ? mapRecord(rec) : prev?.record ?? null,
      inbox: inbox ? inbox.map(mapPortalMsg) : prev?.inbox ?? [],
      documents: docs ? docs.map(mapDocument) : prev?.documents,
      medicines: meds ? meds.map(mapMedicine) : prev?.medicines,
    },
  });
}

async function load(): Promise<CareState> {
  if (!role) role = (await http<{ role: string }>("/auth/me")).role;
  return role === "patient" || role === "supporter" ? loadPortal() : loadDoctor();
}

async function dispatch(a: Action): Promise<CareState> {
  switch (a.t) {
    case "decideApprovals": {
      const body = decisionBody(a.decision, a.text);
      let ids = a.ids;
      if (a.decision === "approved" && !a.text && ids.length > 1) {
        try {
          const rows = await http<WireBulkItem[]>("/review/bulk-decision", { method: "POST", body: { approval_ids: ids, action: "approve", viewed_approval_ids: ids } });
          const bad = bulkFailures(rows);
          ids = []; // the bulk route answered for every item: refused ones are shown, never retried behind the doctor's back
          if (bad.length) {
            status.bulk({ total: rows.length, failures: bad.map((b) => ({ id: b.id, code: cache.approvals.find((x) => x.id === b.id)?.patientCode ?? "", message: b.message })) });
          }
        } catch {
          /* bulk route failed: fall back to single posts for every id */
        }
      }
      const res = await Promise.allSettled(ids.map((id) => http(`/review/${id}/decision`, { method: "POST", body })));
      const bad = res.find((r) => r.status === "rejected") as PromiseRejectedResult | undefined;
      if (bad) throw bad.reason;
      return load();
    }
    case "decideRequest":
      await http(`/requests/${a.id}/decision`, { method: "POST", body: decisionBody(a.decision, a.text) });
      return load();
    case "addNote":
      await http(`/patients/${toApiToken(a.note.code)}/notes`, { method: "POST", body: { text: a.note.text } });
      return load();
    case "simDay":
      await http("/admin/demo/sim-day", { method: "POST", body: { sim_day: a.value } });
      return load();
    case "usageMode":
      await http("/admin/demo/usage-mode", { method: "POST", body: { mode: a.mode } });
      return load();
    case "dose":
      if (a.value.today === "none") {
        if (role === "supporter") throw new ApiError(0, "A Supporter cannot undo a dose");
        await http("/portal/dose", { method: "DELETE" });
        return load();
      }
      if (role === "supporter") {
        await http("/portal/supporter/mark-taken", { method: "POST" });
      } else {
        await http("/portal/dose", { method: "POST", body: { status: a.value.today === "missed" ? "missed" : "taken", reason: a.value.reason } });
      }
      return load();
    case "newRequest":
      await http(role === "supporter" ? "/portal/supporter/ask" : "/portal/requests", { method: "POST", body: { text: a.req.text, kind: a.req.kind } });
      return load();
    case "markRead":
      await http(`/portal/messages/${a.id}/read`, { method: "POST" });
      return load();
    case "consent": {
      const cur = cache.portal?.consents ?? mapConsents(undefined);
      await http("/portal/consents", { method: "PUT", body: { ...cur, [a.key]: a.value } });
      return load();
    }
    case "reminder":
      await http("/portal/reminder-request", { method: "POST", body: { time: a.time } });
      return load();
    case "undo":
      throw new ApiError(0, "Undo is not available against the server yet");
    default:
      // No backend route (seen, channel, setting, empty): kept in memory until the next reload.
      cache = applyAction(cache, a);
      return cache;
  }
}

export const httpApi: CareApi = {
  load,
  dispatch,
  subscribe: (cb) => startLive(() => cb()),
  async reset() {
    cache = makeEmpty();
    return load();
  },
};

/** Called on login/logout so the next load re-reads the role. */
export function resetHttpSession() {
  role = "";
  cache = makeEmpty();
}
