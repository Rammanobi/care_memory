# CareMemory route contract (`contracts-v1`)

Source of truth: `INTEGRATION_DECISIONS.md` §c (endpoints), §a5 (auth), §d (schemas). There is **no `/v1` prefix**. Every error body is `api.Problem`. Schema names are `module.Class` under `cm/contracts/`. `list[X]` means a JSON array.

**Auth column**
- `jwt:<roles>`: `cm_session` cookie (HttpOnly, Secure, SameSite=Strict) or `Authorization: Bearer`. HS256 with `JWT_SIGNING_KEY`. `tv` is checked against `auth_credentials.token_version`. Cookie mutations need `X-CM-Client: web`.
- `jwt:any` means any authenticated console role.
- `oidc`: Cloud Tasks or Scheduler OIDC token from `cm-tasks-invoker`. Only on `cm-worker`.
- `tg-secret`: the `X-Telegram-Bot-Api-Secret-Token` header.
- `pubsub-oidc`: Pub/Sub push OIDC (SA `cm-pubsub-push`, audience = URL).
- `service`: service token (mock feeds).
- `public`: no auth.
- `DEMO_MODE` and `CM_OFFLINE` gates return 404 when the flag is off.

**Owner** is the lane that writes the route (§e). Lanes: G core API, B console backend, J sim/eval/channels, K mock feeds, N agent logic behind a G route.

**P** is the priority: P0 is built; P1 is built only if time allows.

## Health

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| GET | `/healthz` | none | `api.HealthOut` | public | G | P0 |
| GET | `/readyz` | none | `api.HealthOut` (DB and Store ping) | public | G | P0 |

## Auth

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| POST | `/auth/login` | `admin.LoginIn` | `admin.TokenOut` + `Set-Cookie: cm_session` (rate limit 10/min per IP, 5/min per username) | public | G | P0 |
| GET | `/auth/me` | none | `admin.Me` | jwt:any | G | P0 |
| POST | `/auth/logout` | none | 204 (clears the cookie) | jwt:any | G | P0 |
| POST | `/auth/demo-switch` | `admin.DemoSwitchIn` | `admin.TokenOut` | jwt:admin + DEMO_MODE | G | P1 |

## Webhooks (`cm-api`, always fast-ack)

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| POST | `/webhooks/telegram` | `api.TelegramUpdate` | 200 `api.OkOut` (always 200; dedupe on `tg:{update_id}`) | tg-secret | G (route) / F (handler) | P0 |
| POST | `/webhooks/gmail` | `api.PubSubPush` (data = `api.GmailNotification`) | 204; enqueues `gmail-fetch-{historyId}` | pubsub-oidc | G (route) / M (handler) | P0 |

## Ingest

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| POST | `/ingest/chemist-csv` | multipart CSV (rows parse to `api.ChemistCsvRow`); admin may pass `chemist_id` | `api.IngestReceipt` | jwt:chemist,admin | G (parser K) | P0 |
| POST | `/ingest/lab` | `api.LabResultIn` | `api.IngestReceipt` (fast-path R2) | jwt:lab,admin | G | P0 |
| POST | `/ingest/supporter` | `api.SupporterCheckinIn` | `api.IngestReceipt` | jwt:supporter (assigned patients only) | G (logic F) | P0 |
| POST | `/ingest/household-contact` | `api.HouseholdContactIn` | `api.HouseholdContactOut` | jwt:supporter (assigned), doctor | G (logic F) | P0 |
| POST | `/ingest/portal` | `api.PortalIngestIn` | `api.IngestReceipt` | service | G (parser K) | P0 |
| POST | `/ingest/wearable` | `api.WearableBatchIn` | `api.IngestReceipt` | service | G | P1 |
| POST | `/ingest/lab-report` | multipart PDF or image, stored in GCS `uploads/lab/` | `api.IngestReceipt` (raises `lab_confirm`) | jwt:lab,doctor | G | P1 |

