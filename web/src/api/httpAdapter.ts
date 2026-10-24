import { makeEmpty } from "../mocks/seed";
import { startLive } from "../realtime/sse";
import { ApiError, forgetSession, getMe, http } from "./http";
import { status } from "./status";
import {
  bulkFailures, decisionBody, mapDistrict, mapDocument, mapMedicine, type WireBulkItem, type WireDistrict, mapApproval, mapAudit, mapChannels, mapConsents, mapMessage, mapPatient, mapPortalMe, mapPortalMsg, mapPortalRequest, mapRecord, mapRequest, mapServerSettings, mapSupporterView, mapTemplate, mapUsage, toApiToken,
  type WireAudit, type WirePortalMe, type WirePortalMsg, type WirePortalRequest, type WireRecord, type WireSupporterView, type WireToday, type WireMessage, type WireRequest, type WireReviewDetail, type WireReviewItem, type WireTemplate, type WireUiPatient, type WireUsage,
} from "./mapping";
import { applyAction } from "./reducer";
import type { Action, CareApi, CareState, Evidence, LensSnap, Note } from "./types";

/** Live mode starts from an honestly empty state: no sample patients, usage, clinics or channels. */
function makeLiveEmpty(): CareState {
  const e = makeEmpty();
  return {
    ...e, clinics: [], templates: [], channels: [], simDay: 0, loadErrors: [],
    usage: { mode: "GREEN", todaySpend: 0, todayCap: 0, budgetUsed: 0, budget: 0, days: [], tasks: [], retries: 0, breaker: 0, billing: 0, providerPct: 0 },
  };
}

let cache: CareState = makeLiveEmpty();
let role = "";
const details = new Map<string, WireReviewDetail>(); // approval id -> detail, fetched at most once
const detailInflight = new Map<string, Promise<void>>();
const queueItems = new Map<string, WireReviewItem>();
let loading: Promise<CareState> | null = null;

/**
 * Optional slices: a 4xx (role not allowed, route missing) keeps the previous (real) value and is reported as
 * "could not load <name>" instead of silently showing sample data. 401/403 (role not allowed): console only.
 * Network errors still throw.
 */
const failed = new Set<string>();
const opt = async <T,>(name: string, p: Promise<T>): Promise<T | undefined> => {
  try {
    return await p;
  } catch (e) {
    if (e instanceof ApiError) {
      console.warn(`[caremem] could not load ${name}: ${e.httpStatus} ${e.message}`);
      if (e.httpStatus !== 403 && e.httpStatus !== 401) failed.add(name);
      return undefined;
    }
    throw e;
  }
};

const dedupeQueue = (items: WireReviewItem[]) => [...new Map(items.map((i) => [i.approval_id, i])).values()];
const mapQueue = (items: WireReviewItem[], now: number) => dedupeQueue(items).map((i) => mapApproval(i, details.get(i.approval_id), now));

/** Fetch one approval's draft text (when a card is opened, and for Red items on load). Cached, one request per id. */
export function loadApprovalDetail(id: string): Promise<CareState> {
  if (details.has(id)) return Promise.resolve(cache);
  let p = detailInflight.get(id);
  if (!p) {
    p = http<WireReviewDetail>(`/review/${id}`)
      .then((d) => {
        details.set(id, d);
        const it = queueItems.get(id);
        if (it) cache = { ...cache, approvals: cache.approvals.map((a) => (a.id === id ? mapApproval(it, d, Date.now()) : a)) };
      })
      .catch((e) => {
        console.warn(`[caremem] could not load draft ${id}: ${e instanceof Error ? e.message : e}`);
      })
      .finally(() => detailInflight.delete(id));
    detailInflight.set(id, p);
  }
  return p.then(() => cache);
}

