## 1. Fixes
- [x] 1.1 portal request with banned words returns 201 receipt (`cm/api/routers/portal.py`); test `test_patient_typing_a_banned_word_is_not_an_error`
- [x] 1.2 robust `code` filter (`cm/api/readmodels.py`); test `test_sql_injection_in_query_strings_and_paths`
- [x] 1.3 DataError -> 422 (`cm/api/main.py`); test `test_null_bytes_are_rejected_not_500`
- [x] 1.4 cursor clamp (`cm/api/deps.py`, review/patients routers); test `test_paging_and_numeric_params_never_500`
- [x] 1.5 reminder time pattern (`cm/api/portal_models.py`); tests `test_reminder_time_*`
- [x] 1.6 one banned-word list (`cm/api/suppress.py`, `cm/router/banned.py`); tests `test_both_banned_filters_agree_on_hard_cases` and gate tests
- [x] 1.7 case-insensitive /stop (`cm/channels/tg_inbound.py`); test `test_stop_then_everything_goes_quiet...`
- [x] 1.8 Ask-box quiet answer verified (`cm/api/routers/query.py`); test `test_ask_box_never_echoes_secrets_or_pii_and_never_sends`
