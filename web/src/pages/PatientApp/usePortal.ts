// One view of the patient/Supporter data for every screen. Mock mode: the sample data plus localStorage extras (unchanged
// behaviour). Http mode: /portal/* data held in CareState.portal; only UI prefs stay in localStorage.
import { useCare } from "../../api/CareProvider";
import { USE_MOCK } from "../../api";
import { dayFromIso } from "../../api/mapping";
import { setExtras, useExtras, type Consents } from "../../api/patientExtras";
import { patientProfile as P } from "../../mocks/data";
import { HISTORY60, MESSAGES, MISS_REASON, PAST, PAST_REQUESTS, SUPPORTER, UPCOMING, idxDate, lastDays, type Appt, type Msg, type PastReq } from "./sampleData";

export interface PView {
  live: boolean;
  name: string; code: string; clinic: string; day: number;
  supporter: { name: string; relation: string } | null;
  history60: string; // oldest first; the last char is overridden by today's dose in the screens
  reasonAt: (i: number) => string | undefined;
  dateAt: (i: number) => Date;
  streak: number; // already includes today when taken
  messages: Msg[];
  isRead: (id: string) => boolean;
  markRead: (id: string) => void;
  upcoming: Appt[];
  past: Appt[];
  nextVisitText: string;
  pastRequests: PastReq[];
  consents: Consents;
  setConsent: (k: keyof Consents, v: boolean) => void;
  reminder: { current: string; pending: string | null; ask: (time: string) => void };
  supporterMarked: boolean;
  clearMark: () => void; // forget "marked by supporter" before the patient taps Took it
  markBySupporter: () => void; // mock only: remember that the Supporter tapped it
  canUndo: boolean;
  showMedicines: boolean;
  medicines: { id: string; label: string; when: string; note: string | null }[] | null; // null = mock mode (sample list)
  documents: { id: string; title: string; kind: string; date: string; summary: string }[] | null;
  /** Supporter screen */
  sup: { patientName: string; supporterName: string; relation: string; allowed: boolean; week: (today: "none" | "taken" | "missed") => string[]; messages: Msg[] };
}

const msgFromWire = (m: { id: string; title: string; text: string; at: string; forSupporter: boolean }): Msg => ({ id: m.id, daysAgo: 0, title: m.title, text: m.text, forSupporter: m.forSupporter, date: new Date(m.at) });

export function usePortal(): PView {
  const { state, dispatch } = useCare();
  const [ex] = useExtras();
  const today = state?.dose.today ?? "none";

  if (USE_MOCK) {
    const mine = (state?.requests ?? []).filter((r) => r.patientCode === P.code);
    const approved = [...ex.remReqs].reverse().find((rr) => mine.some((r) => r.id === rr.id && r.status === "approved"));
    const pending = ex.remReqs.find((rr) => mine.some((r) => r.id === rr.id && r.status === "waiting"));
    return {
      live: false, name: P.name, code: P.code, clinic: P.clinic, day: 60, supporter: SUPPORTER,
      history60: HISTORY60, reasonAt: (i) => MISS_REASON[i], dateAt: idxDate,
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
      sup: { patientName: P.name, supporterName: SUPPORTER.name, relation: SUPPORTER.relation, allowed: true, week: (t) => lastDays(7, t), messages: ex.empty ? [] : MESSAGES.filter((m) => m.forSupporter) },
    };
  }

  const p = state?.portal;
  const me = p?.me;
  const hist = p?.history ?? "";
  const inbox = (p?.inbox ?? []).map(msgFromWire);
  const readIds = new Set((p?.inbox ?? []).filter((m) => m.read).map((m) => m.id));
  const days = p?.record?.days;
  const sup = p?.supporter;
  return {
    live: true,
    name: me?.name ?? sup?.patientName ?? "", code: me?.code ?? sup?.patientCode ?? "", clinic: me?.clinic ?? "", day: me?.day ?? 0, supporter: me?.supporter ?? null,
    history60: hist,
    reasonAt: (i) => days?.[i]?.reason ?? undefined,
    dateAt: (i) => (days?.[i] ? dayFromIso(days[i].date) : idxDate(i)),
    streak: p?.streak ?? 0,
    messages: inbox,
    isRead: (id) => readIds.has(id),
    markRead: (id) => { if (!readIds.has(id)) dispatch({ t: "markRead", id }); },
    upcoming: p?.record?.upcoming ?? [], past: p?.record?.past ?? [], nextVisitText: p?.nextVisit ?? "",
    pastRequests: [],
    consents: p?.consents ?? { telegram: false, gmail: false, calendar: false },
    setConsent: (k, v) => dispatch({ t: "consent", key: k, value: v }),
    reminder: { current: me?.reminder ?? "", pending: me?.pendingReminder ?? null, ask: (time) => dispatch({ t: "reminder", time }) },
    supporterMarked: p?.markedBy === "supporter",
    clearMark: () => undefined,
    markBySupporter: () => undefined,
    canUndo: !sup && !!me,
    showMedicines: !sup && !!me,
    medicines: p?.medicines ?? [], documents: p?.documents ?? [],
    sup: {
      patientName: sup?.patientName ?? "", supporterName: sup?.supporterName ?? "", relation: sup?.relation ?? "", allowed: sup?.allowed ?? true,
      week: (t) => { const a = (sup?.week ?? "").split(""); if (a.length) a[a.length - 1] = t === "taken" ? "o" : t === "missed" ? "m" : "f"; return a; }, messages: inbox,
    },
  };
}
