## 1. Telegram
- [x] 1.1 `tg_http.py`: getFile, streamed download with byte cap, retry through `cm.core.retry`, token-free errors (tests: `test_tg_upload.py` client section)
- [x] 1.2 `tg_upload.py` + `tg_inbound.py`: photo/document intake, caption routing, one reply (tests: `test_tg_upload.py`)
- [x] 1.3 `confirmations.yaml` `upload_rejected_v1` + `REQUIRED_KINDS` (tests: `test_templates.py`)
- [x] 1.4 `adapters_pg.build_deps` wiring + `cm/store/upload_channels_repo.py`

## 2. Gmail
- [x] 2.1 `fetch_attachment` on `ports_gmail.py`, `fakes_gmail.py`, `gmail_google.py`; `gmail.normalize_message` attachments (tests: `test_gmail_attach.py`)
- [x] 2.2 `gmail_attach.py`: allowlist, authentication, patient code, accept_upload, dispatch (tests: `test_gmail_attach.py`)

## 3. Verify
- [x] 3.1 Offline unit tests, ruff, `openspec validate`
- [x] 3.2 Live check handed to the owner (real Telegram photo and PDF, real Gmail attachment)
