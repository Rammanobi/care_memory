# CareMemory reliability playbook (research checked 23 Oct 2026)

Items marked ⚠ could not be confirmed against official documentation. Check them during the build.

## 1. Rate limits
- **LLM provider: OpenAI or DeepSeek (Claude/Gemini optional).**
  - Every provider limits requests per minute and tokens per minute.
  - A 429 response may include a `retry-after` header. Honour it.
  - A spend-cap error must **not** be retried. Mark the job failed and alert.
  - Set the SDK's `max_retries` on the client.
  - Add a LangChain `InMemoryRateLimiter` ⚠. It only works inside one process (one Cloud Run instance), so the **global** cap comes from the Cloud Tasks queue limits.
- **Telegram:**
  - At most about 1 message/sec per chat and about 30 messages/sec per bot overall.
  - A 429 response carries `retry_after` ⚠.
  - Throttle per chat inside the outbox worker.
- **Gmail:**
  - 6,000 quota units/min per user.
  - Costs: `messages.send` = 100 units, `messages.get` = 20, `history.list` = 2, `users.watch` = 100.
  - On errors, use truncated exponential backoff: wait min(2^n + jitter, 32–64 s), then give up.
- **Calendar:** 600 requests/min per user, 10,000/min per project. Same backoff.
- **Cloud Tasks queue (the global throttle):**
  - `maxDispatchesPerSecond` counts retries too.
  - `maxConcurrentDispatches` should stay at or below (LLM requests per minute ÷ LLM calls per job).
  - Retry settings: `maxAttempts`, `minBackoff`, `maxBackoff`, `maxDoublings`.
- **`tenacity`** for wrapped external calls: `wait_random_exponential(max=60)`, `stop_after_attempt(6)`, and retry only on retryable errors.

## 2. Doctor approval (human in the loop) when the doctor replies hours later
- LangGraph's `interrupt()` saves a checkpoint and pauses. Resume with `Command(resume=...)` on the **same `thread_id`**, even days later, from any Cloud Run instance.
- **When a node resumes, it re-runs from its beginning.** So:
  - Code that runs before `interrupt()` must be idempotent (upserts only).
  - Side effects go *after* the interrupt or in a separate node.
  - Never wrap `interrupt()` in try/except.
  - Never reorder interrupts or skip them conditionally.
  - The payload must be JSON-serialisable.
- Deep Agents version: `interrupt_on={"send_message": {"allowed_decisions": ["approve","edit","reject"]}}`.
  - Resume with `Command(resume={"decisions":[...]})`, one decision per action, in order.
  - Don't use `respond` to deny a tool that has side effects.
  - A sub-agent's interrupts surface in the parent graph.
- **The doctor queue lives in our own `approvals` table.** Don't build it by scanning checkpoints.
  - Columns: `thread_id`, `interrupt_id`, payload, tier, `created_at`, `expires_at`, `status`.
  - The interrupting node writes the row with an upsert keyed on `thread_id` + `interrupt_id`.
- **Timeouts and escalation** (nothing is built in):
  - A Cloud Scheduler sweep runs every 5–15 minutes.
  - Escalation steps: reminder → backup doctor → resume with an explicit `expired` decision.
  - Red-tier approvals escalate to the supervisor after 4 hours.
- **Approval by email reply:**
  - Put a single-use approval token in the Reply-To plus-address or in the subject.
  - When the reply arrives (via Gmail push → `history.list`), map the token back to its `thread_id`.
  - Verify the sender before acting.
- **Rejected drafts:** send the doctor's feedback back to the agent for a re-draft, at most twice. After that the doctor writes the message manually.

## 3. Async jobs and broken runs
- Pass `durability="sync"` on `invoke`/`stream`, so every step is checkpointed before the next one starts.
- **Resume after a crash:** `graph.invoke(None, {"configurable":{"thread_id":...}})`. Completed steps are loaded from the checkpoint and are not re-run.
- Wrap each side effect in a LangGraph `@task`, plus an idempotency key.
- Node retries:
  - `add_node(..., retry_policy=RetryPolicy(max_attempts=3, initial_interval=0.5, backoff_factor=2, jitter=True, retry_on=custom))`.
  - Write a custom `retry_on` that also retries 429s.
