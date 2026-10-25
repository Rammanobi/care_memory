// Fictional sample data for patient Ravi (PT-0142, day 60). Consistent with the shared mock store.
// No medical content. Every sample text has English and Telugu (sampleFor). Telugu wording NEEDS native-speaker review.
import { patientProfile } from "../../mocks/data";
import type { Appt, Msg, PastReq } from "./portalTypes";
import type { Lang } from "../../components/i18n";

export { TOTAL_DAYS, dayDate, idxDate } from "./portalTypes";
export type { Appt, Msg, PastReq, ReqState } from "./portalTypes";
// 60 days of history, oldest first. 'o' taken, 'm' missed. Last 30 come from the shared profile.
const FIRST30 = "oooomoooooooooooomoooooooooomo".slice(0, 30);
export const HISTORY60 = FIRST30 + patientProfile.history;
export const MISS_REASON: Record<number, string> = { 4: "Forgot to take it", 17: "Travelling", 28: "Felt unwell", 41: "Ran out of tablets" };


export const MESSAGES: Msg[] = [
  { id: "m1", daysAgo: 0, title: "Bring your medicine strip", text: "Please bring your medicine strip to the visit on Wednesday at 6 pm.", forSupporter: true },
  { id: "m2", daysAgo: 1, title: "Lab slot held for you", text: "Your lab slot is held for Friday at 10 am. Please come to the clinic reception first." },
  { id: "m3", daysAgo: 3, title: "Well done this week", text: "Thank you. You did not miss a day this week. Keep going.", forSupporter: true },
  { id: "m4", daysAgo: 8, title: "Reminder time saved", text: "Your reminder time is saved. Tell us if you want to change it again." },
  { id: "m5", daysAgo: 15, title: "Clinic closed on Sunday", text: "The clinic is closed this Sunday. It opens again on Monday at 9 am." },
  { id: "m6", daysAgo: 30, title: "Welcome to CareMemory", text: "Welcome. Your care team will send you approved messages here." },
];

export const UPCOMING: Appt[] = [
  { id: "u1", kind: "visit", title: "Clinic visit", when: "Wed 6 pm", place: "Anantapur Clinic" },
  { id: "u2", kind: "lab", title: "Lab test", when: "Fri 10 am", place: "Anantapur Clinic lab" },
  { id: "u3", kind: "visit", title: "Clinic visit", when: "Next month", place: "Anantapur Clinic" },
];
export const PAST: Appt[] = [
  { id: "p1", kind: "visit", title: "Clinic visit", when: "2 weeks ago", place: "Anantapur Clinic", daysAgo: 14, note: "Done" },
  { id: "p2", kind: "lab", title: "Lab test", when: "4 weeks ago", place: "Anantapur Clinic lab", daysAgo: 28, note: "Your doctor has the result" },
  { id: "p3", kind: "visit", title: "Clinic visit", when: "6 weeks ago", place: "Anantapur Clinic", daysAgo: 42, note: "Done" },
  { id: "p4", kind: "lab", title: "Lab test", when: "8 weeks ago", place: "Anantapur Clinic lab", daysAgo: 56, note: "Your doctor has the result" },
];

export const PAST_REQUESTS: PastReq[] = [
  { id: "sx-1", text: "Can you remind me at 7 pm?", when: "last week", status: "approved", reply: "Reminder now 7 pm" },
  { id: "sx-2", text: "I need help getting my refill.", when: "3 weeks ago", status: "approved", reply: "A nurse called you and your refill is ready." },
  { id: "sx-3", text: "Can I change my visit to Monday?", when: "4 weeks ago", status: "declined" },
  { id: "sx-4", text: "Where do I go for the lab test?", when: "6 weeks ago", status: "approved", reply: "Please go to the clinic reception first." },
  { id: "sx-5", text: "Can my sister come with me?", when: "7 weeks ago", status: "declined" },
];

export const SUPPORTER = { name: "Lakshmi", relation: "sister" };
export const lastDays = (n: number, today: "none" | "taken" | "missed") =>
  HISTORY60.slice(-n).split("").map((c, i, a) => (i === a.length - 1 ? (today === "taken" ? "o" : today === "missed" ? "m" : "f") : c));

export const MEDICINES = [
  { id: "med1", label: "Morning tablets", when: "Every day, with water", note: null },
  { id: "med2", label: "Vitamin tablet", when: "Every day, evening", note: null },
];

