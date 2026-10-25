// Fictional sample data (synthetic patients, no real people). makeSeed() builds a fresh state; makeEmpty() the empty-state view.
import type { Approval, AuditEntry, CareState, Evidence, EvKind, Message, Patient, PatientRequest, UsageMode } from "../api/types";

// code, sex, age, day, base, tag, why, missed, noData, nextStep, visitThisWeek, quiet, nextVisit, supporter, consent, clinic, changes[text, ev]
type PT = [string, "M" | "F", number, number, Patient["base"], string, string, number[], number, string, boolean, boolean, string, string, string, string, [string, string][]];
const PTS: PT[] = [
  ["PT-0142", "M", 34, 60, "red", "RED", "Refill gap suspected", [3, 5, 6, 9, 10, 11, 18, 19], 0, "Approve visit Wed 6 pm", true, false, "Wed 6 pm", "Linked", "Active", "anantapur", [["Missed 3 doses in 4 days", "E-0412"], ["no chemist refill since day 33", "E-0388"], ["Supporter says he is travelling", "E-0420"]]],
  ["PT-0087", "F", 41, 44, "red", "RED", "3 missed, lab slot open", [13, 14, 17], 0, "Approve call today", true, false, "Fri 10 am", "Linked", "Active", "anantapur", [["3 missed doses in 7 days", "E-0377"], ["lab slot still open", "E-0391"]]],
  ["PT-0213", "F", 29, 18, "grn", "ASKED", "Wants reminder at 7 pm", [17], 0, "Approve change", false, false, "Mon 11 am", "Not linked", "Active", "anantapur", [["Asked to change her reminder time", "E-0431"]]],
  ["PT-0198", "F", 37, 52, "amb", "QUIET", "No reply for 6 days", [], 6, "Ask Supporter to check", true, true, "Today 4 pm", "Linked", "Active", "anantapur", [["No data since Monday", "E-0405"], ["Last reply was 6 days ago", "E-0361"]]],
  ["PT-0301", "M", 45, 40, "grn", "ON TRACK", "Adherence steady", [], 0, "Nothing needed", false, false, "Next month", "Linked", "Active", "anantapur", [["No missed doses in 20 days", "E-0399"]]],
  ["PT-0254", "M", 52, 27, "amb", "WATCH", "Felt tired after tablets", [8, 12, 15], 0, "Approve check-in message", false, false, "Today 11 am", "Linked", "Active", "anantapur", [["Reported feeling tired in the mornings", "E-0425"], ["2 doses logged late", "E-0366"]]],
  ["PT-0416", "F", 61, 95, "grn", "ON TRACK", "Adherence steady", [], 0, "Nothing needed", false, false, "Next month", "Linked", "Active", "anantapur", [["No missed doses in 20 days", "E-0433"]]],
  ["PT-0900", "F", 40, 3, "amb", "WATCH", "Day 3: little is known yet", [], 0, "Approve welcome message", false, false, "Thu 10 am", "Not linked", "Pending", "anantapur", [["First dose logged on day 1", "E-0301"], ["No chemist record yet", "E-0302"]]],
  ["PT-0901", "F", 40, 60, "grn", "ON TRACK", "Day 60: pattern is known", [4], 0, "Nothing needed", false, false, "Next month", "Linked", "Active", "anantapur", [["Takes doses 7 to 8 am, steady", "E-0440"]]],
  ["PT-0176", "F", 58, 71, "red", "RED", "Missed 5 of last 7", [10, 13, 14, 16, 17, 19], 0, "Approve call today", true, false, "Today 2 pm", "Linked", "Active", "kalyandurg", [["5 missed doses in 7 days", "E-0415"], ["Phone was off for 2 days", "E-0416"]]],
  ["PT-0310", "M", 31, 12, "grn", "ON TRACK", "Adherence steady", [], 0, "Nothing needed", false, false, "Next week", "Linked", "Active", "kalyandurg", [["All doses logged this week", "E-0408"]]],
  ["PT-0322", "F", 26, 90, "grn", "ON TRACK", "Adherence steady", [7], 0, "Nothing needed", false, false, "Next month", "Not linked", "Active", "kalyandurg", [["Reminder moved to 8 pm", "E-0409"]]],
  ["PT-0333", "M", 63, 35, "amb", "QUIET", "No data for 4 days", [], 4, "Ask Supporter to check", true, true, "Thu 9 am", "Linked", "Active", "kalyandurg", [["No data since Tuesday", "E-0417"]]],
  ["PT-0345", "F", 47, 8, "amb", "WATCH", "First week, 2 doses missed", [5, 9], 0, "Approve first-week note", false, false, "Sat 10 am", "Not linked", "Active", "kalyandurg", [["2 missed doses in first 7 days", "E-0422"]]],
  ["PT-0427", "M", 36, 48, "amb", "WATCH", "Travelling, supply low", [14], 0, "Approve supply check", true, false, "Fri 3 pm", "Linked", "Active", "kalyandurg", [["Told supporter about a trip", "E-0428"], ["Strip count suggests 3 days left", "E-0429"]]],
  ["PT-0360", "M", 39, 120, "grn", "ON TRACK", "Adherence steady", [], 0, "Nothing needed", false, false, "Next month", "Linked", "Active", "dharmavaram", [["Visit done, all well", "E-0410"]]],
  ["PT-0371", "F", 33, 66, "red", "RED", "Lab result overdue", [11, 12, 15, 18], 0, "Approve lab follow-up", true, false, "Wed 12 pm", "Linked", "Active", "dharmavaram", [["Lab result 9 days late", "E-0418"], ["4 missed doses in 10 days", "E-0419"]]],
  ["PT-0382", "M", 55, 150, "grn", "ON TRACK", "Adherence steady", [], 0, "Nothing needed", false, false, "Next month", "Linked", "Withdrawn", "dharmavaram", [["Supporter consent withdrawn", "E-0414"]]],
  ["PT-0394", "F", 44, 22, "amb", "QUIET", "No reply for 3 days", [], 3, "Ask Supporter to check", false, true, "Next week", "Linked", "Active", "dharmavaram", [["No data since Wednesday", "E-0423"]]],
  ["PT-0405", "M", 28, 5, "grn", "ON TRACK", "New, doing well", [], 0, "Nothing needed", false, false, "Today 5 pm", "Not linked", "Pending", "dharmavaram", [["Started well, 5 of 5 doses", "E-0424"]]],
];

