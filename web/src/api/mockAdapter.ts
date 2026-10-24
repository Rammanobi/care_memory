import { makeEmpty, makeSeed } from "../mocks/seed";
import { applyAction } from "./reducer";
import type { CareApi, CareState } from "./types";

const KEY = "cm_mock_db_v2";
const seed = () => (location.search.includes("empty") ? makeEmpty() : makeSeed());
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function read(): CareState {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return JSON.parse(raw) as CareState;
  } catch {
    /* storage blocked: fall through to the seed */
  }
  return seed();
}

function write(s: CareState) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* storage blocked: state stays in memory only */
  }
}

/** Mock backend. Persists to localStorage so the doctor and patient tabs share one store. */
export const mockApi: CareApi = {
  async load() {
    if (!location.search.includes("nodelay")) await wait(450); // lets the loading skeletons be seen (add ?nodelay to skip)
    return read();
  },
  async dispatch(action) {
    const next = applyAction(read(), action);
    write(next);
    return next;
  },
  subscribe(cb) {
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY || e.key === null) cb();
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  },
  async reset() {
    const s = seed();
    write(s);
    return s;
  },
};
