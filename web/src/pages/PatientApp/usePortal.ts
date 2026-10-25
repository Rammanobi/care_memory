// One view of the patient/Supporter data for every screen. Mock mode: the sample data plus localStorage extras (mockView.ts).
// Live mode: /portal/* data held in CareState.portal (liveView.ts); only UI prefs stay in localStorage. Live mode never
// shows sample or invented data: anything the server did not send is empty or hidden.
import { useCare } from "../../api/CareProvider";
import { USE_MOCK } from "../../api";
import { useLang } from "../../components/i18n";
import { useExtras } from "../../api/patientExtras";
import { buildLiveView } from "./liveView";
import { buildMockView } from "./mockView";
import type { PView } from "./portalTypes";

export type { PView } from "./portalTypes";

export function usePortal(): PView {
  const { state, dispatch } = useCare();
  const [ex] = useExtras();
  const { lang } = useLang();
  return USE_MOCK ? buildMockView(state, ex, dispatch, lang) : buildLiveView(state?.portal, dispatch);
}
