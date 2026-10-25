# CareMemory deploy runbook (Windows, PowerShell): Cloud Run + Cloud SQL + Firebase Hosting/Auth

Status: written 2026-10-25 from a read-only review. No gcloud or firebase command was run and no secret was read.
Use this file on deploy day, top to bottom. It follows `DEPLOY_PLAN.md` (Cloud Run, Cloud SQL, Tasks) and
`FIREBASE_PLAN.md` (stage 1: two Hosting sites on `*.web.app`, Firebase Auth). The global load balancer and
custom domain from DEPLOY_PLAN 1.2 are **not** used. A custom domain is a later stage 2.

Who runs what:
- **OWNER**: the owner runs the step, because it involves a login, the console, billing or a secret value.
  Claude never asks for, prints or reads these values.
- **CLAUDE**: the agent runs the step after the owner says "deploy". Never print a secret value. Never commit `.env`.
- Every command is typed into **one PowerShell window** opened in `C:\Users\ramma\Downloads\jnthu_hackthon\caremem`,
  unless the step says otherwise.
- The `infra/*.sh` scripts are bash. They run through **Git Bash** (`bash.exe`), which is called from PowerShell.
  Plain `bash` in PowerShell may start WSL, so always use `$GitBash`.

Placeholders (fill them in once in step 2.1):
`<PROJECT_ID>` = the GCP project, which is also the Firebase project (FIREBASE_PLAN says `carememory`);
`<DOCTOR_SITE>` / `<PATIENT_SITE>` = Hosting site ids (e.g. `carememory-doctor`, `carememory-patient`);
`<BOT_USERNAME>` = the new cloud bot's username; `<TAG>` = image tag (e.g. `v1`).

---

## 0. Prerequisites the owner provides (before anyone says "deploy")

