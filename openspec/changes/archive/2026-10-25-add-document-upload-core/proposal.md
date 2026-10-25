## Why
Patients and their channels (portal, Telegram, Gmail) need one safe way to hand the clinic a document (lab slip, photo, PDF, note).

## What Changes
- `cm/uploads/{storage,validate,intake}.py` and `cm/store/uploads_repo.py`: storage port with LocalStorage, magic-byte validation, `accept_upload` (consent, 5 per hour wall-time rate limit, per-patient content dedupe, origin idempotency, never raises).
- `POST /portal/documents` (patient only, streamed size cap) and `status` on `GET /portal/documents`.
- Template `upload_ack_v1` (EN/TE) and `data/uploads/` in `.gitignore`.
- No migration: lifecycle is `cm.documents.extra.upload_state`; `documents.status` stays `active`; `content_hash` is sha256 over patient token plus bytes; the original is referenced by `extra.storage_uri` (gcs_uri must be gs://).

## Out of scope
Extraction, review, channel intake, web UI (other lanes). No `cm/contracts/` change.

## Owning lane
A (store, uploads) + G (portal route). Implements docs/design/UPLOAD_INGESTION.md interface.