## Worker tasks (`cm-worker`, OIDC only, named Cloud Tasks)

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| POST | `/tasks/run` | `agents.TaskEnvelope` | 200 `agents.TaskResult`; 503 while shutting down | oidc | G | P0 |
| POST | `/tasks/resume` | `agents.ResumeEnvelope` | 200 `agents.TaskResult` | oidc | G | P0 |
| POST | `/tasks/send` | `review.OutboxRef` | 200 `review.SendResult` | oidc | G (router F) | P0 |
| POST | `/tasks/drain-outbox` | `api.DrainOutboxIn` | 200 `list[review.SendResult]` | oidc | G (router F) | P0 |
| POST | `/tasks/checkins` | `api.CheckinsTaskIn` (`slot`: morning, evening or proxy) | 200 `api.IngestReceipt` (rows queued) | oidc | G (logic F) | P0 |
| POST | `/tasks/checkin-nudge` | `api.CheckinNudgeIn` | 200 `review.SendResult` | oidc | G (logic F) | P0 |
| POST | `/tasks/digest` | `api.DigestTaskIn` | 200 `agents.TaskResult` | oidc | G (logic M) | P0 |
| POST | `/tasks/visit-lists` | `api.VisitListsTaskIn` | 200 `agents.TaskResult` | oidc | G (logic F) | P0 |
| POST | `/tasks/gmail-fetch` | `api.GmailFetchIn` | 200 `api.OkOut` | oidc | G (logic M) | P0 |
| POST | `/tasks/gmail-watch-renew` | `api.EmptyTaskIn` | 200 `api.OkOut` | oidc | G (logic M) | P0 |
| POST | `/tasks/gmail-sweep` | `api.EmptyTaskIn` | 200 `api.OkOut` | oidc | G (logic M) | P0 |
| POST | `/tasks/portal-sync` | `api.PortalSyncIn` | 200 `api.IngestReceipt` | oidc | G (logic K) | P0 |
| POST | `/tasks/calendar-sync` | `api.CalendarSyncIn` (P0 covers only `family_screen`) | 200 `api.IngestReceipt` | oidc | G (logic M) | P0 |
| POST | `/tasks/district-report` | `api.DistrictReportTaskIn` | 200 `agents.TaskResult` | oidc | G | P1 |

## Patients and memory

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| GET | `/patients` | `?clinic_id&tier&day&q&cursor&limit` | `api.Page[dashboard.PatientSummary]` | jwt:doctor,admin | G | P0 |
| GET | `/patients/{pid}` | `?day` | `dashboard.PatientDetail` | jwt:doctor,admin | G | P0 |
| GET | `/patients/{pid}/memory` | `?day` (+ P1 `exclude_sources`) | `memory.MemorySnapshot` | jwt:doctor,admin | G | P0 |
| GET | `/patients/{pid}/card` | `?day&audience=doctor\|supporter` | `memory.MemoryCard` | jwt:doctor,admin; supporter gets the approved brief only | G | P0 |
| GET | `/patients/{pid}/lens` | `?day_a=3&day_b=60` | `memory.LensComparison` | jwt:doctor,admin | G | P0 |
| GET | `/patients/{pid}/funnel` | (+ P1 `exclude_sources`) | `memory.FunnelSeries` | jwt:doctor,admin | G | P0 |
| GET | `/patients/{pid}/timeline` | `?from&to&day` | `list[memory.TimelineItem]` | jwt:doctor,admin | G | P0 |
| GET | `/patients/{pid}/series` | `?day` | `dashboard.PatientSeries` | jwt:doctor,admin | G | P0 |
| GET | `/patients/{pid}/belief-pins` | none | `list[memory.BeliefPin]` | jwt:doctor,admin | G | P0 |
| GET | `/patients/{pid}/household` | none | `dashboard.HouseholdSummary` (names only for the treating doctor and the assigned Supporter) | jwt:doctor,supporter,admin | G | P0 |
| GET | `/patients/{pid}/channel-profile` | `?day` | `api.ChannelProfile` | jwt:doctor,admin | G | P0 |
| GET | `/events/{event_id}` | none | `dashboard.EventOut` | jwt:doctor,admin (role-checked) | G | P0 |
| GET | `/beliefs/{belief_id}` | `?day` | `memory.BeliefDetail` | jwt:doctor,admin | G | P0 |
| GET | `/conflicts/{conflict_id}` | none | `memory.ConflictDetail` | jwt:doctor,admin | G | P0 |

## Agent (ad hoc)

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| POST | `/agent/tasks` | `agents.AgentTaskIn` | 202 `agents.TaskAccepted` | jwt:doctor | G (logic E/N) | P1 |
| GET | `/agent/tasks/{task_id}` | none | `agents.TaskStatus` | jwt:doctor | G | P1 |

## Review (doctor gate; every decision goes through `cm/review/decide.py`)

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| GET | `/review/queue` | `?tier&doctor_id&status&kind&patient_id&cursor&limit` | `review.ReviewQueueOut` | jwt:doctor,admin | G | P0 |
| GET | `/review/{approval_id}` | none | `review.ReviewItemDetail` | jwt:doctor,admin | G | P0 |
| POST | `/review/{approval_id}/decision` | `review.ReviewDecisionIn` | `review.ReviewDecisionOut`; 409 `already_decided`, 422 `reason_required` or `banned_term` | jwt:doctor | G | P0 |
| POST | `/review/bulk-decision` | `review.BulkDecisionIn` | `list[review.ReviewDecisionOut]` (per-item `red_not_bulk`, `amber_not_viewed`) | jwt:doctor | G | P0 |
| GET | `/review/metrics` | `?days` | `review.ReviewMetrics` | jwt:doctor,admin | G | P1 |