| # | OWNER task | Where / how | Done when |
|---|---|---|---|
| P1 | Choose the project id `<PROJECT_ID>` and confirm that the GCP project and the Firebase project are the same one | console.cloud.google.com, project picker | id written down (not secret) |
| P2 | Link billing (Blaze) | Console > Billing > Link a billing account | project shows a billing account |
| P3 | **Budget alert** | Console > Billing > Budgets & alerts > Create budget: scope = this project, amount **INR 5,000 / month**, thresholds **40% / 90% / 100%**, email to owner | budget listed. A budget only sends alerts. It does not stop spending. To stop spending, use section 12 |
| P4 | Install tools: Google Cloud SDK, Git for Windows (Git Bash), Node 22 + npm, Python venv of the repo (already used locally), Docker Desktop (only for the local DB) | official installers | `gcloud --version`, `node -v`, `& "$env:ProgramFiles\Git\bin\bash.exe" --version` all work |
| P5 | Firebase CLI: `npm i -g firebase-tools` | PowerShell | `firebase --version` |
| P6 | **Logins (owner types them; each opens a browser)**: `gcloud auth login` ; `gcloud config set project <PROJECT_ID>` ; `gcloud auth application-default login` ; `gcloud auth application-default set-quota-project <PROJECT_ID>` ; `firebase login` | PowerShell | `gcloud config list` shows the account and project |
| P7 | **Add Firebase to the GCP project**: console.firebase.google.com > Add project > pick the existing `<PROJECT_ID>` > keep Blaze; Google Analytics is not needed | Firebase console | the project shows in the Firebase console |
| P8 | **Firebase Auth**: Build > Authentication > Get started > Sign-in method > enable **Email/Password** (leave passwordless off). Settings > User actions: **untick "Enable create (sign-up)"** and "Enable delete". Settings: enable **email enumeration protection** | Firebase console | Email/Password = Enabled, sign-up off |
| P9 | **Web app config**: Project settings > General > Your apps > Add app (Web, `</>`), nickname `carememory-web`, no Hosting tick. Copy the 4 values `apiKey`, `authDomain`, `projectId`, `appId` **straight into `web/.env.production`** (step 9.2). Do not paste them into chat. The file is git-ignored | Firebase console | file saved |
| P10 | **Second Telegram bot (cloud bot)**: in Telegram open **@BotFather** (blue check) > `/newbot` > display name e.g. `CareMemory Cloud` > username ending in `bot` (e.g. `carememory_cloud_bot`). Keep the token on screen for step 4.3 and do not paste it into chat. The laptop keeps the existing dev bot. One bot = one webhook | Telegram | username `<BOT_USERNAME>` noted (not secret) |
| P11 | Have ready for step 4.3 (values only typed into a hidden prompt): `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, the new bot token. `LANGSMITH_API_KEY` is optional | own password manager | ready |
| P12 | Decide the demo time window. Quiet hours run 21:00-07:00 IST: for a night demo set `DEMO_IGNORE_QUIET_HOURS=1` (section 11.3) | | decided |

---

## 1. Pre-deploy repo edits (CLAUDE, before deploy day ends; each is a gap from section 13)

These files are in lane I. Claude makes the edits, the owner approves, and each one is logged in OpenSpec
`add-gcp-cloud-run-deploy` / `add-firebase-hosting-auth`. **Do not deploy until 1.1-1.6 are done.**

1.1 `infra/env/{api,worker,jobs}.env.yaml` and `infra/cloudbuild.yaml`: replace every `caremem-hack` with
    `<PROJECT_ID>` (GCP_PROJECT, GCS_DOCS_BUCKET, DB_HOST socket path, TASKS_INVOKER_SA, PUBSUB_PUSH_SA_EMAIL,
    GMAIL_PUBSUB_TOPIC) (gap 5).
1.2 `infra/env/api.env.yaml`: fill `FIREBASE_PROJECT_ID=<PROJECT_ID>`, `<site-doctor>` / `<site-patient>` and
    `TELEGRAM_BOT_USERNAME=<BOT_USERNAME>`. Change `CM_ALLOWED_HOSTS` to
    `<DOCTOR_SITE>.web.app,<DOCTOR_SITE>.firebaseapp.com,<PATIENT_SITE>.web.app,<PATIENT_SITE>.firebaseapp.com,*.run.app`
    (`.run.app` without `*` matches nothing, see gap 1) (gaps 1, 3).
1.3 `infra/env/worker.env.yaml`: `PUBLIC_BASE_URL: "https://<PATIENT_SITE>.web.app"`. While `<domain>` is
    still in the file, `60_deploy.sh` exits with "set DOMAIN" (gap 4).
1.4 `infra/60_deploy.sh`: write `WORKER_URL` and **`CM_TASKS_BASE_URL=$WORKER_URL`** into the rendered env files
    instead of using `--update-env-vars` together with `--env-vars-file`, which gcloud rejects as mutually exclusive
    (UNVERIFIED but likely). Set CM_TASKS_BASE_URL on cm-api, cm-worker and both jobs (gaps 2, 15).
1.5 `.firebaserc`: replace `REPLACE-firebase-project-id` with `<PROJECT_ID>` and the two `REPLACE-*-site-id`
    with `<DOCTOR_SITE>` / `<PATIENT_SITE>` (gap 6).
1.6 Add `.gcloudignore` (same exclusions as `.dockerignore`, plus `out/` and `.env*`). This keeps `out/` (demo
    credentials) and `.env` out of the Cloud Build upload (gap 13).
1.7 Run tests locally: `make check` (or `pytest -q`) is green with `AUTH_MODE=local`.

---

## 2. Session setup (CLAUDE, every new PowerShell window)

### 2.1 Variables and helpers
```powershell
Set-Location C:\Users\ramma\Downloads\jnthu_hackthon\caremem
$PROJECT = "<PROJECT_ID>"; $REGION = "asia-south1"
$DOCTOR_SITE = "<DOCTOR_SITE>"; $PATIENT_SITE = "<PATIENT_SITE>"; $TAG = "<TAG>"
$env:PROJECT = $PROJECT; $env:REGION = $REGION        # read by infra/vars.sh
$GitBash = "$env:ProgramFiles\Git\bin\bash.exe"
$AR = "$REGION-docker.pkg.dev/$PROJECT/cm"
function Run-Infra([string]$Script) { & $GitBash $Script; if ($LASTEXITCODE -ne 0) { throw "$Script failed ($LASTEXITCODE)" } }
gcloud config set project $PROJECT
```

### 2.2 Secret helper (OWNER runs it; the value is typed into a hidden prompt, never shown, never in history)
```powershell
function Add-SecretValue([string]$Name) {
  $s = Read-Host "Value for $Name (hidden)" -AsSecureString
  $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
  $tmp = New-TemporaryFile
  try { [IO.File]::WriteAllText($tmp.FullName, [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b))  # no trailing newline
        gcloud secrets versions add $Name --data-file="$($tmp.FullName)" | Out-Null; "added a version to $Name" }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b); Remove-Item $tmp.FullName -Force }
}
```

### 2.3 Tool check (CLAUDE)
```powershell
gcloud --version; firebase --version; node -v; python --version
& $GitBash -lc "gcloud --version >/dev/null && openssl version && echo git-bash-ok"
$env:DRY_RUN = "1"; Run-Infra infra/00_project.sh; Remove-Item Env:DRY_RUN   # prints the gcloud calls only
```
If Git Bash cannot run `gcloud`, run sections 3-6 in **Cloud Shell** instead. Upload the repo without `.env`
and `out/`, then use the same `bash infra/<script>.sh` commands.

---

## 3. Enable APIs (CLAUDE)

```powershell
Run-Infra infra/00_project.sh        # run, sql, secrets, tasks, scheduler, build, artifact registry, pubsub, storage, ...
gcloud services enable firebase.googleapis.com firebasehosting.googleapis.com identitytoolkit.googleapis.com securetoken.googleapis.com
gcloud services list --enabled --format="value(config.name)" | Select-String "run|sqladmin|secretmanager|cloudtasks|firebasehosting|identitytoolkit"
```
`00_project.sh` also creates Artifact Registry `cm` and the bucket `<PROJECT_ID>-cm-docs`. Bucket names are
global, so if the create fails because the name is taken, rename the bucket in the env files. Adding Firebase in
P7 usually enables the Firebase APIs already; the second line makes sure (gap 11).

---

## 4. Service accounts and Secret Manager

4.1 CLAUDE: `Run-Infra infra/10_iam.sh`. A WARN about the Pub/Sub service agent is normal; it is re-run in 6.
4.2 CLAUDE: `Run-Infra infra/30_secrets.sh`. This creates the secrets (replicated in asia-south1 only) and
    generates the random ones. It then prints the REQUIRED names that still have no value (names only).

Secret names (values are never in the repo or in chat):

| Name | Filled by | Used by |
|---|---|---|
| `OPENAI_API_KEY` | OWNER (4.3) | api, worker, jobs |
| `DEEPSEEK_API_KEY` | OWNER (4.3) | api, worker, jobs |
| `TELEGRAM_BOT_TOKEN` | OWNER (4.3), the **new cloud bot** from P10 | worker, jobs |
| `DEMO_USER_PASSWORDS` | OWNER (4.3), same JSON as local `.env` (only needed for the cloud `cm-seed` path, 8.5) | api, jobs |
| `LANGSMITH_API_KEY` | OWNER, optional | api, worker, jobs |
| `GMAIL_OAUTH_CLIENT_JSON`, `GMAIL_REFRESH_TOKEN` | optional, P1 later | worker, jobs |
| `TELEGRAM_WEBHOOK_SECRET`, `JWT_SIGNING_KEY`, `PII_MASTER_KEY` | generated by 30_secrets.sh | api / worker / jobs |
| `DB_PASSWORD_APP`, `DB_PASSWORD_ENGINE`, `DB_PASSWORD_READER`, `DB_PASSWORD_ADMIN` | generated by 30_secrets.sh | Cloud SQL users (step 5) |

4.3 OWNER adds the external values (paste into the hidden prompt):
```powershell
Add-SecretValue OPENAI_API_KEY
Add-SecretValue DEEPSEEK_API_KEY
Add-SecretValue TELEGRAM_BOT_TOKEN          # the NEW cloud bot token (P10), not the laptop dev bot
# optional: Add-SecretValue LANGSMITH_API_KEY
# DEMO_USER_PASSWORDS: copy the exact local value from .env without showing it
$line = Get-Content .env | Where-Object { $_ -match '^DEMO_USER_PASSWORDS=' } | Select-Object -First 1
$tmp = New-TemporaryFile; [IO.File]::WriteAllText($tmp.FullName, ($line -replace '^DEMO_USER_PASSWORDS=','').Trim().Trim("'").Trim('"'))
gcloud secrets versions add DEMO_USER_PASSWORDS --data-file="$($tmp.FullName)" | Out-Null; Remove-Item $tmp.FullName -Force; Remove-Variable line
```
4.4 CLAUDE (names only, no values): `& $GitBash -lc "source infra/vars.sh; for s in OPENAI_API_KEY DEEPSEEK_API_KEY TELEGRAM_BOT_TOKEN DEMO_USER_PASSWORDS; do has_secret_value `$s && echo ok:`$s || echo MISSING:`$s; done"`

---

## 5. Cloud SQL Postgres 16 + pgvector (CLAUDE)

```powershell
Run-Infra infra/20_sql.sh     # cm-pg, PG16 ENTERPRISE db-custom-1-3840, zonal, 10 GB SSD, db "caremem", users cm_app/cm_engine/cm_reader/cm_admin
gcloud sql instances describe cm-pg --format="value(state,databaseVersion,settings.edition,maintenanceVersion)"
```
- Instance creation takes 10-15 min. Wait until the state is `RUNNABLE`.
- **pgvector**: Cloud SQL for PostgreSQL supports the `vector` extension, and `cm_admin` (a member of
  `cloudsqlsuperuser`) may create it. Migration `0001` runs `CREATE EXTENSION IF NOT EXISTS vector`. `0004` uses
  `halfvec(1536)`, which needs **pgvector >= 0.7.0**. Recent PG16 maintenance versions ship 0.8.x
  (**VERIFY on the day**: the exact version follows the instance's `maintenanceVersion`). Check it after
  migrations (7.3). If it is below 0.7, either run a maintenance update
  (`gcloud sql instances patch cm-pg --maintenance-version=<latest listed by describe>`) or migrate with
  `RAG_VECTOR_TYPE=vector` (see the header of `0004_rag.sql`). `cm/jobs/migrate.py` does **not** assert the
  version today (gap 10).
- The instance has a public IP with no authorized networks. Access goes only through the Cloud SQL connector
  (Cloud Run) or the Auth Proxy (step 8).

---

## 6. Pub/Sub and Cloud Tasks queues (CLAUDE)

```powershell
Run-Infra infra/40_pubsub.sh          # topics gmail-push, dead-letter (harmless while Gmail is off)
Run-Infra infra/10_iam.sh             # re-run: the Pub/Sub service agent now exists
Run-Infra infra/50_tasks.sh           # queues agent-runs, resumes (2/s, 4 concurrent, 6 attempts), outbound (5/s, 10)
gcloud tasks queues list --location=$REGION --format="value(name,state)"
```

---

## 7. Build, deploy Cloud Run (asia-south1), migrate

7.1 Build and push the image (CLAUDE). Cloud Build is used, so local Docker is not needed:
```powershell
gcloud builds submit --tag "$AR/cm:$TAG" --timeout=1800s .
```
If Cloud Build fails on permissions (new projects build as the default compute SA), grant that SA
`roles/artifactregistry.writer` and `roles/logging.logWriter`, or add
`--service-account=projects/$PROJECT/serviceAccounts/cm-deployer@$PROJECT.iam.gserviceaccount.com --default-buckets-behavior=regional-user-owned-bucket`.

7.2 Deploy cm-worker (private), cm-api (public, AUTH_MODE=firebase) and the jobs cm-migrate and cm-seed (CLAUDE):
```powershell
$env:IMAGE = "$AR/cm:$TAG"; Run-Infra infra/60_deploy.sh
$API_URL    = gcloud run services describe cm-api    --region=$REGION --format="value(status.url)"
$WORKER_URL = gcloud run services describe cm-worker --region=$REGION --format="value(status.url)"
gcloud run services describe cm-api --region=$REGION --format="yaml(spec.template.spec.containers[0].env)" | Select-String "CM_TASKS_BASE_URL|AUTH_MODE|CM_ALLOWED_HOSTS"
```
A secret that has no value is skipped and listed by name. If `CM_TASKS_BASE_URL` is missing (1.4 not done), fix
it now:
`gcloud run services update cm-api --region=$REGION --update-env-vars="CM_TASKS_BASE_URL=$WORKER_URL"` (same for
`cm-worker`), and `gcloud run jobs update cm-migrate --region=$REGION --update-env-vars="CM_TASKS_BASE_URL=$WORKER_URL"`
(same for `cm-seed`).

7.3 Run migrations (CLAUDE). Take a backup first. Migrations run as `cm_admin` and only move forward:
```powershell
gcloud sql backups create --instance=cm-pg
gcloud run jobs execute cm-migrate --region=$REGION --wait
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=cm-migrate" --freshness=15m --limit=20 --format="value(textPayload)"
```
The log should say `applied N migration(s): 0001_core.sql, ...`. A second run says `none (up to date)`.
`80_webhooks.sh` would also migrate and set the Telegram webhook. This runbook does the two separately (7.3 and 10).

---

## 8. Same mock data and demo accounts as local (export / import)

What "same" means: the main cohort (`cm.jobs.seed`, seed 42, sim day 59, deterministic ids, `seed_data.json`) is
regenerated identically. The two demo accounts (`demo.pt0906` 6 days, `demo.pt0960` 60 days) are moved with the
existing bundle path `cm.jobs.seed_demo_accounts --export` / `--import`. The passwords are the local ones
(`.env` `DEMO_USER_PASSWORDS`, `out/demo_accounts_credentials.txt`). Local edits made after seeding (approvals
clicked, Telegram bindings, uploads) are **not** carried (gap 9).

The import runs **from the laptop into Cloud SQL through the Cloud SQL Auth Proxy**. The bundle file is not in
the image (`out/` is excluded) and there is no Cloud Run job for it (gap 8).

8.1 Export locally (CLAUDE, uses the local Docker DB and the local `.env`, `CM_DATA_CLASS=mock`):
```powershell
docker compose up -d db
python -m cm.jobs.seed_demo_accounts --export out\demo_accounts.json
```
This prints `exported N events, 2 patients to out\demo_accounts.json` and contains no passwords.

8.2 OWNER: download the official **Cloud SQL Auth Proxy v2** for Windows (`cloud-sql-proxy.x64.exe`) from the
Google Cloud docs page "Connect using the Cloud SQL Auth Proxy" into `C:\tools\`. Start it in a **second
PowerShell window** and leave it running (it uses the ADC login from P6):
```powershell
C:\tools\cloud-sql-proxy.x64.exe --port 5433 "<PROJECT_ID>:asia-south1:cm-pg"
```

8.3 Point this window at Cloud SQL as `cm_admin`. The OWNER runs the password line; the value goes into the
variable only and is not shown:
```powershell
$env:DB_HOST = "127.0.0.1"; $env:DB_PORT = "5433"; $env:DB_NAME = "caremem"; $env:DB_USER = "cm_admin"
$env:CM_DATA_CLASS = "mock"; $env:TASKS_MODE = "local"
$env:DB_PASSWORD = gcloud secrets versions access latest --secret=DB_PASSWORD_ADMIN     # OWNER
```
Real env vars win over `.env` (`load_dotenv` never overrides them), so `.env` still supplies
`DEMO_USER_PASSWORDS` and `OPENAI_API_KEY` but not the DB target.

8.4 Seed Cloud SQL from the laptop (CLAUDE, same window):
```powershell
python -m cm.jobs.migrate                                                   # "none (up to date)"
python -c "import os,psycopg; c=psycopg.connect(host='127.0.0.1',port=5433,dbname='caremem',user='cm_admin',password=os.environ['DB_PASSWORD']); print('pg', c.execute('show server_version').fetchone()[0], 'pgvector', c.execute(\"select extversion from pg_extension where extname='vector'\").fetchone()[0])"
python -m cm.jobs.seed                                                      # main cohort, idempotent; do NOT pass --reset
python -m cm.jobs.seed_demo_accounts --import out\demo_accounts.json        # 6/60-day accounts, same passwords (read from out\demo_accounts_credentials.txt)
python -m cm.jobs.rag_index --all                                           # RAG index for the cohort (embeddings via OPENAI_API_KEY; add --no-embed for full-text only)
```
Write down the pgvector version printed by the second line in `docs/deploy/DEPLOY_PLAN.md` (it must be >= 0.7).
`seed_demo_accounts --import` also runs the memory pipeline and indexing for the two accounts (`--no-embed` skips
embeddings, `--skip-pipeline` skips both).

8.5 Alternative for the main cohort only (no proxy): `gcloud run jobs execute cm-seed --region=$REGION --wait`.
It uses the `DEMO_USER_PASSWORDS` secret from 4.3, so the passwords are the same as local. The demo accounts
still need 8.2-8.4.

8.6 Clean up the window (CLAUDE): `Remove-Item Env:DB_PASSWORD,Env:DB_HOST,Env:DB_PORT,Env:DB_USER`, then stop
the proxy window with Ctrl+C.

---

## 9. Firebase Auth users and the two Hosting sites

9.1 Demo users with claims `role/pid/tv` (CLAUDE, laptop; needs ADC from P6). Users: `dr.rao`, `admin.demo`,
`ravi.pt0142`, `lakshmi.s01`, `demo.pt0906`, `demo.pt0960`. Emails are `<username>@users.carememory.app` and
are never mailed. `scripts/firebase_users.py` reads passwords **only from env** (gap 7), so they are loaded
without being shown:
```powershell
pip install firebase-admin==6.5.0
$env:FIREBASE_PROJECT_ID = $PROJECT; $env:AUTH_EMAIL_DOMAIN = "users.carememory.app"
$line = Get-Content .env | Where-Object { $_ -match '^DEMO_USER_PASSWORDS=' } | Select-Object -First 1
$env:DEMO_USER_PASSWORDS = ($line -replace '^DEMO_USER_PASSWORDS=','').Trim().Trim("'").Trim('"'); Remove-Variable line
$map = [ordered]@{}
Get-Content out\demo_accounts_credentials.txt | Where-Object { $_ -notmatch '^#' -and $_.Contains("`t") } |
  ForEach-Object { $u, $p = $_.Split("`t", 2); $map[$u.Trim()] = $p.Trim() }
