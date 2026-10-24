## 1. Store
- [x] `approvals_repo.set_research` (tier only rises), `stream_repo.publish`, outbox `inbox_for` and `sent_today` (tests/integration/test_question_routing.py)
## 2. Capture and task
- [x] `cm/channels/question_routing.py`, `adapters_pg.PgMessages.save`, `/portal/requests`, `tasks.py` dispatch (test_question_routing.py)
## 3. Reply
- [x] `decide._reply_meta`, `tg_sender` question_reply, `tg_client`/`tg_http` reply_to_message_id (tests/unit/channels/test_question_reply_sender.py)
## 4. API fields
- [x] `portal_models`, `readmodels.request_rows`, `portal.py` (test_no_research_fields_in_any_portal_response)
