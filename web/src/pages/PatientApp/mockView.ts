// Mock mode only (VITE_USE_MOCK=true): the sample patient Ravi plus localStorage extras. Never imported by a live path
// except through usePortal, which calls it only when USE_MOCK is true.
import type { Action, CareState } from "../../api/types";
import { setExtras, type Extras } from "../../api/patientExtras";
import { patientProfile as P } from "../../mocks/data";
import { HISTORY60, MESSAGES, MISS_REASON, PAST, PAST_REQUESTS, SUPPORTER, UPCOMING, lastDays } from "./sampleData";
import { idxDate, type PView } from "./portalTypes";

export function buildMockView(state: CareState | null | undefined, ex: Extras, dispatch: (a: Action) => unknown): PView {
  const today = state?.dose.today ?? "none";
  const mine = (state?.requests ?? []).filter((r) => r.patientCode === P.code);
  const approved = [...ex.remReqs].reverse().find((rr) => mine.some((r) => r.id === rr.id && r.status === "approved"));
  const pending = ex.remReqs.find((rr) => mine.some((r) => r.id === rr.id && r.status === "waiting"));
  return {
    live: false, empty: ex.empty, name: P.name, code: P.code, clinic: P.clinic, day: 60, supporter: SUPPORTER,
    history60: HISTORY60, recordReady: true, reasonAt: (i) => MISS_REASON[i], dateAt: idxDate,
    streak: P.streak + (today === "taken" ? 1 : 0),
    messages: ex.empty ? [] : MESSAGES,
    isRead: (id) => ex.read.includes(id),
    markRead: (id) => { if (!ex.read.includes(id)) setExtras({ read: [...ex.read, id] }); },
    upcoming: UPCOMING, past: PAST, nextVisitText: UPCOMING[0].when,
    pastRequests: ex.empty ? [] : PAST_REQUESTS,
    consents: ex.consents,
    setConsent: (k, v) => setExtras({ consents: { ...ex.consents, [k]: v } }),
    reminder: {
      current: approved?.time ?? ex.reminder,
      pending: pending?.time ?? null,
      ask: (time) => {
        const id = `rem-${Date.now()}`;
        dispatch({ t: "newRequest", req: { id, patientCode: P.code, kind: "Reminder time", text: `Please change my reminder to ${time}.`, when: "today, just now", draft: `Your reminder is now ${time}. Tell us if you want to change it again.`, status: "waiting" } });
        setExtras({ remReqs: [...ex.remReqs, { id, time }] });
      },
    },
    supporterMarked: ex.supporterMarked,
    clearMark: () => setExtras({ supporterMarked: false }),
    markBySupporter: () => setExtras({ supporterMarked: true }),
    canUndo: true,
    showMedicines: true,
    medicines: null, documents: null,
    clinicPhone: "000-000-0000",
    sup: { patientName: P.name, supporterName: SUPPORTER.name, relation: SUPPORTER.relation, allowed: true, week: (t) => lastDays(7, t), messages: ex.empty ? [] : MESSAGES.filter((m) => m.forSupporter) },
  };
}