// id, code, at, kind, reporter, text, why
type EV = [string, string, string, EvKind, string, string, string];
const EVS: EV[] = [
  ["E-0301", "PT-0900", "Day 1 · 08:05", "dose", "Patient app", "First dose logged", "First data point; starts the record"],
  ["E-0302", "PT-0900", "Day 2 · 17:40", "refill", "Chemist feed", "No chemist record yet", "Nothing to compare the supply against yet"],
  ["E-0303", "PT-0900", "Day 3 · 09:10", "message", "Patient app", "Asked: when is my next visit?", "Shows the patient reads messages"],
  ["E-0304", "PT-0901", "Day 3 · 08:20", "dose", "Patient app", "Dose logged at 8:20", "Early sign of her morning routine"],
  ["E-0305", "PT-0901", "Day 9 · 07:50", "dose", "Patient app", "Dose logged at 7:50", "Routine is forming"],
  ["E-0306", "PT-0901", "Day 20 · 07:45", "refill", "Chemist feed", "Refill collected on time", "Supply matches the doses logged"],
  ["E-0307", "PT-0901", "Day 34 · 12:30", "dose", "Patient app", "One missed dose, reason: forgot", "A single miss with a clear reason"],
  ["E-0308", "PT-0901", "Day 45 · 09:00", "visit", "Clinic", "Visit done, no concerns", "Doctor saw her in person"],
  ["E-0309", "PT-0901", "Day 57 · 07:55", "supporter", "Supporter", "Supporter says she is well", "Second source agrees with the app"],
  ["E-0361", "PT-0198", "Day 46 · 10:15", "message", "Patient app", "Last reply from the patient", "Start of the silence"],
  ["E-0362", "PT-0198", "Day 49 · 08:00", "system", "System", "Reminder sent, no response", "Silence is not the same as missing"],
  ["E-0363", "PT-0213", "Day 15 · 19:10", "dose", "Patient app", "Dose logged at 7 pm", "Shows an evening habit"],
  ["E-0364", "PT-0213", "Day 17 · 09:00", "dose", "Patient app", "Missed morning dose", "Morning reminder does not fit her day"],
  ["E-0365", "PT-0301", "Day 38 · 08:00", "dose", "Patient app", "All doses logged this week", "Steady routine"],
  ["E-0366", "PT-0254", "Day 25 · 10:40", "dose", "Patient app", "Dose logged 3 hours late", "Pattern of late doses"],
  ["E-0367", "PT-0254", "Day 26 · 11:10", "dose", "Patient app", "Dose logged 2 hours late", "Second late dose in a row"],
  ["E-0368", "PT-0142", "Day 40 · 08:05", "dose", "Patient app", "Dose logged at 8:05", "Good run before the gap"],
  ["E-0369", "PT-0142", "Day 47 · 08:12", "visit", "Clinic", "Visit done, supply given for 14 days", "Defines when the next refill is due"],
  ["E-0370", "PT-0087", "Day 38 · 09:30", "visit", "Clinic", "Lab test requested", "Opens the lab slot"],
  ["E-0371", "PT-0176", "Day 62 · 08:00", "dose", "Patient app", "Dose logged", "Start of recent run"],
  ["E-0372", "PT-0176", "Day 65 · 08:00", "supporter", "Supporter", "Supporter visited, patient was resting", "Context for the missed doses"],
  ["E-0373", "PT-0333", "Day 31 · 18:20", "dose", "Patient app", "Last dose logged", "Last data before the quiet days"],
  ["E-0374", "PT-0371", "Day 55 · 11:00", "lab", "Lab feed", "Sample collected", "Starts the result clock"],
  ["E-0375", "PT-0371", "Day 60 · 11:00", "lab", "Lab feed", "Result not received after 5 days", "Result is later than usual"],
  ["E-0376", "PT-0345", "Day 3 · 08:30", "dose", "Patient app", "Dose logged", "First week routine starting"],
  ["E-0377", "PT-0087", "Day 43 · 08:15", "dose", "Patient app", "3 missed doses in 7 days", "Rule: 3 missed in 7 days raises the rank"],
  ["E-0378", "PT-0427", "Day 44 · 09:00", "refill", "Chemist feed", "Refill collected", "Supply starts here"],
  ["E-0379", "PT-0360", "Day 112 · 10:00", "visit", "Clinic", "Visit done", "Routine review"],
  ["E-0380", "PT-0310", "Day 10 · 08:00", "dose", "Patient app", "All doses logged", "Good start"],
  ["E-0381", "PT-0322", "Day 80 · 20:00", "dose", "Patient app", "Dose logged at 8 pm", "Evening routine"],
  ["E-0382", "PT-0382", "Day 140 · 09:30", "visit", "Clinic", "Visit done", "Routine review"],
  ["E-0383", "PT-0394", "Day 18 · 08:10", "dose", "Patient app", "Dose logged", "Last data before the quiet days"],
  ["E-0384", "PT-0405", "Day 2 · 07:40", "dose", "Patient app", "Dose logged", "Good start"],
  ["E-0385", "PT-0416", "Day 90 · 08:00", "dose", "Patient app", "Dose logged", "Steady routine"],
  ["E-0388", "PT-0142", "Day 58 · 10:05", "refill", "Chemist feed", "No refill since day 33", "Supply for 14 days ran out around day 47"],
  ["E-0391", "PT-0087", "Day 44 · 09:45", "lab", "Lab feed", "Lab slot still open", "No sample has been collected yet"],
  ["E-0399", "PT-0301", "Day 40 · 08:00", "dose", "Patient app", "No missed doses in 20 days", "Sign of a steady routine"],
  ["E-0405", "PT-0198", "Day 52 · 09:00", "system", "System", "No data since Monday", "Silent for 6 days; rank raised"],
  ["E-0408", "PT-0310", "Day 12 · 08:00", "dose", "Patient app", "All doses logged this week", "Steady start"],
  ["E-0409", "PT-0322", "Day 90 · 10:20", "message", "Patient app", "Reminder moved to 8 pm", "Patient chose a time that fits"],
  ["E-0410", "PT-0360", "Day 120 · 10:00", "visit", "Clinic", "Visit done, all well", "Routine review"],
  ["E-0412", "PT-0142", "Day 59 · 08:10", "dose", "Patient app", "Missed 3 doses in 4 days", "Rule: 3 missed in 4 days raises the rank"],
  ["E-0414", "PT-0382", "Day 150 · 11:00", "message", "Clinic", "Supporter consent withdrawn", "Supporter messages are paused"],
  ["E-0415", "PT-0176", "Day 70 · 08:00", "dose", "Patient app", "5 missed doses in 7 days", "Rule: 5 missed in 7 days is RED"],
  ["E-0416", "PT-0176", "Day 70 · 12:00", "supporter", "Supporter", "Phone was off for 2 days", "May explain the silence"],
  ["E-0417", "PT-0333", "Day 35 · 09:00", "system", "System", "No data since Tuesday", "Silent for 4 days"],
  ["E-0418", "PT-0371", "Day 66 · 09:00", "lab", "Lab feed", "Lab result 9 days late", "Needs a follow-up call"],
  ["E-0419", "PT-0371", "Day 66 · 08:30", "dose", "Patient app", "4 missed doses in 10 days", "Second reason for the rank"],
  ["E-0420", "PT-0142", "Day 59 · 18:30", "supporter", "Supporter", "Supporter says he is travelling", "May explain the refill gap"],
  ["E-0422", "PT-0345", "Day 8 · 09:00", "dose", "Patient app", "2 missed doses in first 7 days", "Early misses are worth a kind check-in"],
  ["E-0423", "PT-0394", "Day 22 · 09:00", "system", "System", "No data since Wednesday", "Silent for 3 days"],
  ["E-0424", "PT-0405", "Day 5 · 08:00", "dose", "Patient app", "Started well, 5 of 5 doses", "Good start"],
  ["E-0425", "PT-0254", "Day 27 · 09:20", "message", "Patient app", "Said he felt tired in the mornings", "A nurse should check how he feels"],
  ["E-0428", "PT-0427", "Day 48 · 17:00", "supporter", "Supporter", "Told supporter about a trip", "Travel can break the routine"],
  ["E-0429", "PT-0427", "Day 48 · 17:05", "refill", "Chemist feed", "Strip count suggests 3 days left", "Supply may run out during the trip"],
  ["E-0431", "PT-0213", "Day 18 · 08:40", "message", "Patient app", "Asked to change her reminder time", "Request waiting for approval"],
  ["E-0433", "PT-0416", "Day 95 · 08:00", "dose", "Patient app", "No missed doses in 20 days", "Steady routine"],
  ["E-0440", "PT-0901", "Day 60 · 07:55", "dose", "Patient app", "Takes doses 7 to 8 am, steady", "Learned routine from 60 days of data"],
  ["E-0441", "PT-0142", "Day 55 · 08:00", "dose", "Patient app", "Dose logged", "Part of the good run before the gap"],
  ["E-0442", "PT-0142", "Day 56 · 08:10", "dose", "Patient app", "Dose logged", "Part of the good run before the gap"],
  ["E-0443", "PT-0087", "Day 41 · 08:00", "dose", "Patient app", "Dose logged", "Before the misses started"],
  ["E-0444", "PT-0176", "Day 68 · 08:00", "dose", "Patient app", "Missed dose", "One of 5 misses this week"],
  ["E-0446", "PT-0142", "Day 60 · 09:12", "message", "Patient app", "Asked to move the visit to Thursday", "The request is waiting for approval"],
  ["E-0447", "PT-0213", "Day 18 · 09:30", "message", "Patient app", "Asked about taking paracetamol for a headache", "A medicine question; needs a clinical answer"],
  ["E-0445", "PT-0371", "Day 64 · 08:00", "dose", "Patient app", "Missed dose", "One of 4 misses"],
];
const BCR: Evidence[] = [
  { id: "B-0101", code: "PT-0142", at: "Day 60", kind: "system", reporter: "Memory engine", text: "Takes the morning dose around 8 am", why: "Learned from 38 logged doses; used to judge a late dose" },
  { id: "B-0102", code: "PT-0142", at: "Day 60", kind: "system", reporter: "Memory engine", text: "Refill is due about every 14 days", why: "Learned from the last 2 refills" },
  { id: "C-0201", code: "PT-0142", at: "Day 59", kind: "system", reporter: "Memory engine", text: "App says doses taken, chemist shows no refill", why: "Two sources disagree; needs a human look" },
  { id: "R-0301", code: "PT-0142", at: "Day 60", kind: "system", reporter: "Risk rules", text: "Risk rank: high (range 58 to 74 out of 100)", why: "Shown as a range because the sources disagree" },
  { id: "R-0302", code: "PT-0087", at: "Day 44", kind: "system", reporter: "Risk rules", text: "Risk rank: raised (range 44 to 61 out of 100)", why: "3 missed in 7 days and an open lab slot" },
  { id: "R-0303", code: "PT-0176", at: "Day 71", kind: "system", reporter: "Risk rules", text: "Risk rank: high (range 66 to 82 out of 100)", why: "5 missed in 7 days" },
  { id: "B-0103", code: "PT-0198", at: "Day 52", kind: "system", reporter: "Memory engine", text: "Usually replies within a day", why: "So 4 days of silence is unusual for her" },
  { id: "B-0104", code: "PT-0213", at: "Day 18", kind: "system", reporter: "Memory engine", text: "Prefers evening reminders", why: "Evening doses were on time; morning ones were missed" },
  { id: "B-0105", code: "PT-0901", at: "Day 60", kind: "system", reporter: "Memory engine", text: "Doses between 7 and 8 am", why: "Learned from 54 logged doses" },
  { id: "B-0106", code: "PT-0901", at: "Day 60", kind: "system", reporter: "Memory engine", text: "Supporter and app agree", why: "Two sources match, so trust is higher" },
  { id: "B-0107", code: "PT-0900", at: "Day 3", kind: "system", reporter: "Memory engine", text: "Dose time not known yet", why: "Only 3 days of data" },
  { id: "C-0202", code: "PT-0371", at: "Day 66", kind: "system", reporter: "Memory engine", text: "Lab feed shows collected, no result", why: "The result may be lost or late" },
];

