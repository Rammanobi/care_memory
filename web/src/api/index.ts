import { httpApi } from "./httpAdapter";
import { mockApi } from "./mockAdapter";
import type { CareApi } from "./types";

/** VITE_USE_MOCK=true (default) uses the in-browser mock; false talks to VITE_API_BASE. The MOCK DATA badge follows this flag. */
export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

export const api: CareApi = USE_MOCK ? mockApi : httpApi;
export * from "./types";
