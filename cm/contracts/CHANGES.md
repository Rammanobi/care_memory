# Contract change requests (append only)

## RFC-S1 (backend slice 1, lane G/B): models and routes the frozen contracts do not cover

Status: implemented additively in `cm/api/portal_models.py` and `cm/api/routers/*`. No file in `cm/contracts/` was edited.

Why: the finished React UI needs patient self-service, UI-shaped patient rows (the memory engine tables
`features_daily`, `beliefs`, `risk_scores` are not populated in this slice), evidence by UI id (E-0412),
notes, messages, patient requests and the usage panel. Contract models used as-is: `api.Problem`, `api.Page`,
`api.HealthOut`, `admin.{LoginIn,TokenOut,Me,SettingsOut,SettingsIn,ConsentState}`, `review.{ReviewQueueOut,
ReviewItem,ReviewItemDetail,ReviewDecisionIn,ReviewDecisionOut,BulkDecisionIn,Template}`,
`dashboard.ClinicSummary`, `agents.{QueryIn,QueryAnswer}`.

Additions (proposal for the next contract version):
1. `GET /patients` and `GET /patients/{pid}` return slice models `UiPatient` / `PatientDetailOut` instead of
   `dashboard.PatientSummary` / `PatientDetail` (they need `RiskScore`, `MemoryCard` from the engine).
   Per-patient UI fields (sex, age, base colour, why, missed, next step, changes) are read from a latest
   `ContextNote{kind:'summary'}` event until the engine owns them.
2. Patient requests are `approvals` rows with `payload.subkind = 'patient_request'` (kind `needs_human`),
   decided through `decide()`. Routes: `GET /requests`, `GET /requests/{id}`, `POST /requests/{id}/decision`.
   They are excluded from `GET /review/queue`.
3. New routes: `/clinics`, `/dashboard/tiles`, `/evidence`, `/evidence/{ref}`, `/notes`,
   `/patients/{pid}/notes`, `/patients/{pid}/timeline` (slice model), `/lens`, `/messages`,
   `/admin/usage`, `/admin/demo/usage-mode`, `/admin/demo/sim-day` (DEMO_MODE, admin),
   `/admin/audit` (UI-shaped rows, doctor+admin).
4. Patient/Supporter app (`/portal/*`, roles patient and supporter): `me`, `today`, `dose`, `record`,
   `inbox`, `messages/{id}/read`, `requests`, `reminder-request`, `consents` (GET/PUT),
   `supporter/checkin`, `supporter/mark-taken`, `supporter/ask`. The contract lists these only as P1 `/pwa/*`
   magic-link routes; slice 1 uses normal username/password login for role `patient`.
5. `ReviewDecisionIn` on a Red/Amber reject requires `reason` (422 `reason_required`): UI "decline" buttons must send one.
6. PII vault: `identity_vault.enc_*` hold plain UTF-8 of fictional values in this slice (no AES-GCM yet).

## RFC-S2 (backend gaps 1, lane G/B): routes added after RFC-S1

Status: implemented additively in `cm/api/*`, migration `0008_event_stream.sql`. No frozen file edited.
New routes (to be added to `openapi_routes.md` in the next contract version):
- `DELETE /portal/dose` (patient): compensating `DoseCheckin` with `payload.status='undone'` that supersedes today's mark. Append-only; idempotent. Returns `PortalToday`. Readers of `DoseCheckin` outside the API must treat `undone` as "no dose recorded".
- `GET /portal/documents` (patient): `list[PortalDocument{id,title,kind,date,summary}]` from `ContextNote{kind:'document'}`.
- `GET /portal/medicines` (patient): `list[PortalMedicine{id,label,when,note}]` from `ContextNote{kind:'medicine'}`; plain language, no drug names.
- `GET /stream?topics=review,channels` (any signed-in role, cookie or bearer): SSE. SSE event name = topic (`review`: approval_created, approval_decided, request_created; `channels`: message_sent); data JSON `{type, topic, ref, patient_id}`. Heartbeat comment `: ping` every 15 s. Patients/Supporters receive only events about themselves.
- `GET /dashboard/district?clinic=` (doctor, admin): `DistrictOut` with `small_cell_threshold` (5); counts 1..4 returned as null and listed in `suppressed`.
Changed shapes (additive fields):
- `UiPatient.person_id`; `MessageOut.delivery` (`queued|sent|failed`, from the outbox row) and `delivery_error`.
- `POST /review/bulk-decision` returns `list[BulkItemResult]` = `ReviewDecisionOut` + `ok`, `message`; `error_code` is open (any decision code). HTTP 200 on partial success.
Migration `0008`: trigger function `cm.notify_event()` publishes ids (no text) on Postgres channel `cm_events`.

## RFC-Q1 (lane G, Ask box + patient RAG): optional patient code in `QueryIn`
Why: the doctor on a patient page should be able to ask "when did she miss doses?" without typing the code. `QueryIn` has `extra="forbid"` and no patient field, so today only a `PT-xxxx` written in the question targets one patient.
Proposal (additive): `QueryIn.patient_code: str | None = Field(default=None, pattern=r"^PT-\d{4}$")`. The server uses it only to choose which patient's record to search; it is checked against the doctor's patient list and never forwarded to a model (the patient token is injected server-side). No change to `QueryAnswer`: citations already travel in `tool_calls_used[].result_preview` as `{ref, date, kind, snippet}` rows of the `search_patient_memory` call. Status: not implemented; the router change is a three-line follow-up once L0 approves.