const DAYS = [2.4, 3.1, 2.8, 3.6, 4.2, 3.3, 2.9, 3.8, 4.4, 5.1, 3.9, 4.6, 5.3, 4.1];
export function usageFor(mode: UsageMode) {
  const today = mode === "GREEN" ? 4.1 : mode === "AMBER" ? 7.4 : 9.35;
  const used = mode === "GREEN" ? 61 : mode === "AMBER" ? 98 : 131;
  const days = DAYS.map((spend, i) => ({ d: `D${i + 47}`, spend: i === 13 ? today : spend }));
  const f = mode === "GREEN" ? 1 : mode === "AMBER" ? 1.8 : 2.3;
  const tasks = [
    { name: "Nightly memory rebuild", spend: +(2.1 * f).toFixed(2), pct: 52, flag: "on budget" },
    { name: "Narrator cards", spend: +(1.2 * f).toFixed(2), pct: 30, flag: "on budget" },
    { name: "Doctor Ask box", spend: +(0.55 * f).toFixed(2), pct: 68, flag: "watch" },
    { name: "Other", spend: +(0.25 * f).toFixed(2), pct: 6, flag: "on budget" },
  ];
  return { mode, todaySpend: today, todayCap: 10, budgetUsed: used, budget: 150, days, tasks, retries: mode === "GREEN" ? 7 : 12, breaker: mode === "RED" ? 2 : 0, billing: 0, providerPct: mode === "GREEN" ? 22 : mode === "AMBER" ? 48 : 71 };
}