// ---- Telugu sample set (needs native-speaker review) ----
const TE_MSG: Record<string, { title: string; text: string }> = {
  m1: { title: "మీ మందు స్ట్రిప్ తీసుకురండి", text: "బుధవారం సాయంత్రం 6 గంటలకు సందర్శనకు మీ మందు స్ట్రిప్ తీసుకురండి." },
  m2: { title: "మీ కోసం ల్యాబ్ స్లాట్ ఉంచాము", text: "శుక్రవారం ఉదయం 10 గంటలకు మీ ల్యాబ్ స్లాట్ ఉంచాము. దయచేసి ముందుగా క్లినిక్ రిసెప్షన్‌కు రండి." },
  m3: { title: "ఈ వారం బాగా చేశారు", text: "ధన్యవాదాలు. ఈ వారం ఒక్క రోజు కూడా మిస్ కాలేదు. ఇలాగే కొనసాగించండి." },
  m4: { title: "గుర్తుచేసే సమయం సేవ్ అయింది", text: "మీ గుర్తుచేసే సమయం సేవ్ అయింది. మళ్లీ మార్చాలంటే మాకు చెప్పండి." },
  m5: { title: "ఆదివారం క్లినిక్ మూసివేత", text: "ఈ ఆదివారం క్లినిక్ మూసి ఉంటుంది. సోమవారం ఉదయం 9 గంటలకు మళ్లీ తెరుస్తారు." },
  m6: { title: "కేర్‌మెమరీకి స్వాగతం", text: "స్వాగతం. మీ సంరక్షణ బృందం ఆమోదించిన సందేశాలను ఇక్కడ పంపుతుంది." },
};
const TE_CLINIC = "అనంతపురం క్లినిక్";
const TE_APPT: Record<string, { when: string; place: string; note?: string }> = {
  u1: { when: "బుధవారం సాయంత్రం 6", place: TE_CLINIC },
  u2: { when: "శుక్రవారం ఉదయం 10", place: `${TE_CLINIC} ల్యాబ్` },
  u3: { when: "వచ్చే నెల", place: TE_CLINIC },
  p1: { when: "2 వారాల క్రితం", place: TE_CLINIC, note: "అయింది" },
  p2: { when: "4 వారాల క్రితం", place: `${TE_CLINIC} ల్యాబ్`, note: "మీ డాక్టర్ వద్ద ఫలితం ఉంది" },
  p3: { when: "6 వారాల క్రితం", place: TE_CLINIC, note: "అయింది" },
  p4: { when: "8 వారాల క్రితం", place: `${TE_CLINIC} ల్యాబ్`, note: "మీ డాక్టర్ వద్ద ఫలితం ఉంది" },
};
const TE_REQ: Record<string, { text: string; when: string; reply?: string }> = {
  "sx-1": { text: "రాత్రి 7 గంటలకు గుర్తు చేయగలరా?", when: "గత వారం", reply: "ఇప్పుడు గుర్తుచేత రాత్రి 7 గంటలకు" },
  "sx-2": { text: "నా రీఫిల్ పొందడానికి సహాయం కావాలి.", when: "3 వారాల క్రితం", reply: "ఒక నర్సు మీకు కాల్ చేశారు, మీ రీఫిల్ సిద్ధంగా ఉంది." },
  "sx-3": { text: "నా సందర్శనను సోమవారానికి మార్చవచ్చా?", when: "4 వారాల క్రితం" },
  "sx-4": { text: "ల్యాబ్ పరీక్షకు ఎక్కడికి వెళ్లాలి?", when: "6 వారాల క్రితం", reply: "దయచేసి ముందుగా క్లినిక్ రిసెప్షన్‌కు వెళ్లండి." },
  "sx-5": { text: "నా చెల్లి నాతో రావచ్చా?", when: "7 వారాల క్రితం" },
};
const TE_MED: Record<string, { label: string; when: string }> = {
  med1: { label: "ఉదయం మాత్రలు", when: "ప్రతిరోజూ, నీటితో" },
  med2: { label: "విటమిన్ మాత్ర", when: "ప్రతిరోజూ, సాయంత్రం" },
};

/** The sample set in the patient's language. Same ids and structure in both languages. */
export function sampleFor(lang: Lang) {
  const te = lang === "te";
  return {
    patientName: te ? "రవి" : patientProfile.name,
    clinic: te ? TE_CLINIC : patientProfile.clinic,
    supporter: te ? { name: "లక్ష్మి", relation: "సోదరి" } : SUPPORTER,
    messages: MESSAGES.map((m) => (te ? { ...m, ...TE_MSG[m.id] } : m)),
    upcoming: UPCOMING.map((a) => (te ? { ...a, ...TE_APPT[a.id] } : a)),
    past: PAST.map((a) => (te ? { ...a, ...TE_APPT[a.id] } : a)),
    pastRequests: PAST_REQUESTS.map((r) => (te ? { ...r, ...TE_REQ[r.id] } : r)),
    medicines: MEDICINES.map((m) => (te ? { ...m, ...TE_MED[m.id] } : m)),
  };
}
