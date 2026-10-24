## 1. Implementation
- [x] 1.1 Decrypt name via cm/store (`channels_repo.first_name_from_vault`, `reminder_targets` returns `first_name` only, never `enc_name`); tests/unit/store/test_channels_names.py, tests/unit/jobs/test_reminders_names.py, tests/integration/test_telegram_pg.py (written, not run: it resets the live Ravi binding)
- [x] 1.2 Template fallback test (`reminders.greeting_name`: absent or banned-term name falls back to "friend")
- [x] 1.3 Check no PII reaches an LLM (reminders are template-only, no LLM call; only the first word, letters only, reaches the message)
