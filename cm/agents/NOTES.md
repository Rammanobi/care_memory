# cm/agents NOTES: live run, PT-0142 (task 1.8)

Live DeepSeek run via `python -m cm.jobs.nightly --patient PT-0142 --live` (ORCHESTRATOR=deepseek:deepseek-v4-pro,
WORKER=deepseek:deepseek-flash). Seeded DB on 5433 was NOT reset.

## Result
- Card draft approval `75e1cc0d-2c3b-4330-8a1e-89309ca22884`: status pending, tier amber, kind card, thread
  `nightly_patient:P-0142:59:6b846f87`. Visible in GET /review/queue (checked with the sim clock pinned; queue
  hides rows created after `clock.now()`). Never auto-sent: only `cm.review.decide` can release it.
- Orchestrator flow: write_todos, get_patient_snapshot, compute_features, list_events, write_card, submit_for_review
  (interrupt) then resume "approve" (releases the pending draft only). Checkpointer: Postgres. Budget state GREEN.
- Final card (model-written, 5 sentences kept, source=model) with E/B citations.

## Numbers
- Whole orchestrator task `nightly-P-0142-d59` (cumulative over 3 attempts, 2 of which aborted on caps, see below):
  tokens in 74,951, out 5,136, cost 0.9036 USD. The completing run took about 49 s wall.
- Narrator alone (write_card, ORCHESTRATOR model, clean probe): latency 30.4 s, tokens in 647 / out 2,656,
  cost 0.0862 USD, kept 3 / cut 2 (both cut with reason `no_ref`).
- ai_smoke: ORCHESTRATOR 12.5 s cold, WORKER 1.4 s.

## Findings / open issues
1. Cap blocks on the first attempts, not bugs: the seeded demo spend was already 5.30 USD today (cap 3.75, RED,
   event 53.5 of 25 USD), then per-task 0.25 USD and per-patient 60k tokens. The live run used process-only env
   overrides (CM_BUDGET_DAILY_USD=20, CM_BUDGET_EVENT_USD=200, CM_BUDGET_TASK_USD=1.0, CM_BUDGET_PATIENT_TOKENS=400000);
   `.env` untouched. Per-task 0.25 USD is too small for the deep-agent flow on the pro model (about 0.3 USD per run).
2. Narrator cuts: the model sometimes writes citations as `[E-a, E-b]` (comma inside one bracket). cite_or_cut then
   sees no ref (`no_ref`). A prompt line or tolerant ref parser would keep these (cm/validator/cite_or_cut.py).
3. The stored task_run totals do not split per attempt; re-running with --force reuses the same thread, so the
   resumed run replayed prior state (tool_calls empty in its summary, approval from the earlier attempt).

## Budget alerts
GET /admin/usage/caps now returns `alerts` (AMBER at >=70%, RED above 90% or on a billing error), read-only so
the once-per-day owner send in `budget.pending_alerts` is not consumed. Code: cm/api/routers/ops.py; test:
tests/unit/ai/test_caps_alerts.py.
