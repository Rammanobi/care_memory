// Tiny shared store for connectivity and toasts (no React dependency; CareProvider renders it).
type L = () => void;
const ls = new Set<L>();
let snap = { offline: false, live: false, toast: null as string | null, bulk: null as { total: number; failures: { id: string; code: string; message: string }[] } | null };
const emit = () => {
  snap = { ...snap };
  ls.forEach((l) => l());
};
export const status = {
  get: () => snap,
  subscribe: (l: L) => {
    ls.add(l);
    return () => {
      ls.delete(l);
    };
  },
  setOffline(v: boolean) {
    if (snap.offline !== v) {
      snap = { ...snap, offline: v };
      emit();
    }
  },
  setLive(v: boolean) {
    if (snap.live !== v) {
      snap = { ...snap, live: v };
      emit();
    }
  },
  bulk(b: typeof snap.bulk) {
    snap = { ...snap, bulk: b };
    emit();
  },
  toast(msg: string | null) {
    snap = { ...snap, toast: msg };
    emit();
  },
};
