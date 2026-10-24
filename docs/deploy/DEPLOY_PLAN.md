# CareMemory deploy plan: Cloud Run (asia-south1), one domain, several hostnames

Status: plan only, written 2026-10-25 from a read-only review of the repo. No Google Cloud call was made.
Owning lane: I (Infra). Code gaps are routed to their lanes in section 3. OpenSpec: `add-gcp-cloud-run-deploy`.
Placeholders: `<domain>` = the owner's domain, `<project>` = GCP project id (repo default `caremem-hack`).

---

## 1. Architecture

### 1.1 Recommended shape

```
 doctor.<domain>  patient.<domain>  family.<domain>  demo.<domain>  <domain> (apex)
        \               |                |               |            /
         +-------- DNS A records -> ONE global static IP --------------+
                                   |
             Global external Application Load Balancer (EXTERNAL_MANAGED)
             - Google-managed certificate, one cert listing every hostname
             - HTTP :80 -> HTTPS redirect
             - URL map: every host -> backend cm-api-be (optional "/" redirect per host)
                                   |
                 Serverless NEG (asia-south1) -> Cloud Run service cm-api
                 (one container: FastAPI API + the built web app from web/dist)
                                   |
   Cloud SQL cm-pg (PG16 + pgvector)   Cloud Tasks / Scheduler -> cm-worker (private, OIDC)
   Secret Manager                      Cloud Run Jobs: cm-migrate, cm-seed (others later)
```

### 1.2 Load balancer vs Cloud Run domain mappings

| Option | asia-south1 | Certs | Cost | Verdict |
|---|---|---|---|---|
| Cloud Run domain mapping (`gcloud beta run domain-mappings`) | Not in the documented list of supported regions for domain mapping (preview); verify, but do not plan on it | Auto, per mapping | Free | Rejected: region, preview status, slow cert issue, no per-host routing |
| **Global external Application LB + serverless NEG** | Yes (NEG is regional, LB is global) | Google-managed classic cert, up to 100 names, no wildcard | About USD 0.60/day for one forwarding rule (+ HTTP rule) | **Chosen** |
| Firebase Hosting rewrite to Cloud Run | Works | Free, per custom domain | Free tier | Fallback only: 60 s request cap breaks SSE `/stream`, adds a second product |

Certificate: create one `gcloud compute ssl-certificates create cm-cert --global --domains=<all hosts>`.
It goes ACTIVE only after every listed name resolves to the LB IP; this takes 15 to 60 min and can take
hours. **So the LB, IP and DNS go in first thing in the morning**, before the app is ready (see the
placeholder trick in 2.2). If one host never validates, the whole cert stays PROVISIONING, so list only
hosts whose DNS you will add now. Adding a host later = create a second cert and attach both to the proxy.

### 1.3 DNS records the owner must add (at the registrar or DNS host)

