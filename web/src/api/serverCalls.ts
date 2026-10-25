// Doctor-side reads that are fetched on demand (not part of the polled state): Ask and the patient Timeline.
import type { OwnAnswers } from "./types";
import { USE_MOCK } from "./index";
import { http } from "./http";
import { mapConsentState, mapOwnAnswers, mapQueryAnswer, mapTimeline, toApiToken, type MappedAnswer, type WireOwnAnswer, type TimelineRow, type WireQueryAnswer, type WireTimeline } from "./mapping";

export const isLive = !USE_MOCK; // not a hook; true when talking to the real API

export async function askServer(question: string): Promise<MappedAnswer> {
  return mapQueryAnswer(await http<WireQueryAnswer>("/query", { method: "POST", body: { question } }));
}

export const suggestionsServer = () => http<string[]>("/query/suggestions");

export async function timelineServer(code: string): Promise<TimelineRow[]> {
  const rows = await http<WireTimeline[]>(`/patients/${toApiToken(code)}/timeline`, { query: { limit: 200 } });
  return rows.map(mapTimeline);
}

/** Consent overview: one state word per person id (Settings). */
export async function consentStatesServer(ids: string[]): Promise<Record<string, "Active" | "Pending" | "Withdrawn">> {
  const out: Record<string, "Active" | "Pending" | "Withdrawn"> = {};
  await Promise.all(ids.map(async (id) => {
    try { out[id] = mapConsentState(await http(`/consents/${id}`)); } catch { /* leave the patient's own consent word */ }
  }));
  return out;
}

/** Patient app: the "About my record" cards. Text is server-rendered in the patient's language; shown as is. */
export async function ownAnswersServer(): Promise<OwnAnswers> {
  return mapOwnAnswers(await http<WireOwnAnswer[]>("/portal/answers"));
}