## Templates

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| GET | `/templates` | `?status&key&lang` | `list[review.Template]` | jwt:doctor,admin | B | P0 |
| POST | `/templates` | `review.TemplateDraftIn` | `review.Template` (draft) | jwt:doctor,admin | B | P0 |
| POST | `/templates/{template_id}/approve` | none | `review.Template` (422 if banned terms are found) | jwt:doctor | B | P0 |
| POST | `/templates/{template_id}/retire` | none | `review.Template` | jwt:doctor,admin | B | P0 |
| GET | `/templates/{template_id}/preview` | `?slots` (JSON) | `review.TemplatePreview` | jwt:doctor,admin | B | P0 |

## Consent and erasure

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| GET | `/consents/{person_id}` | none | `admin.ConsentState` | jwt:doctor,admin; the patient's own via PWA (P1) | B | P0 |
| POST | `/consents` | `admin.ConsentEventIn` | `admin.ConsentEventOut` | jwt:doctor,admin,supporter (`via` = `supporter:S-nn`) | B | P0 |
| POST | `/erasure-requests` | `admin.ErasureRequestIn` | `admin.ErasureRequestOut` (`awaiting_second_approval`) | jwt:doctor,admin | B | P0 |
| GET | `/erasure-requests` | `?status` | `list[admin.ErasureRequestOut]` | jwt:doctor,admin | B | P0 |
| POST | `/erasure-requests/{request_id}/approve` | `admin.ErasureApproveIn` | `admin.ErasureRequestOut` (approver must differ from requester; DB CHECK) | jwt:doctor,admin | B | P0 |

## Dashboards

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| GET | `/dashboard/clinic/{clinic_id}/summary` | `?day` | `dashboard.ClinicSummary` | jwt:doctor,admin | B | P0 |
| GET | `/dashboard/district/{district_id}/summary` | `?day` | `dashboard.DistrictSummary` | jwt:sts,dto,admin | B | P0 |
| GET | `/dashboard/district/{district_id}/blocks` | `?day` | `list[dashboard.BlockRow]` | jwt:sts,dto,admin | B | P0 |
| GET | `/dashboard/district/{district_id}/trends` | `?metric&days` | `dashboard.TrendSeries` | jwt:sts,dto,admin | B | P0 |
| GET | `/dashboard/district/{district_id}/payments-stuck` | `?day` | `list[dashboard.PaymentStuckRow]` | jwt:sts,dto,admin | B | P0 |
| GET | `/dashboard/district/{district_id}/cascade` | `?day` | `list[dashboard.CascadeStage]` | jwt:sts,dto,admin | B | P1 |
| GET | `/dashboard/district/{district_id}/pharmacies` | `?day&window=30` | `list[dashboard.PharmacyRow]` | jwt:sts,dto,admin | B | P1 |
| GET | `/dashboard/district/{district_id}/supporters` | `?day&window=7` | `list[dashboard.SupporterActivityRow]` | jwt:sts,dto,admin | B | P1 |
| GET | `/dashboard/district/{district_id}/report` | `?month=YYYY-MM&format=json\|csv` | `dashboard.MonthlyReport` or `application/zip` | jwt:sts,dto,admin | B | P1 |
| POST | `/dashboard/district/{district_id}/reveal` | `dashboard.RevealIn` | `dashboard.RevealOut` (audited) | jwt:dto | B | P1 |

## Supporter

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| GET | `/supporter/{sid}/visit-list` | `?date` | `api.VisitList` (approved only) | jwt:supporter (self), admin | G | P0 |

## Dashboard Q&A (runs inline in `cm-api`, 25 s budget)

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| POST | `/query` | `agents.QueryIn` | `agents.QueryAnswer` | jwt:doctor,sts,dto,admin | G (route) / N (agent) | P1 |
| GET | `/query/suggestions` | none | `list[str]` | jwt:any | G | P1 |

