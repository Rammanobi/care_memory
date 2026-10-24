import { EXTRA } from "./i18nExtra";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "en" | "te";

// Simple string table for the patient app. Telugu wording needs a native-speaker review before real use.
const BASE = {
  home: ["Home", "హోమ్"],
  record: ["My record", "నా రికార్డు"],
  askNav: ["Ask my care team", "మా సంరక్షణ బృందాన్ని అడగండి"],
  askTab: ["Ask", "అడగండి"],
  me: ["Me", "నేను"],
  morning: ["Good morning", "శుభోదయం"],
  dayOf: ["Day {n} of your 6 month treatment", "మీ 6 నెలల చికిత్సలో {n}వ రోజు"],
  todayMed: ["TODAY'S MEDICINE", "నేటి మందు"],
  notTaken: ["Not taken yet", "ఇంకా తీసుకోలేదు"],
  taken: ["Taken today", "ఈరోజు తీసుకున్నారు"],
  missedToday: ["Missed today. Your care team knows.", "ఈరోజు మిస్ అయ్యారు. మీ బృందానికి తెలుసు."],
  tookIt: ["✓ I took it", "✓ నేను తీసుకున్నాను"],
  undo: ["Undo", "వెనక్కి"],
  missQ: ["Missed today?", "ఈరోజు మిస్ అయ్యారా?"],
  tellUs: ["Tell us", "మాకు చెప్పండి"],
  whyMissed: ["What happened?", "ఏమైంది?"],
  rForgot: ["I forgot", "మర్చిపోయాను"],
  rUnwell: ["I felt unwell", "ఆరోగ్యం బాగోలేదు"],
  rRanOut: ["I ran out", "అయిపోయాయి"],
  rTravel: ["I am travelling", "ప్రయాణంలో ఉన్నాను"],
  sendMiss: ["Tell my care team", "నా బృందానికి చెప్పండి"],
  cancel: ["Cancel", "రద్దు"],
  nextVisit: ["Next visit", "తదుపరి సందర్శన"],
  streak: ["Your streak", "మీ వరుస"],
  daysRow: ["{n} days", "{n} రోజులు"],
  inARow: ["in a row", "వరుసగా"],
  fromTeam: ["From your care team", "మీ సంరక్షణ బృందం నుండి"],
  yesterday: ["yesterday", "నిన్న"],
  last30: ["Last 30 days", "గత 30 రోజులు"],
  legTaken: ["Taken", "తీసుకున్నారు"],
  legMissed: ["Missed", "మిస్ అయ్యారు"],
  legToday: ["Today", "ఈరోజు"],
  myMeds: ["My medicines (set by your doctor)", "నా మందులు (మీ డాక్టర్ నిర్ణయించినవి)"],
  medsRead: ["You cannot change these here. Ask your doctor.", "వీటిని ఇక్కడ మార్చలేరు. మీ డాక్టర్‌ను అడగండి."],
  askTitle: ["Ask your care team", "మీ సంరక్షణ బృందాన్ని అడగండి"],
  readsFirst: ["Your doctor reads every request first", "మీ డాక్టర్ ప్రతి అభ్యర్థనను ముందుగా చదువుతారు"],
  waiting: ["Waiting for your doctor", "మీ డాక్టర్ కోసం ఎదురుచూస్తోంది"],
  sent: ["Sent", "పంపబడింది"],
  reviews: ["Doctor reviews", "డాక్టర్ చూస్తారు"],
  reply: ["Reply", "జవాబు"],
  answered: ["Answered", "జవాబు వచ్చింది"],
  approved: ["(doctor approved)", "(డాక్టర్ ఆమోదించారు)"],
  declined: ["Your doctor cannot do this. Please call your clinic.", "మీ డాక్టర్ దీన్ని చేయలేరు. దయచేసి మీ క్లినిక్‌కు కాల్ చేయండి."],
  noReq: ["You have not asked anything yet.", "మీరు ఇంకా ఏమీ అడగలేదు."],
  newReq: ["New request", "కొత్త అభ్యర్థన"],
  cChange: ["Change visit", "సందర్శన మార్చండి"],
  cRemind: ["Reminder time", "గుర్తుచేసే సమయం"],
  cRefill: ["Refill help", "మందుల సహాయం"],
  cOther: ["Other", "ఇతరం"],
  typeHere: ["Type your message", "మీ సందేశం రాయండి"],
  mic: ["Voice input is not in this preview", "వాయిస్ ఇన్‌పుట్ ఈ ప్రివ్యూలో లేదు"],
  sendDoc: ["Send to my doctor", "నా డాక్టర్‌కు పంపండి"],
  sentOk: ["Sent. Your doctor will read it first.", "పంపబడింది. మీ డాక్టర్ ముందుగా చదువుతారు."],
  coming: ["Coming up", "రాబోయేవి"],
  visit: ["Clinic visit", "క్లినిక్ సందర్శన"],
  lab: ["Lab test", "ల్యాబ్ పరీక్ష"],
  labWhen: ["Date will be shared by clinic", "తేదీని క్లినిక్ తెలియజేస్తుంది"],
  unwellB: ["Feeling very unwell?", "చాలా అనారోగ్యంగా ఉందా?"],
  unwellT: ["Do not wait for a reply. Call your clinic or emergency number", "జవాబు కోసం వేచి ఉండకండి. మీ క్లినిక్‌కు లేదా అత్యవసర నంబర్‌కు కాల్ చేయండి"],
  disc: ["This app shows your information only. It does not give medical advice.", "ఈ యాప్ మీ సమాచారాన్ని మాత్రమే చూపిస్తుంది. ఇది వైద్య సలహా ఇవ్వదు."],
  langName: ["Language", "భాష"],
  recTitle: ["My record", "నా రికార్డు"],
  meTitle: ["About me", "నా వివరాలు"],
  clinic: ["My clinic", "నా క్లినిక్"],
  switchRole: ["Switch role", "పాత్ర మార్చండి"],
  taken2: ["Taken {n}", "తీసుకున్నవి {n}"],
  missed2: ["Missed {n}", "మిస్ అయినవి {n}"],
} as const;
const T = { ...BASE, ...EXTRA };

export type Key = keyof typeof T;

interface Ctx { lang: Lang; setLang: (l: Lang) => void; t: (k: Key, v?: Record<string, string | number>) => string }
const LangCtx = createContext<Ctx | null>(null);

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    try { return localStorage.getItem("cm_lang") === "te" ? "te" : "en"; } catch { return "en"; }
  });
  useEffect(() => {
    try { localStorage.setItem("cm_lang", lang); } catch { /* ignore */ }
    document.documentElement.lang = lang;
  }, [lang]);
  const t: Ctx["t"] = (k, v) => {
    let s: string = T[k][lang === "te" ? 1 : 0];
    if (v) for (const [a, b] of Object.entries(v)) s = s.replace(`{${a}}`, String(b));
    return s;
  };
  return <LangCtx.Provider value={{ lang, setLang, t }}>{children}</LangCtx.Provider>;
}

export function useLang() {
  const c = useContext(LangCtx);
  if (!c) throw new Error("useLang outside LangProvider");
  return c;
}
