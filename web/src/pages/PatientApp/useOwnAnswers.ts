// "About my record" data. Live: GET /portal/answers (this patient only). Mock: sample cards so the app demos offline.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useCare } from "../../api/CareProvider";
import { useLang } from "../../components/i18n";
import { usePortal } from "./usePortal";
import { USE_MOCK } from "../../api";
import { mapOwnAnswers } from "../../api/mapping";
import { ownAnswersServer } from "../../api/serverCalls";
import type { OwnAnswers } from "../../api/types";
import { sampleOwnAnswers } from "../../mocks/ownAnswers";

export type OwnState = { k: "loading" } | { k: "error" } | { k: "ready"; data: OwnAnswers };

export function useOwnAnswers(): { s: OwnState; retry: () => void } {
  const { lang } = useLang();
  const { state } = useCare();
  const v = usePortal();
  const [s, setS] = useState<OwnState>({ k: "loading" });
  // Mock: the answers follow the language and the same sample values the Home cards show (streak, next visit, last 7 days).
  const week = v.sup.week(state?.dose.today ?? "none").join("");
  const mock = useMemo<OwnState | null>(() => (USE_MOCK ? { k: "ready", data: mapOwnAnswers(sampleOwnAnswers(lang, { streak: v.streak, nextVisit: v.nextVisitText ?? "", week: week.split("") })) } : null), [lang, v.streak, v.nextVisitText, week]);
  const [n, setN] = useState(0);
  useEffect(() => {
    if (USE_MOCK) return;
    let live = true;
    setS({ k: "loading" });
    ownAnswersServer().then((data) => { if (live) setS({ k: "ready", data }); }, () => { if (live) setS({ k: "error" }); });
    return () => { live = false; };
  }, [n]);
  const retry = useCallback(() => setN((x) => x + 1), []);
  return { s: mock ?? s, retry };
}