$env:DEMO_ACCOUNT_PASSWORDS = $map | ConvertTo-Json -Compress; Remove-Variable map
python scripts\firebase_users.py              # dry run: 6 lines "would create/update"
python scripts\firebase_users.py --apply      # expect 6 x "created, claims ok"; "skipped" = password missing or < 12 chars
Remove-Item Env:DEMO_USER_PASSWORDS, Env:DEMO_ACCOUNT_PASSWORDS
```
The tv default is 1, which matches a fresh Cloud SQL (`token_version DEFAULT 1`).

9.2 Web build for Firebase (CLAUDE writes the non-secret lines; the OWNER pastes the 4 console values from P9).
File `web\.env.production` is git-ignored and excluded from the image:
```
VITE_USE_MOCK=false
VITE_API_BASE=
VITE_AUTH_MODE=firebase
VITE_AUTH_EMAIL_DOMAIN=users.carememory.app
VITE_FIREBASE_PERSISTENCE=session
VITE_FIREBASE_API_KEY=<owner pastes>
VITE_FIREBASE_AUTH_DOMAIN=<owner pastes>
VITE_FIREBASE_PROJECT_ID=<owner pastes>
VITE_FIREBASE_APP_ID=<owner pastes>
```
```powershell
Push-Location web; npm ci; npm run build; Pop-Location     # writes web\dist (one build for both sites)
```
In firebase mode the web app polls (`sse.ts` `pollOnly`), so `/stream` is never used through Hosting.

9.3 Create two sites, map the targets, preview, then go live (CLAUDE):
```powershell
firebase hosting:sites:create $DOCTOR_SITE  --project $PROJECT
firebase hosting:sites:create $PATIENT_SITE --project $PROJECT
firebase target:apply hosting doctor  $DOCTOR_SITE  --project $PROJECT    # only if 1.5 was not done by hand
firebase target:apply hosting patient $PATIENT_SITE --project $PROJECT
firebase hosting:channel:deploy preview --only doctor,patient --project $PROJECT --expires 2d
# smoke the two preview URLs (section 11, steps 3-6), then:
firebase deploy --only hosting --project $PROJECT
```
Site ids are global. If one is taken, choose another and update 1.2, 1.5 and the variables.
- The `firebase.json` rewrites send `/auth`, `/review`, `/patients`, ... to Cloud Run `cm-api` in `asia-south1`.
  **VERIFY** at the first deploy that Hosting accepts the `asia-south1` rewrite. If it is refused, the fallback is to
  rebuild with `VITE_API_BASE=$API_URL`, add `$API_URL` to the CSP `connect-src` in `firebase.json`, and set
  `CORS_ORIGINS` to the two site origins.
- `/webhooks/*` and `/tasks/*` are deliberately **not** rewritten. Telegram calls `$API_URL` directly.

9.4 OWNER, Firebase console > Authentication > Settings > **Authorized domains**: make sure
`<DOCTOR_SITE>.web.app` and `<PATIENT_SITE>.web.app` are listed (add them if missing). Leave `localhost`
only if it is needed for dev.

9.5 If `CORS_ORIGINS` / `CM_ALLOWED_HOSTS` changed after 7.2: edit `infra/env/api.env.yaml`, then re-run 7.2.
The re-run is idempotent and creates a new revision.

---

## 10. Telegram: webhook for the second (cloud) bot

Hosting does not proxy `/webhooks`, so the webhook goes to the Cloud Run URL. The laptop keeps the dev bot
with `tg_poll`. **Never run `python -m cm.jobs.tg_poll` with the cloud bot token**: it calls `deleteWebhook`.

Option A (CLAUDE, Git Bash script, token never printed):
```powershell
& $GitBash infra/90_telegram_webhook.sh $API_URL
```
Option B (OWNER, pure PowerShell, same effect):
```powershell
$tok = gcloud secrets versions access latest --secret=TELEGRAM_BOT_TOKEN
$sec = gcloud secrets versions access latest --secret=TELEGRAM_WEBHOOK_SECRET
$body = @{ url = "$API_URL/webhooks/telegram"; secret_token = $sec; allowed_updates = @("message","callback_query"); drop_pending_updates = $true } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$tok/setWebhook" -ContentType "application/json" -Body $body | Out-Null
(Invoke-RestMethod "https://api.telegram.org/bot$tok/getWebhookInfo").result | Select-Object url, pending_update_count, last_error_message
Remove-Variable tok, sec, body
```
The expected `url` is `https://cm-api-...run.app/webhooks/telegram`, with no `last_error_message`. Then send
`/start` to `@<BOT_USERNAME>`.

---

## 11. Scheduler and smoke tests

11.1 Scheduler (CLAUDE): `Run-Infra infra/70_scheduler.sh` creates `sched-drain-outbox` (every minute) and
`sched-checkins` (07:30 IST). Both send OIDC to cm-worker, which works only when `CM_TASKS_BASE_URL` is set
(1.4 / 7.2).

11.2 Smoke checks (CLAUDE; use `curl.exe`, not the PowerShell `curl` alias):
1. `Run-Infra infra/tests/smoke.sh`: api /healthz ok, the worker rejects anonymous calls (401/403), the 3 queues and 2 jobs exist, and cm-pg is `ENTERPRISE RUNNABLE`.
2. `curl.exe -fsS "$API_URL/readyz"` returns `{"status":"ok","db":true}` (socket + `DB_PASSWORD` mapping work).
3. `curl.exe -fsS "https://$DOCTOR_SITE.web.app/healthz"` returns ok (the Hosting rewrite reaches Cloud Run).
4. `curl.exe -sI "https://$DOCTOR_SITE.web.app/"` gives `302` to `/doctor`; on the patient site it goes to `/patient`. A deep link such as `/doctor/approvals` returns the SPA.
5. `curl.exe -s -o NUL -w "%{http_code}" "https://$DOCTOR_SITE.web.app/auth/me"` gives `401` (no token).
6. Browser: sign in as `dr.rao` on the doctor site and as `demo.pt0960` on the patient site. There is no MOCK badge. DevTools shows `Authorization: Bearer` on API calls and `Cache-Control: private, no-store` on responses (VERIFY that Hosting forwards `Authorization`). PT-0960 shows 60 days of history, PT-0906 shows 6.
7. Approve one review card as `dr.rao`. It leaves the queue within a 5 s poll.
8. Telegram: `/start` to the cloud bot gets a reply; cm-api logs show `update_id` only.
9. `gcloud scheduler jobs run sched-drain-outbox --location=$REGION`. The worker log shows 200, not 401.
10. `gcloud logging read "severity>=ERROR AND resource.type=cloud_run_revision" --freshness=15m --limit=20 --format="value(textPayload)"` is empty.

11.3 Night demo only: `gcloud run services update cm-api --region=$REGION --update-env-vars=DEMO_IGNORE_QUIET_HOURS=1`
(same for `cm-worker`). Set it back to `0` afterwards.

---

## 12. Rollback and stop switches

| What broke | Command |
|---|---|
| New cm-api / cm-worker revision | `gcloud run revisions list --service=cm-api --region=$REGION` then `gcloud run services update-traffic cm-api --region=$REGION --to-revisions=<previous>=100` (same for cm-worker) |
| Hosting release | Firebase console > Hosting > site > Release history > **Rollback** on the previous release (or rebuild and `firebase deploy --only hosting:doctor`) |
| Firebase login path broken | Set cm-api `AUTH_MODE=local` (`gcloud run services update cm-api --region=$REGION --update-env-vars=AUTH_MODE=local`) and use `$API_URL` directly. The image's own SPA is built in local mode and uses the cookie login |
| One demo user compromised | `python scripts\firebase_users.py --revoke <username> --apply` |
| Database / bad migration or seed | `gcloud sql backups list --instance=cm-pg` then `gcloud sql backups restore <BACKUP_ID> --restore-instance=cm-pg` (overwrites the DB, about 10 min) |
| Telegram | point the webhook at the previous URL (10), or `python -m cm.jobs.tg_set_webhook --delete` with the cloud token and demo locally with the dev bot |
| Everything | local stack: `docker compose up -d db`, API + web, `scripts/ngrok_dev.sh` (the tested path) |

Stop spending (OWNER approves): `gcloud run services update cm-api --region=$REGION --min-instances=0`;
`gcloud sql instances patch cm-pg --activation-policy=NEVER` (start again with `ALWAYS`, 2-5 min);
`gcloud scheduler jobs pause sched-drain-outbox --location=$REGION` (and `sched-checkins`).

---

## 13. Cost note (asia-south1, approximate; verify in the pricing calculator)

| Item | Setting | USD/day | INR/day (~88/USD) |
|---|---|---|---|
| Cloud SQL Enterprise `db-custom-1-3840` + 10 GB SSD | always on | 2.2-2.6 | 195-230 |
| cm-api min 1 instance, 2 vCPU / 2 GiB, idle | `min-instances=1` | 1.0-1.5 | 90-130 |
| cm-worker, jobs | scale to zero | < 0.2 | < 20 |
| Firebase Hosting (2 sites), Firebase Auth email/password | free tier at demo volume (Auth stays free well past demo use; VERIFY if upgraded to Identity Platform) | ~0 | ~0 |
| Tasks, Scheduler (2 jobs, within the 3 free), Pub/Sub, Secret Manager (~14 secrets), Artifact Registry, Logging | low volume | < 0.3 | < 25 |
| LLM providers (OpenAI / DeepSeek) | outside GCP, capped by `CM_BUDGET_DAILY_USD` | per cap | per cap |
| **Total GCP** | no load balancer in this plan | **about 3.5-4.5** | **about 300-400** |

That is roughly INR 9,000-12,000 per 30 days if everything stays on. Against the INR 5,000 budget, stop the DB
and set min-instances to 0 (section 12) between demo days.

---

## 14. Gaps found in the existing code and scripts (numbered)

1. **Blocker.** `infra/env/api.env.yaml` `CM_ALLOWED_HOSTS` ends with `.run.app`, but `cm/api/web.py::host_allowed` only matches exact names or `*.`-prefixed patterns. Every request to `cm-api-*.run.app` (Telegram webhook, direct calls, possibly the Hosting rewrites) would get 400 "Invalid host header". Use `*.run.app`.
2. **Blocker.** `CM_TASKS_BASE_URL` is set nowhere: not in the env YAMLs, and `60_deploy.sh` injects only `WORKER_URL`. In `TASKS_MODE=cloud`, `cm.core.tasks.enqueue` raises `TasksConfigError`, and `/tasks/*` on cm-worker fails closed (401) for Scheduler and Tasks OIDC calls. Set it to the cm-worker URL on api, worker and jobs.
3. `api.env.yaml` still has the placeholders `<firebase-project-id>`, `<site-doctor>`, `<site-patient>` and `<bot-username>`. `render_env` substitutes only `<domain>`. With `AUTH_MODE=firebase`, cm-api will verify tokens against the wrong project and reject every host.
4. `infra/env/worker.env.yaml` keeps `PUBLIC_BASE_URL: https://<domain>`, so `render_env` calls `need_domain` and `60_deploy.sh` exits in the Firebase stage 1, where there is no domain.
5. The project id `caremem-hack` is hard-coded in all three env YAMLs (instance socket path, bucket, SA emails, topic), in `infra/cloudbuild.yaml`, and as the `vars.sh` default. FIREBASE_PLAN names the project `carememory`. They must match.
6. `.firebaserc` contains only `REPLACE-*` placeholders. `firebase.json` defines only the `doctor` and `patient` targets, which matches the two-site decision. FIREBASE_PLAN 1.1 still lists family and demo sites.
7. `scripts/firebase_users.py` reads passwords only from the env vars `DEMO_USER_PASSWORDS` / `DEMO_ACCOUNT_PASSWORDS`. It neither loads `.env` nor reads `out/demo_accounts_credentials.txt` (the seeds do both), so `--apply` without the 9.1 loader skips every user. FIREBASE_PLAN 2.6 says it reads Secret Manager; the code does not.
8. `cm.jobs.seed_demo_accounts` has no Cloud Run job and no `DEMO_ACCOUNT_PASSWORDS` secret in `30_secrets.sh`. In the container it would try to write `out/demo_accounts_credentials.txt` as uid 10001 under `/app`, and the bundle file is not in the image (`out` is in `.dockerignore`). The import must run from the laptop through the Auth Proxy (section 8).
9. `cm.jobs.seed` has no export/import. Cloud data equals local only because the seed is deterministic; local changes made after seeding are lost. A full copy would need `pg_dump`/`pg_restore`, which is not scripted.
10. `cm/jobs/migrate.py` does not assert pgvector >= 0.7, although `0001_core.sql` and `20_sql.sh` say "asserted by cm-migrate". On an old extension, `0004` fails on `halfvec` with an unclear error.
11. `infra/00_project.sh` does not enable `firebase`, `firebasehosting`, `identitytoolkit` or `securetoken`. It still enables `compute`, which was only needed for the dropped load balancer (harmless).
12. All `infra/*.sh` are bash. On Windows they need Git Bash, and `bash` in PowerShell may start WSL. MSYS path conversion of the `mktemp` env-file paths passed to `gcloud.exe` is UNVERIFIED; Cloud Shell is the fallback.
13. There is no `.gcloudignore`. `gcloud builds submit` uploads the source tarball to a Cloud Build bucket, and keeping `.env` and `out/` (demo credentials) out of it depends on gcloud's automatic `.gitignore` handling.
14. `infra/20_sql.sh` passes DB passwords on the command line (`--password="$(...)"`), so they are visible in the local process list while it runs.
15. `60_deploy.sh` combines `--env-vars-file` with `--update-env-vars` on `run deploy` and `run jobs deploy`. gcloud treats these as mutually exclusive (the script itself marks the jobs case UNVERIFIED), so the deploy may fail at cm-worker or cm-api.
16. cm-api keeps `--timeout=60`, and Hosting rewrites cap requests at 60 s anyway. Long `/query` LLM calls or large `/portal/documents` uploads through Hosting can return 504. FIREBASE_PLAN asks for `--timeout=3600` on cm-api; it is not applied.
17. The image's web bundle is built in local auth mode (the Dockerfile sets no `VITE_AUTH_MODE`). With `AUTH_MODE=firebase` on cm-api, `/auth/login` returns 404, so the SPA served at `$API_URL` cannot sign in. That fallback only works after switching cm-api back to `AUTH_MODE=local`.
18. `30_secrets.sh` lists `DEMO_USER_PASSWORDS` as REQUIRED, but in firebase mode it is needed only by the optional `cm-seed` job path. FIREBASE_PLAN's rollback cites `firebase hosting:rollback`, which this review could not confirm as a CLI command (use the console Release history).
19. `Dockerfile` pulls `ghcr.io/astral-sh/uv:0.9` (marked UNVERIFIED, not an exact pin), and `infra/cloudbuild.yaml` hard-codes the project and runs the same `60_deploy.sh`, so gaps 2, 4, 5 and 15 also affect CI.
