## 1. Core (lane A)
- [ ] 1.1 `cm/uploads/storage.py`: `StoragePort`, `LocalStorage` (atomic write, 0600, path `<tok>/<sha>`), `get_storage()`; test `tests/test_uploads_storage.py`
- [ ] 1.2 `cm/store/uploads_repo.py`: insert/get/set_lifecycle (transition guard)/set_doc_type/list/count_recent/find_by_source_key; test `tests/test_uploads_repo.py`
- [ ] 1.3 `cm/uploads/intake.py`: `accept_upload` checks in design §4 order (consent, size, magic bytes, pages, EXIF, rate, dedupe, store, enqueue); test `tests/test_uploads_intake.py` (design §11 cases 1-9)
- [ ] 1.4 `cm/uploads/extract.py`: txt / pypdf / vision paths, tokenise, budget + real-data refusal to `failed`; test `tests/test_uploads_extract.py` (cases 10-12)
- [ ] 1.5 `cm/uploads/review.py`: `create_review_item` (payload golden), `on_approved`, `on_rejected`, apply + index tasks; test `tests/test_uploads_review.py` (cases 13-15)
- [ ] 1.6 Add fakes (`FakeStorage`) and task handlers `upload-extract`, `upload-apply`, `upload-index`

## 2. API + review (lane G)
- [ ] 2.1 `POST /portal/documents` multipart and `GET /portal/documents` status in `cm/api/routers/portal.py`; models in `cm/api/portal_models.py`; test `tests/test_api_portal_documents.py`
- [ ] 2.2 `RequestOut.document`, `readmodels.request_rows` includes `document_review`; `/review/queue` excludes it; test `tests/test_api_requests_documents.py`
- [ ] 2.3 `cm/review/decide.py`: call `on_approved`/`on_rejected` for `subkind=document_review`; allow edit without body; test `tests/test_review_document.py`
- [ ] 2.4 `GET /documents/{id}/file` doctor-only, attachment + nosniff, audit

## 3. Telegram (lane F)
- [ ] 3.1 `tg_http.py` + `tg_client.py`: `get_file`, `download_file` with retry; fake equivalents
- [ ] 3.2 `tg_inbound._on_message`: photo/document enqueue `tg-upload-<update_id>`; task calls `accept_upload` and sends template; test `tests/test_tg_upload.py`

## 4. Gmail (lane M)
- [ ] 4.1 `GmailApi.get_attachment` port + google adapter + fake; allowlisted sender + `P-xxxx` subject → `accept_upload`; test `tests/test_gmail_attachments.py`

## 5. Content (lane K)
- [ ] 5.1 `document_ack_v1`, `document_refused_v1` EN/TE in `cm/router/templates/confirmations.yaml`; `make banned-terms`

## 6. Web (lanes H2/H1)
- [ ] 6.1 Patient app upload control (accept jpg/png/pdf/txt, 10 MB client check, status chip)
- [ ] 6.2 Doctor Requests card for `document` (fields + confidence, edit, approve/reject, open original)

## 7. Infra (lane I)
- [ ] 7.1 `.gitignore` adds `data/uploads/`; verify `pypdf`, `pillow`, `python-multipart` pins install
- [ ] 7.2 `npx openspec validate add-document-upload`
