# AI rate limits and spend caps: research and what to add

Research date: 24 Oct 2026. Sources are mostly third-party guides and they disagree on exact numbers. Treat every number as "check the provider dashboard", not as fact.

## 1. What the research says
**OpenAI**
- Limits are per organisation and per model, counted as requests per minute (RPM) and tokens per minute (TPM). Going over gives HTTP 429. Higher limits unlock as cumulative payments grow (guides list steps from about $5 up to $1,000). One source reports an Oct 2026 tier rename (Build/Launch/Grow); others still show the older five tiers. Unconfirmed. ([inference.net](https://inference.net/content/openai-rate-limits-guide/), [requesty.ai](https://www.requesty.ai/blog/rate-limits-for-llm-providers-openai-anthropic-and-deepseek), [layer3labs](https://www.layer3labs.io/guides/openai-api-usage-tiers))
- Monthly usage limits exist per organisation. Budget alerts and per-project limits were not confirmed by my search; check the dashboard. ([bswen](https://docs.bswen.com/blog/2026-03-10-openai-api-rate-limits-explained/))

**DeepSeek**
- Prepaid balance. When it hits zero you get HTTP 402: the key is valid, but nothing works until you top up. Retrying a 402 never helps. ([error codes](https://deepseek-usa.ai/docs/deepseek-error-codes/), [guide](https://deepseekv4pro.com/guides/deepseek-error-codes-guide))
- Throttling is described as concurrency-based and load-dependent, with no fixed published per-minute cap. Extra API keys do not add capacity. 429 = too fast, 503 = server overloaded. ([fast.io](https://fast.io/resources/deepseek-rate-limit/), [developersdigest](https://www.developersdigest.tech/blog/ai-api-rate-limit-retry-guide-2026))
- Our own rule already says DeepSeek is refused when `CM_DATA_CLASS=real`.

**Cost-control patterns that keep coming up** ([gravitee](https://gravitee.io/corpus/gen-246/zedriv-gt3/cost-controls-for-llms.html), [glukhov](https://glukhov.org/llm-architecture/cost-optimization/cost-optimization-for-llm-systems/))
- Count tokens before and after each call; throttle, block or reroute to a cheaper model at a threshold.
- Circuit breaker for runaway agents (tool-call budget).
- Pair failover with retry limits, backoff and idempotency keys, or retries multiply spend.
- Prompt caching for long system prompts; batch API (about 50% cheaper) for non-urgent work.

## 2. What we already have (do not rebuild)
- `task_runs` columns `tokens_in`, `tokens_out`, `cost_usd`, `error_class` (`spend_cap` is one class).
- Rule: spend-cap and auth errors are never retried or failed over (INTEGRATION_DECISIONS C28; RELIABILITY_PLAYBOOK row "Spend cap reached": no retry, fail the job, pause the queue).
- Cloud Tasks queue rates (`agent-runs`, `resumes` 2/s, `outbound` 5/s) and `cm.core.retry` honouring retry-after.
- All model access goes through `cm.core.llm.get_model(...)`: one place to enforce caps.

## 3. What to add (the gap)
| # | Add | Where | Why |
|---|---|---|---|
| 1 | **Budget governor** `cm/core/budget.py`: estimate tokens before each call, record actuals after; keep running totals per day, per task type and per patient | wraps `get_model` in `cm/core/llm.py` | One choke point; feeds the meter |
| 2 | **Four caps**: global daily USD, per-task USD, per-patient-per-day tokens, and a locked demo-day reserve that cannot be spent before the final round | `.env` plus a `budget_limits` row | A loop cannot eat the demo budget |
| 3 | **Three states**: GREEN under 70%; AMBER 70-90% (cheaper worker model, skip optional sub-agents, shorter drafts); RED over 90% (template-only mode: no LLM drafting, rules and approved templates still work) | governor | The system degrades, it does not die |
| 4 | **Circuit breaker**: max tool calls and max sub-agent depth per run; a trip stops the run and creates a "needs a human" item for the doctor | `cm/agents/runtime.py` | Runaway-agent protection |
| 5 | **Provider-limit handling**: token-bucket limiter for RPM/TPM; on 429 honour retry-after; on 503 back off with jitter; on 402 or spend-cap stop, set `error_class=spend_cap`, flip state to RED, alert | `cm/core/retry.py` | Matches the provider behaviour above |
| 6 | **Caching and batching**: cache static prompt prefixes; run the nightly job through the batch API when not time-critical; cache embeddings by content hash | narrator, nightly job, RAG | Cheapest real savings |
| 7 | **Demo-safe mode**: cassette replay (already planned) when state is RED or Wi-Fi fails | `cm/sim/cassette.py` | The demo never depends on credits |
| 8 | **Usage and caps panel** in the admin UI (preview: `ui_previews/usage_caps_panel.png`) | `web/src/pages/Admin/` | Cap, burn rate and state at a glance |
| 9 | **Alerts** to the owner at 70%, 90% and on any 402; system messages allow-listed past the doctor gate | outbox system kinds | You hear before the cap hits |

## 4. Numbers to set before the event (owner)
- A monthly cap in each provider dashboard, set to the amount you are willing to lose; use keys with spend limits.
- Daily budget = (total budget minus demo reserve) divided by build days.
- Keep at least 25% untouched until H30 as the demo reserve.
- Never send real patient data through DeepSeek.

## 5. Tasks to add to WORK_BREAKDOWN
- Phase 3, lanes A/E: governor plus circuit breaker (about 3 h, Sonnet).
- Phase 4, lane I: alerts and env config (about 1 h, Haiku).
- Phase 7: RED-mode drill (cut credits on purpose, confirm template-only mode works).
- Phase 8: usage panel on screen in the last rehearsal.

## 6. Unverified, check first
Exact RPM/TPM per tier; whether OpenAI offers per-project hard limits and alerts; DeepSeek's current concurrency numbers; current batch and cache discounts.