export function makeSeed(): CareState {
  const t0 = Date.now();
  const patients: Patient[] = PTS.map((r) => ({
    code: r[0], sex: r[1], age: r[2], day: r[3], base: r[4], tag: r[5], why: r[6], missed: r[7], noData: r[8], nextStep: r[9],
    visitThisWeek: r[10], quiet: r[11], nextVisit: r[12], supporter: r[13], consent: r[14], clinic: r[15],
    changes: r[16].map(([text, ev]) => ({ text, ev })),
  }));
  const evidence: Evidence[] = [
    ...EVS.map(([id, code, at, kind, reporter, text, why]) => ({ id, code, at, kind, reporter, text, why })),
    ...BCR,
  ].sort((a, b) => (a.id < b.id ? 1 : -1));

  const rq = (id: string, patientCode: string, kind: string, text: string, when: string, draft: string, status: PatientRequest["status"], dueMin: number, refs: string[] = [], extra: Partial<PatientRequest> = {}): PatientRequest => ({
    id, patientCode, kind, text, when, draft, status, dueMin, refs, createdAt: t0 - 3600000, ...(status === "approved" ? { reply: draft } : {}), ...extra,
  });
  const requests: PatientRequest[] = [
    rq("rq-1", "PT-0142", "Change visit", "Can I move my visit to Thursday?", "today 09:12", "Your visit is moved to Thursday 5 pm. Please bring your medicine strip.", "waiting", 102, ["E-0446", "E-0420"]),
    rq("rq-2", "PT-0213", "Reminder time", "Please remind me at 7 pm, not in the morning.", "today 08:40", "Your reminder is now 7 pm. Tell us if you want to change it again.", "waiting", 190, ["E-0431", "B-0104"]),
    rq("rq-3", "PT-0087", "Other", "Can I do my lab test on Friday?", "yesterday 18:05", "Your lab slot is held for Friday 10 am. Please come after breakfast.", "waiting", 45, ["E-0391"]),
    rq("rq-4", "PT-0176", "Other", "Can someone call me? My phone was off.", "today 07:50", "A nurse will call you today before noon. Please keep your phone on.", "waiting", 75, ["E-0416"]),
    rq("rq-5", "PT-0254", "Other", "I felt tired after my morning tablets. What should I do?", "today 09:20", "Thank you for telling us. A nurse will call you today to ask how you feel.", "waiting", 130, ["E-0425"]),
    rq("rq-6", "PT-0301", "Visit", "Can I get a reminder before my next visit?", "yesterday 12:00", "Yes. We will remind you 2 days before your visit.", "approved", 0),
    rq("rq-7", "PT-0322", "Reminder time", "Please move my reminder to 8 pm.", "2 days ago", "Your reminder is now 8 pm.", "approved", 0, ["E-0409"]),
    rq("rq-8", "PT-0310", "Other", "Can I skip this week?", "2 days ago", "Please call the clinic so we can talk about it.", "declined", 0),
    rq("rq-9", "PT-0345", "Other", "Where is the lab?", "3 days ago", "The lab is on the ground floor, next to the pharmacy.", "approved", 0),
    // Patient questions with research (add-doctor-question-ui): ready, pending and failed, so the screen can be demoed offline.
    rq("rq-q1", "PT-0213", "Question", "Can I take my tablets together with paracetamol for my headache?", "today 09:30", "Thank you for asking. Please do not add anything new on your own. A nurse will call you today and tell you what is safe.", "waiting", 90, [], {
      origin: { channel: "telegram", excerpt: "Can I take my tablets together with paracetamol for my headache?" },
      research: { status: "ready", category: "medicine", priority: "high", confidence: "medium", model: "sample", costUsd: 0.0021, suggestedReply: "Thank you for asking. Please do not add anything new on your own. A nurse will call you today and tell you what is safe.",
        brief: [{ text: "The patient asked today about taking paracetamol for a headache.", refs: ["E-0447"] }, { text: "One morning dose was missed in the last 7 days.", refs: ["E-0364"] }, { text: "No medicine change is on record since the last visit.", refs: [] }] },
    }),
    rq("rq-q2", "PT-0142", "Question", "Which foods should I eat to get stronger?", "today 09:41", "", "waiting", 200, [], {
      origin: { channel: "portal", excerpt: "Which foods should I eat to get stronger?" },
      research: { status: "pending", category: "food", priority: "normal", brief: [], suggestedReply: "" },
    }),
    rq("rq-q3", "PT-0254", "Question", "I have a bad cough with blood since last night and I feel very weak.", "today 09:48", "Please go to the nearest clinic or call the emergency number now. A nurse will also call you.", "waiting", 20, [], {
      origin: { channel: "telegram", excerpt: "I have a bad cough with blood since last night and I feel very weak." },
      research: { status: "failed", category: "symptom", priority: "urgent", brief: [], suggestedReply: "Please go to the nearest clinic or call the emergency number now. A nurse will also call you.", reason: "the record search timed out" },
    }),
    // Uploaded documents to check (add-document-upload): one with fields at all three confidence levels, one where nothing could be read.
    rq("rq-d1", "PT-0087", "Document", "Uploaded a file: lab_report.pdf", "today 08:55", "Thank you. We have added your lab report to your record.", "waiting", 150, ["E-0391"], {
      origin: { channel: "portal", excerpt: "Uploaded a file: lab_report.pdf" },
      document: { id: "doc-1", filename: "lab_report.pdf", mime: "application/pdf", size: 184320, pages: 2, status: "with your care team", docType: "lab_report",
        fields: [{ name: "Test", value: "Sputum smear", confidence: "high" }, { name: "Collected on", value: "12 March", confidence: "medium" }, { name: "Result", value: "Negative (hand-written, hard to read)", confidence: "low" }],
        textExcerpt: "Anantapur Urban Clinic laboratory. Patient PT-0087. Sputum smear collected 12 March. Result: negative." },
    }),
    rq("rq-d2", "PT-0371", "Document", "Uploaded a file: photo_0042.jpg", "today 09:05", "Thank you. Please bring the original paper to your next visit.", "waiting", 210, [], {
      origin: { channel: "telegram", excerpt: "Uploaded a file: photo_0042.jpg" },
      document: { id: "doc-2", filename: "photo_0042.jpg", mime: "image/jpeg", size: 903168, pages: null, status: "with your care team", docType: "other", fields: [], textExcerpt: "" },
    }),
    rq("rq-0", "PT-0142", "Reminder time", "Can you remind me at 7 pm?", "last week", "Reminder now 7 pm", "approved", 0, [], { archived: true }),
  ];

  const ap = (id: string, patientCode: string, lane: Approval["lane"], title: string, draft: string, dueMin: number, why: string, refs: string[], status: Approval["status"] = "waiting"): Approval => ({
    id, patientCode, lane, title, draft, dueMin, why, refs, status, ...(status === "approved" ? { reply: draft } : {}),
  });
  const approvals: Approval[] = [
    ap("ap-1", "PT-0142", "red", "Confirm visit Wed 6 pm", "Please come to the clinic on Wednesday at 6 pm. Bring your medicine strip.", 102, "No refill since day 33 and 3 missed doses in 4 days.", ["E-0412", "E-0388", "R-0301"]),
    ap("ap-2", "PT-0087", "red", "Call today", "A nurse will call you today about your lab test. Please keep your phone near you.", 185, "3 missed doses in 7 days and the lab slot is still open.", ["E-0377", "E-0391", "R-0302"]),
    ap("ap-7", "PT-0176", "red", "Call today", "A nurse will call you today. Please keep your phone on and near you.", 38, "5 missed doses in 7 days; phone was off.", ["E-0415", "E-0416", "R-0303"]),
    ap("ap-8", "PT-0371", "red", "Lab result follow-up", "We are checking your lab result. Please come to the clinic on Wednesday at 12 pm.", 240, "Lab result is 9 days late and 4 doses were missed.", ["E-0418", "E-0419", "C-0202"]),
    ap("ap-3", "PT-0198", "amber", "Ask Supporter to check", "We have not heard from you for some days. Please tell us how you are.", 300, "No data for 6 days; she usually replies within a day.", ["E-0405", "B-0103"]),
    ap("ap-9", "PT-0254", "amber", "Check-in message", "How are you feeling this week? A nurse is happy to talk if you want to.", 420, "Said he felt tired; 2 doses logged late.", ["E-0425", "E-0366"]),
    ap("ap-10", "PT-0333", "amber", "Ask Supporter to check", "Your family helper will check in with you today. Please reply when you can.", 360, "No data for 4 days.", ["E-0417"]),
    ap("ap-11", "PT-0345", "amber", "First-week note", "Welcome. Two doses were missed this week. It is common. Tell us if anything is hard.", 480, "2 missed doses in the first week.", ["E-0422"]),
    ap("ap-15", "PT-0394", "amber", "Ask Supporter to check", "We have not heard from you for 3 days. Please tell us how you are.", 390, "No data for 3 days.", ["E-0423"]),
    ap("ap-16", "PT-0427", "amber", "Supply check before trip", "Planning a trip? Please visit us on Friday at 3 pm to collect enough medicine.", 330, "Strip count suggests 3 days left and a trip is planned.", ["E-0428", "E-0429"]),
    ap("ap-17", "PT-0900", "amber", "Welcome message", "Welcome. We will remind you each morning. Tell us what time suits you best.", 520, "Day 3: the system does not know her routine yet.", ["E-0301", "B-0107"]),
    ap("ap-4", "PT-0301", "green", "Weekly thank-you note", "Well done, you did not miss a day this week. Keep going.", 900, "No missed doses in 20 days.", ["E-0399"]),
    ap("ap-5", "PT-0213", "green", "Reminder time confirmed", "Your reminder time is saved. See you at your next visit.", 900, "Follows her request.", ["E-0431"]),
    ap("ap-6", "PT-0301", "green", "Visit reminder", "Your next visit is next month. We will remind you a few days before.", 900, "Routine reminder.", ["E-0399"]),
    ap("ap-12", "PT-0310", "green", "Weekly thank-you note", "Great start. All your doses were logged this week.", 900, "All doses logged.", ["E-0408"]),
    ap("ap-13", "PT-0322", "green", "Weekly thank-you note", "Thank you for keeping up. See you next month.", 900, "Steady routine.", ["E-0409"]),
    ap("ap-14", "PT-0360", "green", "Visit reminder", "Your next visit is next month. We will remind you a few days before.", 0, "Routine reminder.", ["E-0410"], "approved"),
  ];

  const msg = (id: string, srcId: string, code: string, at: string, channel: string, text: string, status: Message["status"], version = 1): Message => ({ id, srcId, code, at, channel, text, approvedBy: "Dr. A. Rao", version, status });
  const messages: Message[] = [
    msg("m-1", "rq-6", "PT-0301", "yesterday 12:20", "Patient app", "Yes. We will remind you 2 days before your visit.", "seen"),
    msg("m-2", "rq-7", "PT-0322", "2 days ago 10:30", "Patient app", "Your reminder is now 8 pm.", "seen"),
    msg("m-3", "rq-9", "PT-0345", "3 days ago 11:00", "Patient app", "The lab is on the ground floor, next to the pharmacy.", "seen"),
    msg("m-4", "ap-14", "PT-0360", "yesterday 16:00", "Telegram", "Your next visit is next month. We will remind you a few days before.", "seen"),
    msg("m-5", "old-1", "PT-0142", "last week 09:00", "Patient app", "Reminder now 7 pm", "seen"),
    msg("m-6", "old-2", "PT-0142", "Day 47 · 08:30", "Telegram", "Your supply is for 14 days. Please come back on day 61.", "seen"),
    msg("m-7", "old-3", "PT-0087", "Day 38 · 10:00", "Telegram", "Please come for a lab test. The nurse will take a small sample.", "seen", 2),
    msg("m-8", "old-4", "PT-0901", "Day 45 · 10:00", "Telegram", "Thank you for coming today. See you next month.", "seen"),
    msg("m-9", "old-5", "PT-0176", "Day 66 · 09:00", "Telegram", "We noticed you missed a few doses. Is everything all right?", "seen", 2),
    msg("m-10", "old-6", "PT-0198", "Day 49 · 09:00", "Telegram", "Good morning. Please tell us how you are today.", "sent"),
    msg("m-11", "old-7", "PT-0301", "Day 38 · 18:00", "Telegram", "Well done this week. Keep going.", "seen"),
    msg("m-12", "old-8", "PT-0900", "Day 1 · 08:00", "Telegram", "Welcome to the programme. We will help you each day.", "seen"),
  ];
  const au = (id: string, code: string, at: string, actor: string, action: string, srcId?: string, version?: number, note?: string): AuditEntry => ({ id, code, at, actor, action, srcId, version, note });
  const audit: AuditEntry[] = [
    au("au-1", "PT-0142", "today 07:58", "Assistant", "Drafted: Confirm visit Wed 6 pm", "ap-1", 1, "Cited E-0412, E-0388"),
    au("au-2", "PT-0142", "today 09:12", "Patient", "Asked to move visit", "rq-1"),
    au("au-3", "PT-0142", "today 09:13", "Assistant", "Drafted reply", "rq-1", 1),
    au("au-4", "PT-0142", "last week 09:00", "Dr. A. Rao", "Approved reply", "old-1", 1),
    au("au-5", "PT-0142", "Day 47 · 08:30", "Dr. A. Rao", "Approved reply", "old-2", 1),
    au("au-6", "PT-0087", "Day 38 · 09:55", "Dr. A. Rao", "Edited then approved", "old-3", 2, "Shortened the text"),
    au("au-7", "PT-0087", "today 08:05", "Assistant", "Drafted: Call today", "ap-2", 1),
    au("au-8", "PT-0176", "today 07:40", "Assistant", "Drafted: Call today", "ap-7", 1),
    au("au-9", "PT-0176", "Day 66 · 08:55", "Dr. A. Rao", "Edited then approved", "old-5", 2, "Made the tone softer"),
    au("au-10", "PT-0198", "Day 49 · 08:50", "Dr. A. Rao", "Approved reply", "old-6", 1),
    au("au-11", "PT-0301", "yesterday 12:20", "Dr. A. Rao", "Approved reply", "rq-6", 1),
    au("au-12", "PT-0322", "2 days ago 10:30", "Dr. A. Rao", "Approved reply", "rq-7", 1),
    au("au-13", "PT-0310", "2 days ago 14:00", "Dr. A. Rao", "Declined reply", "rq-8", 1, "Needs a phone call instead"),
    au("au-14", "PT-0345", "3 days ago 11:00", "Dr. A. Rao", "Approved reply", "rq-9", 1),
    au("au-15", "PT-0360", "yesterday 16:00", "Dr. A. Rao", "Approved reply", "ap-14", 1),
    au("au-16", "PT-0382", "Day 150 · 11:00", "Clinic staff", "Recorded Supporter consent withdrawn", undefined, undefined, "Supporter messages paused"),
    au("au-17", "PT-0901", "Day 45 · 10:00", "Dr. A. Rao", "Approved reply", "old-4", 1),
    au("au-18", "PT-0900", "Day 1 · 07:55", "Dr. A. Rao", "Approved reply", "old-8", 1),
  ];
  return {
    patients, requests, approvals, dose: { today: "none" }, seededAt: t0, simDay: 60, evidence, messages, audit,
    notes: [
      { id: "n-1", code: "PT-0142", at: "Day 47 · 08:40", by: "Dr. A. Rao", text: "Works far from the clinic. Offer a visit after 5 pm." },
      { id: "n-2", code: "PT-0142", at: "Day 52 · 17:10", by: "Nurse S. Devi", text: "Spoke to the family helper. Patient plans a short trip." },
      { id: "n-3", code: "PT-0087", at: "Day 40 · 11:00", by: "Dr. A. Rao", text: "Lab visits are hard on weekdays. Try Friday." },
      { id: "n-4", code: "PT-0176", at: "Day 66 · 09:10", by: "Nurse S. Devi", text: "Lives alone. Phone is often switched off to save battery." },
      { id: "n-5", code: "PT-0901", at: "Day 45 · 10:15", by: "Dr. A. Rao", text: "Doing well. Next visit in a month." },
    ],
    clinics: [
      { id: "anantapur", name: "Anantapur Urban Clinic", area: "Urban" },
      { id: "kalyandurg", name: "Kalyandurg Health Centre", area: "Rural" },
      { id: "dharmavaram", name: "Dharmavaram Clinic", area: "Semi-urban" },
    ],
    templates: [
      { id: "t-1", name: "Visit reminder", text: "Your next visit is on {date} at {time}. Please bring your medicine strip." },
      { id: "t-2", name: "Weekly thank-you", text: "Well done, you took your doses this week. Keep going." },
      { id: "t-3", name: "Missed dose, gentle", text: "We noticed a missed dose. Is everything all right? Tell us if you need help." },
      { id: "t-4", name: "Call from nurse", text: "A nurse will call you today. Please keep your phone near you." },
      { id: "t-5", name: "Reminder time saved", text: "Your reminder time is saved. Tell us if you want to change it again." },
      { id: "t-6", name: "Lab test", text: "Your lab test is on {date}. Please come after breakfast." },
      { id: "t-7", name: "Welcome", text: "Welcome. We will remind you each day. Tell us what time suits you best." },
      { id: "t-8", name: "Call the clinic", text: "Please call the clinic so we can talk about it." },
    ],
    lens: [
      {
        code: "PT-0900", day: 3, known: "3 days of data, 1 source (the app)",
        beliefs: [
          { id: "B-0107", text: "Dose time not known yet", conf: "Low" },
          { id: "E-0301", text: "First dose logged on day 1", conf: "Seen once" },
          { id: "E-0302", text: "No chemist record yet", conf: "Unknown" },
        ],
        risk: [15, 70], conflicts: [],
      },
      {
        code: "PT-0901", day: 60, known: "60 days of data, 3 sources (app, chemist, Supporter)",
        beliefs: [
          { id: "B-0105", text: "Doses between 7 and 8 am", conf: "High" },
          { id: "B-0106", text: "Supporter and app agree", conf: "High" },
          { id: "E-0306", text: "Refills collected on time", conf: "High" },
        ],
        risk: [12, 24], conflicts: [{ id: "E-0307", text: "One missed dose on day 34, explained by the patient" }],
      },
    ],
    usage: usageFor("GREEN"),
    channels: [
      { name: "Telegram", connected: true, detail: "Bot online, last message 2 min ago" },
      { name: "Gmail", connected: true, detail: "Inbox watched, 0 unread replies" },
      { name: "Calendar", connected: false, detail: "Not connected (mock)" },
    ],
    settings: { notifyRed: true, notifyRequests: true, digest: false, quiet: true, sound: false },
  };
}

/** The same app with no records, to check the empty states. */
export function makeEmpty(): CareState {
  const s = makeSeed();
  return { ...s, patients: [], requests: [], approvals: [], evidence: [], messages: [], audit: [], notes: [], lens: [] };
}
