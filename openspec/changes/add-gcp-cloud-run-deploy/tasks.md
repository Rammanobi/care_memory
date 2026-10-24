## 1. Implementation
- [ ] 1.1 Dockerfile + build test
- [ ] 1.2 Service and job manifests
- [ ] 1.3 Queue config (2/s, 4 concurrent, 6 attempts for resumes)
- [ ] 1.4 Deploy runbook

## 2. Deploy day (from docs/deploy/DEPLOY_PLAN.md, 2026-10-25 review)
- [x] 2.1 Write docs/deploy/DEPLOY_PLAN.md (architecture, runbook, gaps, cost, inputs, smoke, rollback)
- [ ] 2.2 (I) Dockerfile: drop COPY of missing models/, fixtures/cassettes, fixtures/eval; set VITE_USE_MOCK=false and VITE_API_BASE="" in the web stage; pin uv. Test: docker build succeeds
- [x] 2.3 (L0/I) cm/__main__.py dispatching CM_ROLE=api|worker (uvicorn on $PORT) and CM_ROLE=job (cm.jobs.<CM_JOB>). Test: CM_ROLE=api python -m cm serves /healthz
- [ ] 2.4 (G) Serve web/dist from cm-api: /assets StaticFiles + SPA fallback for /, /doctor/*, /patient/*, /supporter/*; TrustedHostMiddleware. Test: reload of /doctor/approvals returns index.html; API routes unchanged
- [x] 2.5 (I) infra/env/*.env.yaml: DB_HOST=/cloudsql/<instance>, DB_USER per service, COOKIE_SECURE=1, CORS_ORIGINS=hostnames, PUBLIC_BASE_URL, model names, LANGSMITH_TRACING per key availability
- [x] 2.6 (I) infra/60_deploy.sh: map DB_PASSWORD=DB_PASSWORD_APP (api/worker) and DB_PASSWORD_ADMIN + DB_USER=cm_admin (jobs); trim --set-secrets to secrets that have versions; deploy only cm-migrate and cm-seed jobs
- [x] 2.7 (I) infra/00_project.sh: enable compute.googleapis.com
- [x] 2.8 (I) New infra/85_lb.sh + infra/lb/urlmap.yaml: static IP, serverless NEG, backend, URL map with per-host "/" redirects, managed cert for all hostnames, HTTPS proxy, HTTP->HTTPS redirect
- [ ] 2.9 (A) Cloud Tasks mode in cm/core/tasks.py (name = task_id, OIDC to cm-worker), or record the interim TASKS_MODE=local + --no-cpu-throttling decision
- [ ] 2.10 (G) OIDC verification for /tasks/* (audience worker URL, email cm-tasks-invoker); remove the cloud-mode 501
- [x] 2.11 (I) infra/70_scheduler.sh: keep check-ins, add drain-outbox every minute; drop sweeper, nightly, portal-sync, digest, visit-lists, gmail-* until implemented
- [x] 2.12 (I) infra/80_webhooks.sh: skip gmail-push-sub until /webhooks/gmail exists; setWebhook on run.app first, then domain when cert is ACTIVE
- [x] 2.13 (F) Quiet-hours override accepts CM_ENV=demo with DEMO_IGNORE_QUIET_HOURS=1. Test: unit test in tests for quiet_hours
- [ ] 2.14 (B/K/I) Seed on Cloud SQL via cm-seed job with DEMO_USER_PASSWORDS from Secret Manager; one-off RAG index job
- [ ] 2.15 (M/G) P1: /webhooks/gmail route with gmail_oidc verification + gmail-watch-renew task
- [ ] 2.16 (I) Run the 10-step smoke test in DEPLOY_PLAN section 6; record results here

- [x] 2.17 (I) infra/90_telegram_webhook.sh, infra/README.md, DRY_RUN in vars.sh (change fix-deploy-blockers-infra; nothing run against GCP)
