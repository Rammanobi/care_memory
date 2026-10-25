// Mock mode only (offline demo): five sample cards and the advice footer, as the server would render them.
// English and Telugu sets (Telugu NEEDS native-speaker review). The numbers come from the same sample values as the
// Home cards (streak, next visit, last 7 days), passed in by the caller, so the two never contradict.
import type { WireOwnAnswer } from "../api/mapping";

const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

export interface OwnSampleFacts {
  /** Days in a row, already including today when taken (same number as the Home streak card). */
  streak: number;
  /** Same text as the Home "Next visit" card. */
  nextVisit: string;
  /** Last 7 days, oldest first: 'o' taken, 'm' missed, 'f' not yet (today). */
  week: string[];
}

export const DEFAULT_FACTS: OwnSampleFacts = { streak: 12, nextVisit: "Wed 6 pm", week: ["o", "o", "o", "o", "o", "o", "f"] };

export const sampleOwnAnswers = (lang: "en" | "te" = "en", f: OwnSampleFacts = DEFAULT_FACTS): WireOwnAnswer[] => {
  const as_of = today();
  const missed = f.week.filter((c) => c === "m").length;
  const took = f.week.filter((c) => c === "o").length;
  const te = lang === "te";
  return [
    te
      ? { topic: "advice", question: "నా మందుల గురించి ఎవరిని అడగాలి?", answer_text: "మీ మందులు, ఆహారం లేదా లక్షణాల గురించి ఏ ప్రశ్న ఉన్నా మీ సంరక్షణ బృందాన్ని అడగండి.", as_of, lang }
      : { topic: "advice", question: "Where do I ask about my medicines?", answer_text: "For any question about your medicines, food or symptoms, ask your care team.", as_of, lang },
    te
      ? { topic: "last_refill", question: "నా మందు చివరిసారి ఎప్పుడు తీసుకున్నాను?", answer_text: "మీ చివరి రీఫిల్ అక్టోబర్ 12న.", as_of, lang }
      : { topic: "last_refill", question: "When did I last collect my medicine?", answer_text: "Your last refill was on 12 Oct.", as_of, lang },
    te
      ? { topic: "next_visit", question: "నా తదుపరి సందర్శన ఎప్పుడు?", answer_text: `మీ తదుపరి సందర్శన ${f.nextVisit}, క్లినిక్‌లో.`, as_of, lang }
      : { topic: "next_visit", question: "When is my next visit?", answer_text: `Your next visit is ${f.nextVisit} at the clinic.`, as_of, lang },
    te
      ? { topic: "streak", question: "వరుసగా ఎన్ని రోజులు మందు తీసుకున్నాను?", answer_text: `మీరు వరుసగా ${f.streak} రోజులు మందు తీసుకున్నారు.`, as_of, lang }
      : { topic: "streak", question: "How many days in a row have I taken my medicine?", answer_text: `You have taken your medicine ${f.streak} days in a row.`, as_of, lang },
    te
      ? { topic: "missed_week", question: "ఈ వారం ఎన్ని మోతాదులు మిస్ అయ్యాను?", answer_text: missed === 0 ? "గత 7 రోజుల్లో మీరు ఒక్క మోతాదు కూడా మిస్ కాలేదు." : `గత 7 రోజుల్లో మీరు ${missed} మోతాదు(లు) మిస్ అయ్యారు.`, as_of, lang }
      : { topic: "missed_week", question: "How many doses did I miss this week?", answer_text: missed === 0 ? "You did not miss any dose in the last 7 days." : `You missed ${missed} ${missed === 1 ? "dose" : "doses"} in the last 7 days.`, as_of, lang },
    te
      ? { topic: "taken_week", question: "ఈ వారం ఎన్ని మోతాదులు తీసుకున్నాను?", answer_text: `గత 7 రోజుల్లో 7 లో ${took} మోతాదులు తీసుకున్నారు.`, as_of, lang }
      : { topic: "taken_week", question: "How many doses did I take this week?", answer_text: `You took ${took} of 7 doses in the last 7 days.`, as_of, lang },
  ];
};