## Realtime

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| GET | `/stream` | `?topics=review,tasks,sim,channels`, `Last-Event-ID` | `text/event-stream` of `api.LiveEvent` (ids only; 50 s rotation) | jwt:any (role and scope filtered) | G | P0 (cut #6) |

## Sim (demo)

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| POST | `/sim/reset` | `?seed&patients&days` (no params restores demo seed 42) | 202 `evalsim.SimRunOut` | jwt:admin | J | P0 |
| POST | `/sim/advance` | `?to_day&mode=fast\|full` | `evalsim.SimAdvanceOut` (full on GCP: 202 + `task_id`; going backwards: 409) | jwt:admin,doctor | J | P0 |
| GET | `/sim/clock` | none | `evalsim.SimClock` | jwt:any | J | P0 |
| POST | `/sim/escalation-offset` | `evalsim.EscalationOffsetIn` | `evalsim.SimClock` | jwt:admin + DEMO_MODE | J | P0 |
| POST | `/sim/sweep-now` | none | 202 `api.TaskRef` | jwt:admin + DEMO_MODE | J | P0 |
| GET | `/sim/inbox` | `?persona&after` | `list[evalsim.SimInboxItem]` | jwt:any + CM_OFFLINE | J | P0 |
| POST | `/sim/inbox/{persona}/reply` | `evalsim.SimReplyIn` | `evalsim.SimInboxItem` | jwt:any + CM_OFFLINE | J | P0 |
| POST | `/sim/inject` | `evalsim.SimInjectIn` | 202 `api.TaskRef` | jwt:admin + DEMO_MODE | J | P1 |

## Eval and ops

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| GET | `/eval` | `?seed` (seed must be 42 or at least 2000, otherwise 422) | 200 `evalsim.EvalReport`, or 202 + `Location: /eval/runs/{run_id}` after 45 s | jwt:any | J | P0 |
| GET | `/eval/runs/{run_id}` | none | `evalsim.EvalRunStatus` | jwt:any | J | P0 |
| GET | `/task-runs/{task_id}` | none | `evalsim.TaskRunStatus` | jwt:any | J | P0 |
| GET | `/channels` | none | `list[evalsim.ChannelStatus]` | jwt:admin,doctor | J | P0 (cut #1) |
| POST | `/channels/{channel}` | `evalsim.ChannelToggleIn` | `evalsim.ChannelStatus` | jwt:admin | J | P0 (cut #1) |

## Admin

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| GET | `/admin/persons` | `?role&clinic_id&cursor` | `api.Page[admin.PersonAdminOut]` | jwt:admin | B | P0 |
| POST | `/admin/persons` | `admin.PersonAdminIn` | `admin.PersonAdminOut` | jwt:admin | B | P0 |
| PATCH | `/admin/persons/{person_id}` | `admin.PersonAdminPatch` (bumps `token_version` when the role changes or the person is deactivated) | `admin.PersonAdminOut` | jwt:admin | B | P0 |
| GET | `/admin/settings` | none | `admin.SettingsOut` | jwt:admin,doctor | B | P0 |
| PUT | `/admin/settings` | `admin.SettingsIn` (409 on a version mismatch) | `admin.SettingsOut` | jwt:admin | B | P0 (editor UI P1) |
| GET | `/admin/audit` | `?actor&action&patient_id&from&to&cursor&format=csv` | `api.Page[admin.AuditEntry]` | jwt:admin | B | P1 |

## Mock Ni-kshay portal

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| GET | `/mock/nikshay/patients/{nikshay_id}` | none | `api.MockNikshayPatient` | service | K | P0 |
| GET | `/mock/nikshay/payments` | `?since&nikshay_id` | `list[api.MockNikshayPayment]` | service | K | P0 |
| POST | `/mock/nikshay/scenario` | `api.MockScenarioIn` | `api.OkOut` | jwt:admin | K | P0 |

## Identity (P1)

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| POST | `/identity/resolve` | `agents.IdentityQuery` | `agents.IdentityMatch` | jwt:admin | G | P1 |
| GET | `/identity/unmatched` | `?source&cursor` | `api.Page[agents.IdentityQuery]` | jwt:admin | G | P1 |

## Patient PWA (P1, magic link, role `patient`)

| Method | Path | Request | Response | Auth | Owner | P |
|---|---|---|---|---|---|---|
| POST | `/pwa/session` | `api.MagicLinkExchangeIn` | `admin.TokenOut` | public (single-use token) | G | P1 |
| GET | `/pwa/inbox` | none | `api.PwaInbox` | jwt:patient | G | P1 |
| POST | `/pwa/checkins` | `api.PwaCheckinIn` | `api.IngestReceipt` | jwt:patient | G | P1 |
| POST | `/pwa/symptoms` | `api.PwaSymptomsIn` | `api.IngestReceipt` | jwt:patient | G | P1 |
| POST | `/pwa/monthly` | `api.PwaMonthlyIn` | `api.IngestReceipt` | jwt:patient | G | P1 |
| POST | `/pwa/push-subscriptions` | `api.PushSubscriptionIn` | 204 | jwt:patient | G | P1 |
| DELETE | `/pwa/push-subscriptions` | `api.PushSubscriptionIn` | 204 | jwt:patient | G | P1 |

## Counts

- **105 routes** in total: **80 P0** and **25 P1**.
- Rejected routes, which must not be built: `/v1/*`, `/sim/reset-demo`, `/tasks/escalate`, eval polling through `/task-runs/{id}`, and `/review/{review_id}`.
