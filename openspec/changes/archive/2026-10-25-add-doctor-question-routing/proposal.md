## Why
A patient question (Telegram free text or the web "message to my care team") reached the doctor only as a bare request. The doctor had no research brief, no live notification, and the approved reply was sent as an unthreaded message that counted against the 3-per-day cap and waited out quiet hours even for urgent questions.

## What Changes
- A question request now carries `data.origin` (channel, Telegram chat and message id, clean excerpt) and `data.research` (status `pending`), and enqueues task `question_research` (task id `qresearch-<approval_id>`).
- The task runs `research_question` (fake model unless `CM_QUESTION_RESEARCH_LIVE=1`; a local stub that stays `pending` while `cm/agents/question_research.py` is absent), stores the brief via `approvals_repo.set_research`, raises (never lowers) the tier for urgent triage, publishes an SSE `review` event `patient_question`, and calls `notify_doctor_new_question` (guarded).
- `decide()` writes `meta.reply_to {approval_id, question_excerpt, telegram_message_id}` on the outbox row of a reply to a question. The Telegram sender treats it as the allow-listed logical kind `question_reply`: threaded with `reply_to_message_id`, first line quotes the question (EN/TE), exempt from the daily cap and not counted by it, bypasses quiet hours only when urgent. Consent, binding, banned-term and rate-limit checks still apply.
- `/portal/requests` gains `question_status` (`waiting`, `answered`, `closed`) and `answered_at`; `/portal/inbox` gains `in_reply_to {approval_id, question_excerpt}`. Doctor `/requests` gains `tier, priority, source, origin, research, answered_at`.
- Out of scope: research agent (`cm/agents/question_research.py`), doctor email (`cm/channels/doctor_notify.py`), web UI, RAG.
- Owning lane: F (channels) with G (API, decide) glue. No frozen contract edited: the outbox DB kind stays `ai_message` (no new CHECK value) and the task runs under task_runs type `investigate`.

## Decisions
- A declined question is `closed` for the patient (no reply is coming), never silently `waiting`.
- Urgent = `data.priority == "urgent"` or tier red.
