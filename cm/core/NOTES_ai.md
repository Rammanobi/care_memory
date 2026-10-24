# AI governor notes (lane A, change add-ai-budget-governor)
- budget.py: BudgetGovernor (check/record/state/policy), RunBreaker, pending_alerts, usage_numbers, UsageStore Protocol (+InMemory).
- retry.py: classify, call_with_retry, call_with_fallback, RateLimiter. llm.py: get_model(role). tokenize.py: tokenize, assert_clean. lifecycle.py: shutting_down() (a function), Heartbeat Protocol.
- 90% exactly is AMBER; RED is strictly over 90%. Reserve is locked by shrinking the spendable daily cap.
- Unknown models are priced with a pessimistic default; set CM_PRICE_TABLE_JSON.
- Not verified against real providers (no network). init_chat_model/init_embeddings signatures unchecked.
