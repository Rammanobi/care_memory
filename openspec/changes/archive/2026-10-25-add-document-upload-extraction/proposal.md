## Why
Uploaded documents (txt, pdf, image) must become a doctor-reviewable DRAFT and, only after a doctor approves, memory events and searchable RAG chunks. Nothing clinical is written automatically.

## What Changes
- `cm/uploads/extract.py`: `extract_document_text(document_id) -> Extraction` (txt direct, pdf text layer via pypdf, images via governed vision; PII tokenised; never raises; scanned PDF flagged `needs_vision`, not rendered).
- `cm/uploads/review.py`: `create_review_item`, task `document_extract` (`docx-<id>`), `on_decided` / `on_approved` (events via existing repos, chunk + embed + index, idempotent), SSE `patient_document`, doctor notify category `document`.
- `cm/review/decide.py`: minimal post-commit hook `_after_commit` calling `on_decided` (decision itself unchanged).
- `cm/api/routers/tasks.py`: dispatch + task_type map for `document_extract`.
- `requirements.txt`: pypdf pin verified with `pip index versions`.

Out of scope: intake/storage/validation (other lane), portal and web routes, Telegram and Gmail adapters, real-data vision, rendering scanned PDFs.
Owning lane: G (review, tasks) with K (rag use). Implements UPLOAD_INGESTION.md sections 5-7. No `cm/contracts/` change.