- Use `error_handler=` on nodes to route to a fallback or compensation node after retries are exhausted.
- **Cloud Tasks delivers at least once.**
  - Set `task_name = job_id` so duplicate creation is rejected.
  - Also guard in the database: `INSERT ... ON CONFLICT DO NOTHING`.
  - Read the attempt number from the `X-CloudTasks-TaskRetryCount` header.
  - Handlers can run for up to 30 minutes.
- **Cloud Run shutdown:** the instance gets SIGTERM, then SIGKILL 10 seconds later. The SIGTERM handler should stop taking work, flush, and mark the job `retrying`. Never rely on background CPU after the response has been sent.
- **Pub/Sub push** (used by Gmail):
  - Acknowledge fast with a 2xx, then enqueue the real work to Cloud Tasks.
  - Configure a dead-letter topic, `max_delivery_attempts` 5–100.
- **Transactional outbox:**
  - Write the outgoing message to the `outbox` table in the same database transaction as the state change.
  - A worker sends from the outbox using `FOR UPDATE SKIP LOCKED`.
  - Telegram has no idempotency key, so accept at-least-once delivery and store the returned `message_id`.
- **Jobs table:**
  - States: queued → running → waiting_human → retrying → succeeded / failed.
  - Columns: `thread_id`, `attempt`, `heartbeat_at`, `error`.
- **Sweeper** (Cloud Run Job, every 5 minutes):
  - A `running` job with a stale heartbeat is re-invoked with `None`.
  - A `waiting_human` job past its expiry is escalated.
  - Orphaned threads (no approval row) get their approval row rebuilt.
- **Sub-agent fails:** return the error to the parent as a `ToolMessage`. The parent then re-plans, skips, or flags the case for the doctor.

## 4. Observability
- LangSmith tracing via environment variables, tagging every run with `job_id`, `thread_id` and `patient_token` ⚠.
- Structured JSON logs (`severity`, `trace`, `job_id`), picked up by Cloud Logging and Error Reporting.
- Alerts on: `severity>=ERROR`, sweeper re-enqueues, queue age, and pending approvals older than 4 hours.

## 5. Failure → response table
| Failure | Detection | Automatic | Human fallback |
|---|---|---|---|
| LLM 429 | rate-limit error, `retry-after` header | SDK retry → RetryPolicy → Cloud Tasks backoff | alert if the queue ages; raise the provider tier |
| Spend cap reached | error code in the response | no retry; fail the job; pause the queue | raise the cap |
| LLM timeout | timeout error | retry ×3, then the fallback provider | listed for ops |
| Malformed LLM output | Pydantic validation fails | re-prompt once with the error, then a template | doctor reviews the raw output (flagged) |
| Telegram 429 | 429 with `retry_after` | wait, retry from the outbox, 1/sec per chat | Gmail fallback |
| Duplicate webhook | duplicate `update_id` / `historyId` | unique insert; ack 200 | — |
| Cloud Run killed mid-run | SIGTERM; stale heartbeat | sync durability + sweeper resumes with `None` | alert after N attempts |
| Database connections exhausted | "too many connections" error | bounded pool; cap max-instances | scale up Cloud SQL |
| Doctor never approves | `expires_at` passed | reminder → backup doctor → escalate | clinic admin |
| Doctor rejects | `reject` decision | re-draft, at most 2 times | doctor writes it manually |
| Gmail watch expired | renewal fails or no push for 24 h | daily renewal + `history.list` poll | re-authorise |
| Sub-agent fails | tool error | parent re-plans or skips | partial result flagged for the doctor |
| Partial notification send | unsent outbox rows | retry each row by `dedup_key` | manual resend |
| Cloud Tasks duplicate delivery | same `job_id` seen twice | idempotency key | — |
| Pub/Sub poison message | delivery attempt over the threshold | dead-letter topic | replay |
| Orphan waiting thread | no approval row | sweeper rebuilds the row | ops review |