| Type | Name | Value | TTL |
|---|---|---|---|
| A | `@` (apex `<domain>`) | LB static IP `cm-ip` | 300 |
| A | `doctor` | same IP | 300 |
| A | `patient` | same IP | 300 |
| A | `family` (Supporter app) | same IP | 300 |
| A | `demo` (judges' entry: doctor console with demo admin) | same IP | 300 |

Use A records, not CNAME, for all (the apex cannot be a CNAME anyway). Remove any existing AAAA or
parking records on those names, or the cert check can fail. No CAA record, or one that allows `pki.goog`.
Names are a suggestion; any set works, but the cert must list exactly the names you add.

### 1.4 One container serves API + web

- Dockerfile stage 1 builds `web/` (Vite), stage 2 copies `web/dist` into the Python image. **Today
  `cm/api/main.py` does not serve `web/dist`** (no StaticFiles, no SPA fallback): gap G3.
- Required mount order in `create_app()`: API routers first (unchanged paths: `/auth`, `/patients`,
  `/review`, `/portal`, `/stream`, `/webhooks`, `/tasks`, ...), then `StaticFiles` at `/assets`, then a
  GET catch-all that returns `index.html` only for SPA paths (`/`, `/doctor/*`, `/patient/*`,
  `/supporter/*`). The SPA areas `/doctor`, `/patient`, `/supporter` do not collide with any API prefix
  (checked: API uses `/admin`, `/patients`, `/portal/supporter/...`, never bare `/doctor` or `/patient`).
- Web build flags: `web/src/api/http.ts` already supports `VITE_API_BASE=""` (same origin, resolved
  against `location.origin`), so one build works on every hostname. The image MUST be built with
  `VITE_USE_MOCK=false` and `VITE_API_BASE=""`; today the Dockerfile sets neither, so the image would ship
  the in-browser mock with a `localhost:8080` API (gap G2).

### 1.5 Host-based routing (same app, different names)

Each hostname shows the same SPA; the name only picks the landing area:
`doctor.` -> `/doctor`, `patient.` -> `/patient`, `family.` -> `/supporter`, `demo.` -> `/doctor`,
apex -> `/` (login chooser). Two ways, pick one:

- **A (zero code, recommended for tomorrow):** LB URL map with one `hostRule` per name and a `routeRule`
  matching `fullPathMatch: /` that does `urlRedirect.pathRedirect: /doctor` (etc.); every other path goes to
  `cm-api-be`. Imported with `gcloud compute url-maps import cm-urlmap --source=infra/lb/urlmap.yaml --global`.
- **B (app):** a small middleware in `cm/api` reading `Host` and redirecting `/` (lane G). Testable locally,
  but it is code and needs a host allowlist anyway.

Host validation: add Starlette `TrustedHostMiddleware` with the hostname list plus the `*.run.app` URL
(lane G, part of G3). Cloud Run receives the original `Host` header from the LB.

### 1.6 Cookies, SameSite, CORS, CSRF across subdomains

- Login sets `cm_session` with `HttpOnly`, `SameSite=Strict`, `Secure=COOKIE_SECURE`, `path=/` and **no
  `Domain`** (`cm/api/routers/auth.py`). Keep it host-only: each hostname has its own session, so a
  doctor tab on `doctor.` and a patient tab on `patient.` can be signed in at once in one browser (good for
  the demo) and a patient cookie is never sent to the doctor host. Do **not** set `Domain=.<domain>`:
  sibling subdomains count as same-site, so `SameSite=Strict` would no longer isolate them.
- `COOKIE_SECURE` defaults to off and is **missing from `infra/env/api.env.yaml`**: add `COOKIE_SECURE: "1"`.
- CORS: the web calls the API on its own origin, so CORS is not exercised. Set
  `CORS_ORIGINS` to the exact `https://` hostnames (not `*`, credentials are allowed). Also missing from
  `api.env.yaml` today (defaults to `http://localhost:5173`, harmless but wrong).
- CSRF: cookie mutations already require `X-CM-Client: web` (`cm/api/deps.py`). A custom header forces a
  CORS preflight from any other origin, and the preflight fails for origins outside `CORS_ORIGINS`, so this
  plus `SameSite=Strict` is enough. Keep it.
- SSE `/stream`: cm-api has `--timeout=60`, so Cloud Run cuts each stream at 60 s and `EventSource`
  reconnects. Acceptable; or raise cm-api `--timeout` to 3600 (the serverless NEG uses Cloud Run's timeout).

### 1.7 Ingress

Hackathon setting: cm-api ingress `all` (run.app URL stays usable for webhooks and as a fallback if the
cert is late). Later: `--ingress=internal-and-cloud-load-balancing` once Telegram and Pub/Sub point at the
domain. cm-worker stays `--no-allow-unauthenticated` (OIDC only).

---

## 2. Runbook: numbered infra scripts, in order

Run from `caremem/` in Git Bash or Cloud Shell, after `gcloud auth login` and
`gcloud config set project <project>`. Export `PROJECT` and `REGION=asia-south1` first; `vars.sh` reads them.

### 2.0 Before anything: edits to make (infra lane, no gcloud needed)

1. `infra/env/*.env.yaml`: replace `<flagship-model>` / `<vision-model>` placeholders; set `GCP_PROJECT`,
   bucket and instance names if the project id is not `caremem-hack`; add `COOKIE_SECURE`, `CORS_ORIGINS`,
   `PUBLIC_BASE_URL=https://<domain>`; change DB settings per G4 (`DB_HOST=/cloudsql/<instance>`,
   `DB_USER=cm_app`); set `TASKS_MODE` per G5; `LANGSMITH_TRACING: "false"` unless a key exists.
2. `infra/60_deploy.sh`: map passwords to the name the code reads, e.g. `DB_PASSWORD=DB_PASSWORD_APP:latest`
   (api/worker) and `DB_PASSWORD=DB_PASSWORD_ADMIN:latest` with `DB_USER=cm_admin` (jobs); drop secrets from
   `--set-secrets` that will have no value (any secret with zero versions fails the deploy); trim the job
   list to `cm-migrate` and `cm-seed` until the others run (G15).
3. `infra/70_scheduler.sh`: keep only the check-in jobs and add a drain-outbox job (G9); comment out
   `sched-sweeper`, `sched-nightly`, portal-sync, digest, visit-lists, gmail-renew, gmail-sweep (routes or
   code do not exist yet, so they would 404 or crash every run).
4. `infra/80_webhooks.sh`: skip the Gmail push subscription until `/webhooks/gmail` exists (G7); use the
   domain, not the run.app URL, for `PUBLIC_BASE_URL` once the cert is ACTIVE.
5. `infra/cloudbuild.yaml`: project id is hard-coded; for the first deploy build manually (2.2 step 6).
6. New `infra/85_lb.sh` (+ `infra/lb/urlmap.yaml`): IP, NEG, backend, URL map, cert, proxies, rules (G17).
7. `00_project.sh` does not enable `compute.googleapis.com` (needed for the LB); add it.

### 2.1 Order and what each script needs

| # | Script | Needs | Does | Risks / notes |
|---|---|---|---|---|
| 1 | `00_project.sh` | project exists, billing linked, Owner role | enables APIs, Artifact Registry `cm`, bucket `<project>-cm-docs` | add `compute.googleapis.com`; bucket names are global, fails if taken |
| 2 | `85_lb.sh` (new) | 1; a placeholder `cm-api` (see 2.2) | static IP, NEG, LB, cert | **start early**: cert waits on DNS |
| 3 | owner adds DNS | IP from step 2 | A records (1.3) | registrar access; TTL 300 |
| 4 | `10_iam.sh` | 1 | 6 service accounts + roles | Pub/Sub service agent may not exist yet: prints WARN, rerun after 40 |
| 5 | `30_secrets.sh` | 4 | creates 14 secrets, generates random ones, per-secret grants | then the owner adds external values (stdin only, never on the command line); `DEMO_USER_PASSWORDS` must be the JSON the seed expects |
| 6 | `20_sql.sh` | 5 (DB passwords) | Cloud SQL PG16 Enterprise `db-custom-1-3840`, db `caremem`, 4 users | 10 to 15 min to create; users made by gcloud join `cloudsqlsuperuser` (broad rights; accept for hackathon) |
| 7 | `40_pubsub.sh` | 1 | topics `gmail-push`, `dead-letter` | harmless even if Gmail stays off |
| 8 | `50_tasks.sh` | 1 | queues `agent-runs`, `resumes`, `outbound` | none |
| 9 | build + push image | G1, G2 fixed | `docker build` / `gcloud builds submit --tag $AR/cm:<tag>` | Dockerfile COPY of missing dirs fails today |
| 10 | `60_deploy.sh` | 5, 6, 8, 9 | cm-worker, cm-api, jobs, resource IAM | secrets without versions fail; `min-instances=1` on cm-api costs money (section 4) |
| 11 | `80_webhooks.sh` | 10 | runs `cm-migrate`, Telegram setWebhook, health check | stop any laptop `tg_poll` first (it calls deleteWebhook); skip Gmail sub |
| 12 | seed | 11 | `gcloud run jobs execute cm-seed --wait` | needs G13; then index RAG once |
| 13 | `70_scheduler.sh` | 10, G6 | check-ins + drain-outbox | pause wall-clock jobs on stage |
| 14 | `75_observability.sh` | none | no-op today (no YAML) | skip |
| 15 | `infra/tests/smoke.sh` + section 6 | all | checks | none |

### 2.2 Morning sequence (clock order)

1. `00_project.sh` (with compute API).
2. `gcloud run deploy cm-api --image=us-docker.pkg.dev/cloudrun/container/hello --region=asia-south1 --allow-unauthenticated`
   (placeholder so the NEG has a service; the real deploy replaces it).
3. `85_lb.sh` -> note the IP -> owner adds the DNS records -> cert starts provisioning in the background.
4. `10_iam.sh`, `30_secrets.sh`, owner adds secret values, `20_sql.sh` (wait), `40_pubsub.sh`, `50_tasks.sh`.
5. Meanwhile the code lanes land G1 to G6.
6. Build and push the image; `60_deploy.sh`; `80_webhooks.sh` (migrate, Telegram on the run.app URL first).
7. Seed, scheduler, smoke test. When the cert is ACTIVE, re-run setWebhook with `https://<domain>`.

---

## 3. Gap list: code that blocks the cloud

Size: S under 1 h, M 1 to 3 h, L more. "Blocker" = deploy fails or the demo breaks without it.

| ID | Gap (evidence) | Fix | Lane | Size | Blocker |
|---|---|---|---|---|---|
| G1 | No `cm/__main__.py`; Dockerfile `ENTRYPOINT ["python","-m","cm"]` cannot start | `cm/__main__.py`: `CM_ROLE=api\|worker` -> uvicorn `cm.api.main:app` on `$PORT`; `CM_ROLE=job` -> run `cm.jobs.<CM_JOB>` | L0 (or I by ruling) | S | Yes |
| G2 | Dockerfile copies `models/`, `fixtures/cassettes`, `fixtures/eval` (none exist); web built without `VITE_USE_MOCK=false` / `VITE_API_BASE=""`; uv tag unpinned | drop or guard the COPYs; `ENV VITE_USE_MOCK=false VITE_API_BASE=` in the web stage; pin uv | I | S | Yes |
| G3 | `cm/api/main.py` does not serve `web/dist`; no host allowlist; no per-host landing | StaticFiles + SPA fallback (1.4), TrustedHostMiddleware, optional host redirect (1.5 B). Planned change `add-production-image` | G | M | Yes |
| G4 | `Settings` reads only `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD`; env YAMLs set `DB_CONNECT_MODE`, `CLOUD_SQL_INSTANCE`, `DB_USER_APP`, `DB_PASSWORD_APP` which no code reads | infra-only: `DB_HOST=/cloudsql/<project>:asia-south1:cm-pg`, `DB_USER=cm_app`, secret mapped as `DB_PASSWORD` (jobs: `cm_admin` / `DB_PASSWORD_ADMIN`) | I | S | Yes |
| G5 | `cm/core/tasks.py`: `TASKS_MODE=cloud` raises `NotImplementedError` on every enqueue | real Cloud Tasks client (name = task_id, OIDC to cm-worker). Interim for tomorrow: `TASKS_MODE=local` on cm-api with `--no-cpu-throttling` and `min-instances=1` (in-process thread; breaks non-negotiable 8, so demo only). Planned change `add-cloud-tasks-mode` | A | M | Yes (or interim) |
| G6 | `/tasks/*` guard answers 501 in cloud mode and otherwise wants an admin JWT; Scheduler/Tasks send a Google OIDC token | verify bearer with `google.oauth2.id_token` (audience = worker URL, email = `cm-tasks-invoker`) | G | S-M | Yes for scheduler |
| G7 | No `/webhooks/gmail` route (only `cm/channels/gmail_oidc.py` exists); no gmail-watch-renew / gmail-sweep task routes | wire route + tasks; until then skip the push subscription (else Pub/Sub retries to DLQ) | M + G | M | No (Gmail = P1 tomorrow) |
| G8 | Telegram on laptop uses `cm.jobs.tg_poll` (long polling); Cloud Run cannot poll (scale to zero) | webhook route already verifies the secret header; set `PUBLIC_BASE_URL`, run setWebhook (80_webhooks). Never run tg_poll against the same bot after that (it deletes the webhook). Telegram needs a valid cert: use run.app until the LB cert is ACTIVE | F + I | S | Yes for Telegram |
| G9 | Outbox drainer has no cloud trigger (local loop or `/tasks/drain-outbox` only) | Scheduler `* * * * *` -> worker `/tasks/drain-outbox` with OIDC (after G6); or enqueue a drain task on outbox write | I + G | S | Yes for sends |
| G10 | Migrations job: needs G1 + admin creds (G4); `0001` runs `CREATE EXTENSION vector`, `pgcrypto` | run as `cm_admin` (cloudsqlsuperuser member, allowed on Cloud SQL); `0007` skips CREATE ROLE when gcloud already made the users. Take an on-demand backup before each run | A + I | S | Yes |
| G11 | Secrets: `60_deploy.sh` mounts LangSmith, DeepSeek, Gmail, Telegram, demo passwords; any secret without a version fails the deploy. `cm/jobs/seed.py` writes generated passwords into `.env` when `DEMO_USER_PASSWORDS` is missing (wrong in cloud) | owner adds values or the lists are trimmed; pre-fill `DEMO_USER_PASSWORDS`; model placeholders in env YAMLs | I + owner | S | Yes |
| G12 | `CM_DATA_CLASS`: env YAMLs say `mock`, code default is `synthetic`; `real` refuses DeepSeek and images | keep `mock` (or `synthetic`) for the demo; never `real` on this build; check `admin.py:244` accepts it (it does) | I | S | No |
| G13 | Demo seed on Cloud SQL: `cm-seed` job needs G1, G4 (admin user), pgvector >= 0.7 (Cloud SQL PG16 ships 0.8.x); RAG index (`cm.jobs.rag_index --all`) is not a deployed job | run seed job; add a one-off `cm-rag-index` job or run with `--args` override; needs `OPENAI_API_KEY` | B + K + I | S-M | Yes for demo data |
| G14 | Quiet hours (21:00-07:00 IST) override only works when `CM_ENV=dev`; cloud sets `CM_ENV=demo` (`cm/router/quiet_hours.py:15`) | accept `CM_ENV in {dev, demo}` with `DEMO_IGNORE_QUIET_HOURS=1`; set it only for the demo window | F | S | Only if demoing after 21:00 |
| G15 | `cm/jobs/sweeper.py` raises `NotImplementedError`; `cm-nightly` needs `--patient`; scheduler targets 6 routes that do not exist | do not create those jobs/schedules tomorrow | E + I | S | No (if skipped) |
| G16 | `infra/85_lb.sh` and `infra/lb/urlmap.yaml` do not exist | write them (1.2, 1.5 A) | I | M | Yes for the domain |
| G17 | cm-api `--timeout=60` cuts SSE every minute | raise to 3600 or accept reconnects | I | S | No |

---

## 4. Cost per day (asia-south1, approximate, verify in the pricing calculator)

| Item | Setting | USD/day | INR/day (about 88/USD) |
|---|---|---|---|
| Cloud SQL Enterprise `db-custom-1-3840` + 10 GB SSD | always on | 2.2 to 2.6 | 195 to 230 |
| LB forwarding rules (HTTPS + HTTP redirect) | always on | 0.6 to 1.2 | 55 to 105 |
| cm-api min 1 instance, 2 vCPU / 2 GiB, idle | `min-instances=1` | 1.0 to 1.5 (more with `--no-cpu-throttling`: about 4 to 5) | 90 to 130 (350 to 440) |
| cm-worker, jobs | scale to zero | under 0.2 at demo traffic | under 20 |
| Tasks, Scheduler, Pub/Sub, Secret Manager, Artifact Registry, Logging | low volume | under 0.2 | under 20 |
| LLM providers (OpenAI / DeepSeek) | outside GCP, capped by `CM_BUDGET_DAILY_USD` | per cap | per cap |
| **Total GCP** | | **about 4 to 6** (8 with the interim always-on CPU) | **about 350 to 700** |

Scale to minimum:
- After the demo: `gcloud run services update cm-api --min-instances=0` (cold start 3 to 8 s).
- Stop the DB overnight: `gcloud sql instances patch cm-pg --activation-policy=NEVER` (storage still billed),
  restart with `ALWAYS` (2 to 5 min).
- Cheaper DB for idle days: `db-g1-small` (shared core) is about a third of the price; no SLA, fewer connections.
- After the event: delete forwarding rules and the static IP (an unattached reserved IP is still billed).
- Pause schedulers: `gcloud scheduler jobs pause <name> --location=asia-south1`.

Budget alerts (owner, console Billing > Budgets & alerts, or `gcloud billing budgets create` with the
billing account id): budget INR 5,000 for the project, alert thresholds 40% (INR 2,000), 90%, 100%, email
to the owner. A budget only alerts, it never stops spend; the stop switches are the commands above.

---

## 5. Inputs needed from the owner (names only, never paste values into chat)

- [ ] GCP project id (default in repo `caremem-hack`; every env YAML and `cloudbuild.yaml` hard-codes it)
- [ ] Region confirmed: `asia-south1`
- [ ] Billing account linked (done, Blaze) and the billing account id for the budget
- [ ] `gcloud auth login` done on the machine that runs the scripts, as a project Owner (or Cloud Shell)
- [ ] Docker available locally, or OK to use Cloud Build (`gcloud builds submit`)
- [ ] Domain name `<domain>` and the final hostname list (suggested: apex, doctor, patient, family, demo)
- [ ] Registrar / DNS host access, and who adds the A records (and how fast)
- [ ] Secret values to load into Secret Manager by the owner, via stdin: `OPENAI_API_KEY`,
      `DEEPSEEK_API_KEY`, `TELEGRAM_BOT_TOKEN`, optional `LANGSMITH_API_KEY`, `DEMO_USER_PASSWORDS`
      (generated ones: `JWT_SIGNING_KEY`, `PII_MASTER_KEY`, `TELEGRAM_WEBHOOK_SECRET`, `DB_PASSWORD_*` are made by `30_secrets.sh`)
- [ ] Which Telegram bot is the cloud bot (one bot = one webhook; keep a separate dev bot for the laptop)
- [ ] Model names for `ORCHESTRATOR_MODEL`, `VISION_MODEL` (placeholders in env YAMLs)
- [ ] Gmail (P1): OAuth client JSON file path (Desktop client) for `scripts/gmail_auth.py`, the mailbox
      address (`GMAIL_MAILBOX`), doctor allowlist (`DOCTOR_EMAIL_ALLOWLIST`), calendar id; resulting
      `GMAIL_OAUTH_CLIENT_JSON` and `GMAIL_REFRESH_TOKEN` go to Secret Manager
- [ ] Decision: interim `TASKS_MODE=local` on cm-api (fast, costs more) vs wait for `add-cloud-tasks-mode`
- [ ] Decision: demo window time (quiet hours G14, min-instances, scheduler pause)

---

## 6. Smoke test after deploy (10 steps) and rollback

1. `bash infra/tests/smoke.sh`: cm-api `/healthz` ok, cm-worker answers 401/403 anonymously, 3 queues and the jobs exist.
2. `curl -fsS https://<run.app>/readyz` returns `{"status":"ok","db":true}` (Cloud SQL socket + password mapping work).
3. `gcloud compute ssl-certificates describe cm-cert --global` shows ACTIVE for every name; `curl -I http://doctor.<domain>` gives 301 to https.
4. `https://doctor.<domain>/` lands on `/doctor` (or login); `patient.` -> `/patient`; `family.` -> `/supporter`; a deep link reload (`/doctor/approvals`) returns the SPA, not 404.
5. Browser devtools: no MOCK DATA badge; API calls go to the same origin; `cm_session` is `Secure`, `HttpOnly`, `SameSite=Strict`, no `Domain`.
6. Sign in as the demo doctor on `doctor.` and as a demo patient on `patient.` in the same browser: both stay signed in (host-only cookies).
7. A POST without `X-CM-Client: web` using the cookie gets 403 `csrf`; a request with an unlisted `Host` gets 400 (after G3).
8. Telegram: `getWebhookInfo` (via `scripts/set_telegram_webhook.sh --dry-run` for the target, then the Bot API from the owner's shell) shows the domain URL and no last error; send `/start` to the bot and get the reply; check `cm-api` logs show `update_id` only.
9. Trigger a reminder: run the check-in scheduler job once (`gcloud scheduler jobs run sched-checkins --location=asia-south1`), then the drain job; the Telegram message arrives and the outbox row is `sent`.
10. Doctor flow: approve one card in the review queue, see it leave the queue and the SSE update arrive; `gcloud logging read` shows no ERROR from cm-api/cm-worker in the last 10 min.

Rollback:
- App: `gcloud run revisions list --service=cm-api` then `gcloud run services update-traffic cm-api --to-revisions=<previous>=100` (same for cm-worker). Deploy with `--no-traffic` + tag for risky changes.
- Database: `gcloud sql backups create --instance=cm-pg` before every migrate; restore with `gcloud sql backups restore <id> --restore-instance=cm-pg` (overwrites the DB, about 10 min). Migrations are forward-only.
- Telegram: point the webhook back (setWebhook to the run.app URL) or `python -m cm.jobs.tg_set_webhook --delete` and run the laptop stack with `tg_poll`.
- Domain: if the cert is not ACTIVE by demo time, demo on the `*.run.app` URL (same image, same DB).
- Full fallback: local stack (`docker compose up -d db`, API + web) with `scripts/ngrok_dev.sh`, which is what was tested so far.

---

## 7. Timing estimate for tomorrow

| Block | Who | Time |
|---|---|---|
| Code gaps G1 to G4 (+ G6, G9 if scheduler) | lanes L0/I/G/A in parallel | 2 to 3 h |
| G5 proper Cloud Tasks mode (or interim local mode: 10 min) | A + G | 2 to 3 h |
| 00 + placeholder + LB + DNS added | I + owner | 45 min |
| Cert provisioning (background, waits on DNS) | Google | 15 min to several hours |
| 10, 30 + owner adds secrets, 20 (SQL create), 40, 50 | I + owner | 45 to 60 min |
| First image build + push | I | 15 to 25 min |
| 60 deploy, 80 (migrate, Telegram), seed, RAG index | I | 45 min |
| 70 scheduler, smoke test, fixes | I | 45 to 60 min |
| **Total wall clock** | | **about 5 to 7 h** if code lanes start at the same time as infra; 8 h+ if serial |

Critical path: DNS + cert (start first) and G1/G2/G3/G4 (the image cannot run without them).
