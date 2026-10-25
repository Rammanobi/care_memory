## ADDED Requirements

### Requirement: Cloud Run deployment
The system SHALL deploy cm-api and cm-sweeper to Cloud Run and jobs to Cloud Run Jobs with queues agent-runs, resumes and outbound.

#### Scenario: Deploy from clean checkout
- **WHEN** the deploy script runs with project env set
- **THEN** services start and health checks pass

### Requirement: Stage-1 cloud config without custom domain or cloud Telegram bot
The infra scripts SHALL deploy to project `carememory-c1b3f` (asia-south1) using Firebase Hosting `*.web.app` and Cloud Run `run.app` URLs only, with the project id and Hosting site ids defined once in `infra/vars.sh` and rendered into `infra/env/*.env.yaml`. The cloud Telegram bot SHALL be disabled unless `TELEGRAM_ENABLED=1`: no Telegram secret is required, created, granted or mounted, and no webhook is set.

#### Scenario: Deploy without DOMAIN and without Telegram token
- **WHEN** `60_deploy.sh` runs with `DOMAIN` unset and `TELEGRAM_ENABLED` unset
- **THEN** it does not exit on DOMAIN, mounts no Telegram secret, and `30_secrets.sh` lists only `OPENAI_API_KEY` and `DEEPSEEK_API_KEY` as required

#### Scenario: Unfilled placeholder is refused
- **WHEN** a rendered env file still contains a `<placeholder>` outside comments
- **THEN** `render_env` exits non-zero before any gcloud deploy call

### Requirement: Cloud Tasks base URL and single env file per deploy
`60_deploy.sh` SHALL set `CM_TASKS_BASE_URL` and `WORKER_URL` to the cm-worker URL on cm-api, cm-worker and every job, written into one rendered env file per deploy, and SHALL NOT combine `--env-vars-file` with `--update-env-vars` in one gcloud call. `CM_ALLOWED_HOSTS` SHALL include `*.run.app`.

#### Scenario: Worker URL reaches every service
- **WHEN** `DRY_RUN=1 IMAGE=x bash infra/60_deploy.sh` runs
- **THEN** each rendered env file for cm-worker, cm-api, cm-migrate and cm-seed contains `CM_TASKS_BASE_URL` and no deploy line carries both env flags

### Requirement: Secret-safe build upload and demo password upload
The Cloud Build upload SHALL exclude `.env*`, `out/`, `data/uploads/`, `node_modules` and `.git` (`.gcloudignore`). `DEMO_USER_PASSWORDS` SHALL be copied from the local `.env` to Secret Manager through stdin only (`infra/35_demo_passwords.sh`), validated as a JSON object without printing it, and SHALL be needed only by the cm-seed job.

#### Scenario: Invalid demo password JSON
- **WHEN** `35_demo_passwords.sh` reads a value that is not a JSON object
- **THEN** it exits non-zero with a message that names the variable and does not contain the value
