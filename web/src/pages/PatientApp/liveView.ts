// Live mode: the patient/Supporter view built ONLY from /portal/* data (CareState.portal). No sample data,
// no invented values: whatever the server did not send is empty, null or hidden by the screens.
import { dayFromIso } from "../../api/mapping";
import type { Action, PortalMsg, PortalSlice } from "../../api/types";
import { idxDate, type Msg, type PView } from "./portalTypes";

export const msgFromWire = (m: PortalMsg): Msg => ({ id: m.id, daysAgo: 0, title: m.title, text: m.text, forSupporter: m.forSupporter, date: new Date(m.at), ...(m.inReplyTo ? { inReplyTo: { excerpt: m.inReplyTo.excerpt } } : {}) });

export function buildLiveView(p: PortalSlice | undefined, dispatch: (a: Action) => unknown): PView {
  const me = p?.me;
  const sup = p?.supporter;
  const inbox = (p?.inbox ?? []).map(msgFromWire);
  const readIds = new Set((p?.inbox ?? []).filter((m) => m.read).map((m) => m.id));
  const days = p?.record?.days;
  const upcoming = p?.record?.upcoming ?? [];
  // The server's next-visit text, else the first upcoming visit it listed, else nothing.
  const firstVisit = upcoming.find((a) => a.kind === "visit");
  const nextVisitText = p?.nextVisit || (firstVisit ? firstVisit.when : null);
  return {
    live: true, empty: false,
    name: me?.name ?? sup?.patientName ?? "", code: me?.code ?? sup?.patientCode ?? "", clinic: me?.clinic ?? "", day: me?.day ?? 0, supporter: me?.supporter ?? null,
    history60: p?.history ?? "",
    recordReady: !!days && days.length > 0,
    reasonAt: (i) => days?.[i]?.reason ?? undefined,
    dateAt: (i) => (days?.[i] ? dayFromIso(days[i].date) : idxDate(i)),
    streak: p?.streak ?? 0,
    messages: inbox,
    isRead: (id) => readIds.has(id),
    markRead: (id) => { if (!readIds.has(id)) dispatch({ t: "markRead", id }); },
    upcoming, past: p?.record?.past ?? [], nextVisitText,
    pastRequests: [],
    consents: p?.consents ?? { telegram: false, gmail: false, calendar: false },
    shareSupporter: null,
    setConsent: (k, v) => dispatch({ t: "consent", key: k, value: v }),
    reminder: { current: me?.reminder || null, pending: me?.pendingReminder ?? null, ask: (time) => dispatch({ t: "reminder", time }) },
    supporterMarked: p?.markedBy === "supporter",
    clearMark: () => undefined,
    markBySupporter: () => undefined,
    canUndo: !sup && !!me,
    showMedicines: !sup && !!me,
    medicines: p?.medicines ?? [], documents: p?.documents ?? [],
    clinicPhone: null,
    sup: {
      patientName: sup?.patientName ?? "", supporterName: sup?.supporterName ?? "", relation: sup?.relation || null, allowed: sup?.allowed ?? false,
      week: (t) => { const a = (sup?.week ?? "").split(""); if (a.length) a[a.length - 1] = t === "taken" ? "o" : t === "missed" ? "m" : "f"; return a; },
      messages: inbox,
    },
  };
}
