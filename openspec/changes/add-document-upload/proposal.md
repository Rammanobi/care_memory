## Why
Patients and doctors need to send lab slips, prescriptions and chemist bills into CareMemory from Telegram, the patient
web app and Gmail. Today `cm/api/routers/ingest.py` is an empty skeleton and `cm/tools/vision_extract.py` produces a
draft that nothing stores or reviews. Uploads must be consented, validated, stored outside Postgres, reviewed by a
doctor before any clinical event is written, and indexed for patient RAG only after approval.

## What Changes
- New package `cm/uploads/` (`intake.py`, `storage.py`, `extract.py`, `review.py`) and repo `cm/store/uploads_repo.py`
  with the signatures frozen in `docs/design/UPLOAD_INGESTION.md` section 0.
- `accept_upload`: consent gate, magic-byte type allowlist (jpg/png/pdf/txt), 10 MB cap, 10-page cap, 5 uploads per
  patient per hour, per-patient content-hash dedupe, source-key idempotency (Telegram `file_unique_id`, Gmail
  message id + attachment id), filename sanitising, EXIF strip, original file in `data/uploads/<token>/<sha256>`
  (git-ignored) behind a `StoragePort` (GCS later).
- Lifecycle `received -> extracted|failed -> pending_review -> approved -> indexed | rejected` kept in
  `documents.extra.lifecycle`; `documents.status` stays in its existing CHECK values (rejected = `withdrawn`). No migration.
- Extraction: pypdf text layer, DeepSeek vision via `cm.tools.vision_extract` (mock data only), tokenised before any
  model call, budget-governed; the result is a draft only.
- Doctor review: approvals row `kind=needs_human`, `payload.subkind=document_review`, `data.document{...}`; SSE +
  doctor email reuse the doctor-question notification path with kind `document`.
- On approve: LabResult / Dispense / ContextNote via `events_repo` (idempotent keys), then doc chunks 400/60 with parents
  up to 1,500 into `cm.documents`/`cm.text_chunks`. On reject: withdrawn, nothing written.
- API: `POST /portal/documents` (multipart), `GET /portal/documents` with status, doctor `GET /requests` items carry
  `document`, `GET /documents/{id}/file` (doctor). Telegram photo/document handling (getFile + download in a task).
  Gmail attachments from allowlisted doctors. Templates `document_ack_v1` and `document_refused_v1` (EN/TE).

## Out of scope
GCS storage implementation, OCR beyond vision, scanned-PDF rendering when `pypdfium2` is absent, Supporter uploads,
orphan-file sweeper, `0009_rag_v2` doc_type values (RFC later). No edit to `cm/contracts/` (API models live in
`cm/api/portal_models.py`).

## Owning lanes
A (core: `cm/uploads/`, `cm/store/uploads_repo.py`), G (API + `cm/review/decide.py` hook), F (Telegram), M (Gmail),
K (templates, chunking reuse), H2/H1 (web upload + doctor document card), I (`.gitignore`, requirements verification).
Design: `docs/design/UPLOAD_INGESTION.md`; RAG rules from `docs/design/RAG_STRATEGY_v2.md` rows 7 and 9.
