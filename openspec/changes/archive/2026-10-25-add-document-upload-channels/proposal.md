## Why
Patients and doctors already use Telegram and email. Documents (lab reports, prescriptions, discharge notes) must be
able to arrive on those channels and land in the same intake as portal uploads, without a new trust path.

## What Changes
- Telegram (lane F): `tg_inbound` handles photo and document messages from bound, consented patient chats via the new
  `tg_upload.py`; `tg_http.py` gains `get_file`, `download_file`, `fetch_file` (sync httpx, retry via `cm.core.retry`,
  byte cap, token-free errors); `tg_text.template_text`; template `upload_rejected_v1` (EN/TE) in `confirmations.yaml`
  (the core agent adds `upload_ack_v1`); `adapters_pg.build_deps` wires the file fetcher and a person-token lookup.
- Gmail (lane M): `fetch_attachment` on the Gmail port, fake and `GoogleGmailApi`; `normalize_message` lists
  attachments; new `gmail_attach.py` (allowlist + authentication + patient code + `accept_upload`).
- New `cm/store/upload_channels_repo.py` (person token and doctor-by-email lookups).
- Tests: `tests/unit/channels/test_tg_upload.py`, `tests/unit/gmail/test_gmail_attach.py`, `REQUIRED_KINDS` gains
  `upload_rejected`.

## Out of scope
The intake itself (`cm/uploads/*`), extraction, the portal and web UI, any patient-facing email, auto-approval.
Moving the Telegram download out of the webhook request (the local poller runs handlers in a worker thread).

## Owning lane
F (Telegram) and M (Gmail), with the content lane's template file. No change to `cm/contracts/`.
Implements the channel part of `docs/design/UPLOAD_INGESTION.md`.
