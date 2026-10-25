## 1. Tests
- [x] 1.1 `tests/integration/test_upload_edge.py` (hostile files, filenames, consent, isolation, injection, PII, banned terms, review paths, storage, budget, portal, Telegram, Gmail)
- [x] 1.2 `tests/property/test_upload_props.py` (hypothesis)
- [x] 1.3 `tests/concurrency/test_upload_concurrency.py`

## 2. Fixes (each proven by the tests above)
- [x] 2.1 `cm/uploads/validate.py`: whole-body markup, PDF active content, flate and pixel bombs, Telugu names
- [x] 2.2 `cm/store/uploads_repo.py` `lock_patient` + `cm/uploads/intake.py` (race-safe dedupe and rate limit)
- [x] 2.3 `cm/uploads/intake.py` `has_upload_consent` + `cm/uploads/review.py` consent re-check at approval
- [x] 2.4 `cm/api/body_limit.py` + `cm/api/main.py` (413 before the body is buffered)
- [x] 2.5 `cm/api/routers/portal.py` `indexed` status
- [x] 2.6 `cm/channels/tg_upload.py` consent before download
- [x] 2.7 `cm/channels/gmail_reply.py` single-address From

## 3. Verify
- [x] 3.1 `pytest tests/integration/test_upload_edge.py tests/property/test_upload_props.py tests/concurrency/test_upload_concurrency.py` (109 passed)
- [x] 3.2 `pytest tests/unit/uploads/test_validate.py tests/unit/channels/test_tg_upload.py tests/unit/gmail` (172 passed)
