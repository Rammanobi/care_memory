# CareMemory Makefile. On Windows run from Git Bash/WSL (winget install ezwinports.make).
PY ?= python
.PHONY: install up down down-db migrate seed snapshot restore reseed-demo run-api run-worker run-local \
        offline ngrok gmail-poll docs eval eval-narrator cassette-record cassette-check banned-terms \
        redteam contracts-check lint test web-build check deploy smoke-gcp

install:         ; $(PY) -m pip install -r requirements-dev.txt && npm ci
up:              ; docker compose up -d db
down:            ; docker compose down
down-db:         ; docker compose down -v
migrate:         ; $(PY) -m cm.jobs.migrate
seed:            ; $(PY) -m cm.jobs.seed --seed 42 --patients 40 --days 60 --backfill --sim-day 59
snapshot:        ; docker compose exec -T db pg_dump -U postgres -Fc caremem > fixtures/snapshots/seed42_d59.dump
restore:         ; docker compose exec -T db pg_restore -U postgres --clean --if-exists -d caremem < fixtures/snapshots/seed42_d59.dump
reseed-demo:     down-db up migrate seed snapshot
run-api:         ; CM_ROLE=api TASKS_MODE=local $(PY) -m cm
run-worker:      ; CM_ROLE=worker PORT=8081 TASKS_MODE=local $(PY) -m cm
run-local:       ; $(MAKE) -j2 run-api run-worker
offline:         ; CM_OFFLINE=1 $(MAKE) restore run-local
ngrok:           ; bash scripts/ngrok_dev.sh
gmail-poll:      ; $(PY) -m cm.channels.gmail --sweep-loop 30
docs:            ; docker compose --profile tools run --rm dev python -m cm.sim.docs --seed 42
eval:            ; $(PY) -m cm.jobs.eval_job --seeds 2042,2077,2026 --full
eval-narrator:   ; $(PY) -m cm.eval.judge --dataset narrator-golden-v1
cassette-record: ; CM_CASSETTE=record $(PY) -m pytest tests/replay -m live
cassette-check:  ; CM_OFFLINE=1 $(PY) -m pytest tests/replay -q
banned-terms:    ; $(PY) -m pytest tests/unit/content/test_banned_terms.py -q
redteam:         ; $(PY) -m pytest tests/redteam -q
contracts-check: ; $(PY) -m pytest tests/contract -q
lint:            ; $(PY) -m ruff format --check . && $(PY) -m ruff check . && lint-imports
test:            ; $(PY) -m pytest -m "not live and not slow and not docs" -q
web-build:       ; cd web && npm run build
check:           lint test contracts-check web-build
deploy:          ; gcloud builds submit --config infra/cloudbuild.yaml --substitutions=SHORT_SHA=$$(git rev-parse --short HEAD)
smoke-gcp:       ; bash infra/tests/smoke.sh
