// Mock mode only (VITE_USE_MOCK=true): the sample patient Ravi plus localStorage extras. Never imported by a live path
// except through usePortal, which calls it only when USE_MOCK is true.
import type { Action, CareState } from "../../api/types";
import { setExtras, type Extras } from "../../api/patientExtras";
import { patientProfile as P } from "../../mocks/data";
import { HISTORY60, MISS_REASON, lastDays, sampleFor } from "./sampleData";
import type { Lang } from "../../components/i18n";
import { EXTRA } from "../../components/i18nExtra";
import { excerpt } from "../../api/questions";
import { JUST_NOW, idxDate, type PView } from "./portalTypes";

export function buildMockView(state: CareState | null | undefined, ex: Extras, dispatch: (a: Action) => unknown, lang: Lang = "en"): PView {
  const S = sampleFor(lang);
  const li = lang === "te" ? 1 : 0;
  const today = state?.dose.today ?? "none";
  const mine = (state?.requests ?? []).filter((r) => r.patientCode === P.code);
  const approved = [...ex.remReqs].reverse().find((rr) => mine.some((r) => r.id === rr.id && r.status === "approved"));
  const pending = ex.remReqs.find((rr) => mine.some((r) => r.id === rr.id && r.status === "waiting"));
  // Answered requests appear in Messages as replies, threaded under the question they answer. No `origin` is needed: a
  // patient-app question carries none (and giving it one would turn it into a doctor-side question card). Old history is skipped.
  const answers = mine.filter((r) => r.status === "approved" && r.reply && !r.archived).map((r) => ({ id: `ans-${r.id}`, daysAgo: 0, title: EXTRA.replyTitle[li], text: r.reply ?? "", inReplyTo: { excerpt: excerpt(r.text) } }));
  const supOn = ex.shareSupporter;
  return {
    live: false, empty: ex.empty, name: S.patientName, code: P.code, clinic: S.clinic, day: 60, supporter: S.supporter,
    history60: HISTORY60, recordReady: true, reasonAt: (i) => MISS_REASON[i], dateAt: idxDate,
    streak: P.streak + (today === "taken" ? 1 : 0),
    messages: ex.empty ? [] : [...answers, ...S.messages],
    isRead: (id) => ex.read.includes(id),
    markRead: (id) => { if (!ex.read.includes(id)) setExtras({ read: [...ex.read, id] }); },
    upcoming: S.upcoming, past: S.past, nextVisitText: S.upcoming[0].when,
    pastRequests: ex.empty ? [] : S.pastRequests,
    consents: ex.consents,
    shareSupporter: { on: supOn, set: (on) => setExtras({ shareSupporter: on }) },
    setConsent: (k, v) => setExtras({ consents: { ...ex.consents, [k]: v } }),
    reminder: {
      current: approved?.time ?? ex.reminder,
      pending: pending?.time ?? null,
      ask: (time) => {
        const id = `rem-${Date.now()}`;
        dispatch({ t: "newRequest", req: { id, patientCode: P.code, kind: "Reminder time", text: `Please change my reminder to ${time}.`, when: JUST_NOW, draft: `Your reminder is now ${time}. Tell us if you want to change it again.`, status: "waiting" } });
        setExtras({ remReqs: [...ex.remReqs, { id, time }] });
      },
    },
    supporterMarked: ex.supporterMarked,
    clearMark: () => setExtras({ supporterMarked: false }),
    markBySupporter: () => setExtras({ supporterMarked: true }),
    canUndo: true,
    showMedicines: true,
    medicines: S.medicines, documents: ex.docs,
    clinicPhone: "", // no number in the demo: Help shows the "your clinic will add it" line only
    sup: { patientName: S.patientName, supporterName: S.supporter.name, relation: S.supporter.relation, allowed: supOn, week: (t) => (supOn ? lastDays(7, t) : []), messages: ex.empty || !supOn ? [] : S.messages.filter((m) => m.forSupporter) },
  };
}