async function loadDoctor(): Promise<CareState> {
  const now = Date.now();
  failed.clear();
  const queue = await http<{ items: WireReviewItem[] }>("/review/queue", { query: { limit: 100 } });
  queue.items.forEach((i) => queueItems.set(i.approval_id, i));
  const [pat, reqs, ev, notes, lens, msgs, clinics, usage, audit, tpl, tiles, sset, dist] = await Promise.all([
    opt("patients", http<{ items: WireUiPatient[] }>("/patients", { query: { limit: 200 } })),
    opt("requests", http<WireRequest[]>("/requests")),
    opt("evidence", http<Evidence[]>("/evidence")),
    opt("notes", http<Note[]>("/notes")),
    opt("lens", http<LensSnap[]>("/lens")),
    opt("messages", http<WireMessage[]>("/messages")),
    opt("clinics", http<{ id: string; name: string; area: string }[]>("/clinics")),
    opt("usage", http<WireUsage>("/admin/usage")),
    opt("audit log", http<{ items: WireAudit[] }>("/admin/audit", { query: { limit: 100 } })),
    opt("templates", http<WireTemplate[]>("/templates", { query: { status: "approved" } })),
    opt("dashboard", http<{ sim_day: number }>("/dashboard/tiles")),
    opt("settings", http<Parameters<typeof mapServerSettings>[0]>("/admin/settings")),
    opt("district", http<WireDistrict>("/dashboard/district")),
  ]);
  // Drafts: only pending Red items are fetched up front (once each, cached). Other cards load their draft when opened.
  await Promise.all(dedupeQueue(queue.items).filter((i) => i.status === "pending" && i.tier === "red" && !details.has(i.approval_id)).slice(0, 10).map((i) => loadApprovalDetail(i.approval_id)));
  const sv = sset ? mapServerSettings(sset) : cache.serverSettings;
  return (cache = {
    ...cache,
    seededAt: now,
    simDay: tiles?.sim_day ?? cache.simDay,
    clinics: clinics ?? cache.clinics,
    patients: pat ? pat.items.map(mapPatient) : cache.patients,
    approvals: mapQueue(queue.items, now),
    requests: reqs ? reqs.map((r) => mapRequest(r, now)) : cache.requests,
    evidence: ev ?? cache.evidence,
    notes: notes ?? cache.notes,
    lens: lens ?? cache.lens,
    messages: msgs ? msgs.map(mapMessage) : cache.messages,
    usage: usage ? mapUsage(usage) : cache.usage,
    audit: audit ? audit.items.map(mapAudit) : cache.audit,
    templates: tpl ? tpl.map(mapTemplate) : cache.templates,
    serverSettings: sv,
    channels: sv ? mapChannels(sv.channels) : cache.channels,
    district: dist ? mapDistrict(dist) : cache.district,
    loadErrors: [...failed],
  });
}

/** After a decision: refetch only the slices it changed (queue, plus requests and messages), not the whole app. */
async function refreshAfterDecision(withRequests: boolean): Promise<CareState> {
  const now = Date.now();
  const [queue, reqs, msgs] = await Promise.all([
    http<{ items: WireReviewItem[] }>("/review/queue", { query: { limit: 100 } }),
    withRequests ? opt("requests", http<WireRequest[]>("/requests")) : Promise.resolve(undefined),
    opt("messages", http<WireMessage[]>("/messages")),
  ]);
  queue.items.forEach((i) => queueItems.set(i.approval_id, i));
  return (cache = {
    ...cache,
    seededAt: now,
    approvals: mapQueue(queue.items, now),
    requests: reqs ? reqs.map((r) => mapRequest(r, now)) : cache.requests,
    messages: msgs ? msgs.map(mapMessage) : cache.messages,
  });
}

async function loadPortal(): Promise<CareState> {
  const now = Date.now();
  if (role === "supporter") {
    const v = await opt("check-in", http<WireSupporterView>("/portal/supporter/checkin"));
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
    opt("profile", http<WirePortalMe>("/portal/me")),
    opt("today", http<WireToday>("/portal/today")),
    opt("record", http<WireRecord>("/portal/record")),
    opt("requests", http<WirePortalRequest[]>("/portal/requests")),
    opt("inbox", http<WirePortalMsg[]>("/portal/inbox")),
    opt("consents", http<Record<string, boolean>>("/portal/consents")),
    opt("documents", http<Parameters<typeof mapDocument>[0][]>("/portal/documents")),
    opt("medicines", http<Parameters<typeof mapMedicine>[0][]>("/portal/medicines")),
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

/** Concurrent load() calls (mount, session event, poll, SSE) share one round of requests. */
function load(): Promise<CareState> {
  if (!loading) {
    loading = (async () => {
      if (!role) role = (await getMe()).role;
      return role === "patient" || role === "supporter" ? loadPortal() : loadDoctor();
    })().finally(() => {
      loading = null;
    });
  }
  return loading;
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
      return refreshAfterDecision(false);
    }
    case "decideRequest":
      await http(`/requests/${a.id}/decision`, { method: "POST", body: decisionBody(a.decision, a.text) });
      return refreshAfterDecision(true);
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
  loadDetail: loadApprovalDetail,
  async reset() {
    cache = makeLiveEmpty();
    details.clear();
    return load();
  },
};

/** Called on login/logout so the next load re-reads the role. */
export function resetHttpSession() {
  role = "";
  cache = makeLiveEmpty();
  details.clear();
  queueItems.clear();
  loading = null;
  forgetSession(null);
}
