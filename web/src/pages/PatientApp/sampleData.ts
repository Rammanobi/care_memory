// Fictional sample data for patient Ravi (PT-0142, day 60). Consistent with the shared mock store.
// No medical content. Telugu wording for these sample texts is not provided: the clinic writes them.
import { patientProfile } from "../../mocks/data";
import type { Appt, Msg, PastReq } from "./portalTypes";

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
