## Why
Uploaded documents reach the doctor as approvals with `payload.subkind = document_review`. They must show on the Requests
page (like patient questions), stay off the Approvals queue, count in the Requests tiles, and never reach `/portal/*`.

## What Changes
- `readmodels.request_rows(..., include_documents=False)`: doctor callers pass True to include `document_review`
  rows; `RequestOut.document` (= `payload.data.document`, doctor-only), urgent-first then oldest ordering.
- `approvals_repo.queue(exclude_subkind)` accepts several subkinds; queue, per-tier counts, patient detail pending
  reviews, dashboard tiles and the ask-assistant approvals counts treat `document_review` like `patient_request`.
- `POST /requests/{id}/decision` unchanged (goes through `cm.review.decide`).
- Owning lane: G (Core API). Implements `docs/design/UPLOAD_INGESTION.md` section 8. No `cm/contracts/` change.

## Out of scope
Doctor file download route, decide.py hooks and the edit-without-body exemption (other lane), portal changes.
