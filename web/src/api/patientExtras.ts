// Patient-side state that the shared care store does not hold: consent switches, reminder time,
// large-text mode, message read status, onboarding, Supporter taps. Kept in localStorage.
// A tiny external store (not the shared provider) so the patient app and the Supporter view share it.
import { useSyncExternalStore } from "react";

export interface Consents { telegram: boolean; gmail: boolean; calendar: boolean }
export interface Extras {
  onboarded: boolean;
  consents: Consents;
  shareSupporter: boolean; // mock mode: "Share with my Supporter" (live: the server decides)
  reminder: string; // current approved reminder time, e.g. "8:00 am"
  remReqs: { id: string; time: string }[]; // reminder-time requests sent to the doctor
  largeText: boolean;
  read: string[]; // message ids already read
  supporterMarked: boolean; // today's dose was marked by the Supporter
  empty: boolean; // demo: show empty states
  offline: boolean; // demo: pretend there is no internet
  docs: { id: string; title: string; kind: string; date: string; summary: string; status: string; size: number }[]; // mock mode: files "uploaded" in the demo
}

const KEY = "cm_patient_extras_v1";
export const DEFAULTS: Extras = {
  onboarded: false,
  consents: { telegram: true, gmail: false, calendar: false },
  shareSupporter: true,
  reminder: "8:00 am",
  remReqs: [],
  largeText: false,
  read: ["m3", "m4", "m5", "m6"], // m1 and m2 start unread
  supporterMarked: false,
  empty: false,
  offline: false,
  docs: [],
};

function load(): Extras {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch { /* ignore */ }
  return DEFAULTS;
}

let cur: Extras = load();
const subs = new Set<() => void>();
function emit() {
  try { localStorage.setItem(KEY, JSON.stringify(cur)); } catch { /* ignore */ }
  subs.forEach((f) => f());
}
export const getExtras = () => cur;
export function setExtras(p: Partial<Extras>) { cur = { ...cur, ...p }; emit(); }
export function resetExtras() { cur = { ...DEFAULTS, onboarded: true }; emit(); }
const subscribe = (f: () => void) => { subs.add(f); return () => { subs.delete(f); }; };
if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => { if (e.key === KEY) { cur = load(); subs.forEach((f) => f()); } });
}
export function useExtras(): [Extras, typeof setExtras] {
  const s = useSyncExternalStore(subscribe, () => cur, () => DEFAULTS);
  return [s, setExtras];
}
