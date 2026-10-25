# Document upload ingestion (design, OpenSpec change `add-document-upload`)
## 0. Signatures (FROZEN for parallel builders; read these first)
```python
# cm/uploads/intake.py                                                       (lane A+G core)
Source = Literal["telegram", "web", "gmail"]
@dataclass(frozen=True)
class UploadResult: document_id: UUID | None; status: str; duplicate: bool; reason: str | None
def accept_upload(*, patient_token: str, source: Source, filename: str, mime: str, data: bytes,
                  uploader_person_id: UUID | None = None, origin: dict | None = None) -> UploadResult
# cm/uploads/storage.py
class StoragePort(Protocol):
    def put(self, patient_token: str, sha256_hex: str, data: bytes) -> str: ...   # returns uri, idempotent
    def get(self, uri: str) -> bytes: ...
    def delete(self, uri: str) -> None: ...
class LocalStorage(StoragePort): def __init__(self, root: Path = Path("data/uploads")) -> None  # file://...
class GcsStorage(StoragePort): ...                     # later; gs://$PROJECT-cm-docs/uploads/<tok>/<sha>
def get_storage() -> StoragePort                       # CM_UPLOAD_STORAGE=local|gcs (default local)
# cm/uploads/extract.py
@dataclass
class ExtractField: name: str; value: str | float | int | None; confidence: float
@dataclass
class Extraction: document_id: UUID; doc_kind: str; method: str; pages: int; text: str; fields: list[ExtractField]; text_excerpt: str; low_confidence: list[str]; model: str | None; error: str | None
def extract_document_text(document_id: UUID) -> Extraction
# cm/uploads/review.py
def create_review_item(document_id: UUID) -> UUID          # approval_id; idempotent
def on_approved(approval_id: UUID) -> None                  # hook called by cm/review/decide.py
def on_rejected(approval_id: UUID) -> None
# cm/store/uploads_repo.py (the only SQL)
def insert_upload(row: dict, *, conn=None) -> tuple[UUID, bool]          # (document_id, inserted)
def get_upload(document_id: UUID, *, conn=None) -> dict | None
def set_lifecycle(document_id: UUID, state: str, *, patch: dict | None = None, conn=None) -> None
def set_doc_type(document_id: UUID, doc_type: str, *, conn=None) -> None
def list_uploads(patient_token: str, as_of: datetime, *, conn=None) -> list[dict]
def count_recent(patient_token: str, since: datetime, *, conn=None) -> int
def find_by_source_key(source_key: str, *, conn=None) -> UUID | None    # idempotency lookup
```
`UploadResult.status` is the lifecycle state reached (`received`, or the existing state when duplicate) or `refused`.
`reason` (when refused): `no_consent | unknown_patient | bad_type | too_large | too_many_pages | rate_limited | empty | storage_failed`.

## 1. Scope and non-negotiables
Patients and doctors send documents (lab slip, prescription, chemist bill, letter) through Telegram (photo or
document), the patient web app (multipart upload) and Gmail (attachment from a `DOCTOR_EMAIL_ALLOWLIST` sender).
Nothing clinical is written automatically: extraction gives a DRAFT; only a doctor approval (through
`cm/review/decide.py`, rule 14) writes events and indexes chunks. Patient-facing replies are approved templates only;
contents are never echoed; no TB or drug names (rule 5). PII is tokenised before any model call (rule 10). DeepSeek
vision runs on mock data only (`llm.py` already refuses images and `deepseek:` when `CM_DATA_CLASS=real`).

## 2. Pipeline
```
channel adapter ──> accept_upload ──(enqueue upload-extract-<doc>)──> extract_document_text
  (TG / web / Gmail)   consent, validate, hash,                         pypdf | vision | txt
                       store file, documents row                              │
                                                            create_review_item (needs_human/document_review)
                                                            + SSE "review" + doctor email (dry-run/send)
doctor approve ──> decide.py ──> on_approved: events via events_repo  ──(enqueue upload-index-<doc>)──> chunks
doctor reject  ──> decide.py ──> on_rejected: status withdrawn, file kept until retention_until
```
Webhooks never download or extract inline (rule 8): Telegram and Gmail enqueue a task; the task calls `accept_upload`.
The web route calls `accept_upload` inline (bytes already in the request, <= 10 MB) and enqueues extraction.

## 3. Storage and the `cm.documents` row (no migration)
| Need | Column / place | Note |
|---|---|---|
| Original file | `data/uploads/<patient_token>/<sha256>` (git-ignored: add `data/uploads/` to `.gitignore`) | write `tmp` then `os.replace`; mode 0600; no extension, never executed |
| Pointer | `gcs_uri` only for `gs://` (CHECK `LIKE 'gs://%'`); local uri in `extra.storage_uri` (`file://data/uploads/...`) | GcsStorage later fills `gcs_uri`; readers use `gcs_uri or extra.storage_uri` |
| Dedupe | `content_hash = sha256(b"upload:" + token + b":" + file_bytes)` (global UNIQUE, so per-patient scope) | `extra.file_sha256` = sha of raw bytes, also the storage key |
| Type | `doc_type`: lab_report→`lab`, prescription/chemist_bill→`prescription`, other→`checkin` (patient) or `email` (Gmail) | real kind in `extra.doc_kind`; set at intake as `checkin`/`email`, final on approve |
| Who | `source` (telegram/web/gmail), `author_role` patient/doctor/lab, `consent_id` (required by CHECK) | uploader person in `extra.uploader_person_id` |
| Time | `occurred_at` = upload time (doctor may set report date on approve), `recorded_at` = `clock.now()` | as_of reads filter `recorded_at <= as_of` |
| Sensitivity | `sensitivity='normal'` default; doctor may set `hiv_adjacent`/`mental_health` on approve | copied onto chunks |
| Lifecycle | `extra.lifecycle` + `extra.lifecycle_at` (map below) | `status` CHECK only allows active/superseded/withdrawn |
| Retention | `retention_until` = recorded_at + 3 years (consent withdrawal: withdrawn + file delete job) | |
| Idempotency | `extra.source_key`: `tg:<file_unique_id>`, `gmail:<message_id>:<attachment_id>`, `web:<sha256>` | `find_by_source_key` first; then content_hash |

Lifecycle mapping (no CHECK change):
| `extra.lifecycle` | `documents.status` | Meaning |
|---|---|---|
| `received` | active | stored, validated, consent ok, extraction queued |
| `extracted` | active | draft in `extra.extraction` (tokenised text excerpt, fields, confidence) |
| `pending_review` | active | approvals row exists (`extra.approval_id`) |
| `approved` | active | events written (`extra.event_ids`) |
| `indexed` | active | chunks written (`extra.chunk_count`) |
| `rejected` | withdrawn | no events, no chunks |
| `failed` | active | extraction failed after retries; still goes to review with `error` (doctor reads the file) |
`active` before approval is safe: retrieval reads `cm.text_chunks` only, and chunks exist only after `indexed`.
Allowed transitions: received→extracted|failed→pending_review→approved→indexed, pending_review→rejected.
`set_lifecycle` refuses any other transition (raise `LifecycleError`), which also makes task re-runs no-ops.

## 4. `accept_upload` order of checks (cheap first, nothing stored on refusal)
1. Resolve patient by token (`unknown_patient`). 2. Consent: `consent.latest_consent_id(patient_person_id, src, now)`
   with `src` telegram→`telegram`, web→`web`, gmail→`gmail` then `portal` fallback for doctor mail; None → `no_consent`,
   audit `upload.refused`, return. 3. `len(data)==0` → `empty`; `> 10 MB` → `too_large`.
4. Magic bytes decide the type (extension and `mime` are hints only): `%PDF-` pdf, `\x89PNG\r\n\x1a\n` png,
   `\xff\xd8\xff` jpg, txt = valid UTF-8 with no NUL and <= 1 MB. Anything else → `bad_type` (zip, docx, html, svg,
   heic, exe). 5. PDF: `pypdf.PdfReader(strict=False)`, pages > 10 → `too_many_pages`; encrypted → `bad_type`.
   Images: Pillow `Image.open` with `MAX_IMAGE_PIXELS=40e6` (decompression-bomb guard), re-encode to strip EXIF
   (store the stripped bytes; hash is of the stripped bytes). 6. Rate: `count_recent(token, now-1h) >= 5` → `rate_limited`.
7. Idempotency: `find_by_source_key` or content_hash hit → `duplicate=True`, return existing id + state.
8. `storage.put` (retry 3x on OSError; failure → `storage_failed`, no row) then `insert_upload` (one transaction with
   the audit row `upload.received`). 9. `tasks.enqueue("agent-runs", f"upload-extract-{document_id.hex}", ...)`.
Filename: kept only as `extra.filename` after sanitising (basename, NFC, `[^\w.\- ]`→`_`, max 80 chars); never used
as a path. PDF JavaScript, embedded files and forms are never executed (pypdf text extraction only).

## 5. Extraction (`extract_document_text`, task `upload-extract-<doc>`)
| Type | Method | Cost |
|---|---|---|
| txt | decode UTF-8 | free |
| pdf with text layer | `pypdf` `page.extract_text()` per page | free |
| pdf without text (< 20 chars/page) | render with `pypdfium2` (dev-only today) to PNG at 150 dpi, max 3 pages, then vision; if not installed: `method="none"`, doctor reads the file | 1 vision call/page |
| png / jpg | `cm.tools.vision_extract.extract_document(bytes, doc_type, mime=...)` | 1 vision call |
Vision doc_type guess: `prescription` unless the PDF/text hints `lab`/`report` (keyword, no LLM). Text from pypdf is passed
through `cm.core.tokenize.tokenize()` before it is stored in `extra.extraction` or sent to any model; patient names
are registered with `register_names`. `get_model("VISION")` goes through the budget governor; `BudgetExceeded`,
`TemplateOnlyMode` or `ModelConfigError` (real data) → `method="none"`, `error=<class name>`, lifecycle `failed`,
no retry. Transient provider errors are retried inside `vision_extract` (3 attempts); the task itself has 6 attempts.
Fields: flatten `DraftExtraction.data` to `[{name:"lab_values[0].value", value, confidence}]`; `text_excerpt` = first
300 chars of tokenised text. Then call `create_review_item`. Per-patient cap: 5 vision calls per hour (= upload cap).

## 6. Doctor review item (approvals payload, exact)
`approvals_repo.upsert` with `thread_id=f"upload-{document_id}"`, `interrupt_id="document_review"`, `graph_kind="deep"`,
`kind="needs_human"`, `tier="amber"` (`green` for `other`), `due_at=+12h`, `expires_at=+7d`:
```json
{"audience": "doctor", "title": "Document to review: lab_report", "channel": "console", "recipients": [],
 "body": "", "subkind": "document_review",
 "data": {"kind": "document", "text": "Document received via telegram", "refs": [], "source": "telegram",
   "origin": {"channel": "telegram", "telegram_chat_id": "...", "telegram_message_id": 0},
   "document": {"id": "<uuid>", "filename": "lab_slip.pdf", "mime": "application/pdf", "size": 182344,
     "pages": 1, "status": "pending_review",
     "extraction": {"doc_type": "lab_report", "method": "pypdf",
       "fields": [{"name": "lab_values[0].value", "value": "negative", "confidence": 0.82}],
       "text_excerpt": "...tokenised...", "low_confidence": ["dates[0]"], "error": null}}}}
```
`audience="doctor"` so the banned-term check in `decide._validate` does not block drug names in the draft (doctor-only).
The doctor approves with `edited` = `{"doc_kind": "lab_report", "fields": [...corrected...], "report_date": "2026-10-20",
"sensitivity": "normal"}`; `edit` with no body change is allowed for this subkind (G adds the exemption in `_final_body`).
Notification: reuse `question_routing._tell_doctor` pattern: `stream_repo.publish("review", {"type": "document",
"kind": "document", "approval_id", "patient_code", "category": "document", "priority": "routine"})` and
`notify_doctor_new_question(approval_id, patient_code=..., category="document", priority="routine",
question_excerpt="New document uploaded (lab_report)", channel=source)`; never the content. Both never raise.

## 7. On approval (`on_approved`, called by `decide.py` after commit for `subkind == "document_review"`)
Enqueues `upload-apply-<doc>` (side effects outside the decision transaction, idempotent):
| doc_kind | Events (via `events_repo.append_event`, idempotency key `upload:<doc>:<i>`) |
|---|---|
| lab_report | `LabResult{test (mapped, else other), result, report_date, upload_sha256, extraction_confidence}` per approved lab value |
| chemist_bill | `Dispense{tablets, days_supply, bill_no}` per line with a quantity |
| prescription / other | `ContextNote{origin:"doctor", kind:"document", text_tokenised: summary}` (also feeds `/portal/documents`) |
Every approval also writes one `ContextNote{kind:"document", id, title, doc_kind, summary}` so the patient list shows it
(title/summary are neutral, banned-term checked). `source` = upload source mapped to events CHECK (`web`→`portal`),
`reporter_mode="record"`, `consent_id` from the document. Then `set_lifecycle(approved)` and enqueue
`upload-index-<doc>`: tokenised text → `cm.rag.chunk.chunk_text(size_tokens=400, overlap_tokens=60, strategy="dynamic")`
children, parent chunks up to 1,500 tokens (heading-aware for long PDFs, RAG_STRATEGY_v2 row 9), prescription free
text = 1 chunk, no structured fields embedded (row 7). Rows via `chunks_repo.upsert_chunk` with `document_id`,
`patient_token`, `doc_type`, `sensitivity`, `consent_id`, `occurred_at`, `extra{section,page,chunk_kind:"doc"}`;
embeddings through `get_model("EMBEDDING")` when configured, else NULL (FTS fallback). Then `indexed`.
`on_rejected`: lifecycle `rejected`, `status='withdrawn'`, no events; the doctor's reason is a `ContextNote{kind:rejection_reason}`.

## 8. API routes (lane G)
| Route | Role | Behaviour |
|---|---|---|
| `POST /portal/documents` multipart `file` (+ optional `kind_hint`) | patient | `accept_upload(source="web")`; 201 `{id, status, duplicate}`; 413 too_large, 415 bad_type, 403 no_consent, 429 rate_limited (Retry-After 3600); body limit enforced before read (10 MB + 1 KB) |
| `GET /portal/documents?status=` | patient | existing ContextNote list plus uploads from `list_uploads`: `{id, title: "Your document", kind, date, summary: "", status: "with care team"\|"reviewed"\|"not accepted"}`; never extracted values |
| `GET /requests` (doctor) | doctor/admin | `request_rows` includes `subkind IN ('patient_request','document_review')`; `RequestOut` gains `document: dict | None` (= `payload.data.document`, doctor-only) |
| `GET /documents/{id}/file` | doctor | streams the original with `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`; audit `document.viewed` |
| review queue | doctor | `/review/queue` also excludes `document_review` (it lives in Requests) |
`PortalDocument.kind`/`status` and `RequestOut.document` live in `cm/api/portal_models.py` (API models, not frozen contracts).

## 9. Channels
Telegram (lane F): in `tg_inbound._on_message`, after the binding+consent check, if `message.photo` (take the largest
size) or `message.document` exists: reject `file_size > 10 MB` immediately with the ack-refused template; else
`d.tasks.enqueue("agent-runs", f"tg-upload-{update_id}", {kind:"tg_upload", person_id, file_id, file_unique_id,
mime, file_name, chat_id, message_id})` and return OK (< 1 s). Caption text is ignored (never echoed). The task:
`HttpTelegramClient.get_file(file_id)` → `file_path`, `download_file(file_path) -> bytes` (new methods, both through
`cm.core.retry`, honour `TgRetryAfter`; Fake client gets the same), then `accept_upload(source="telegram",
origin={channel, telegram_chat_id, telegram_message_id}, ...)`, then send template `document_ack_v1` (or
`document_refused_v1` for bad_type/too_large/rate_limited; silent for duplicate) through the router/sender.
Supporters and unbound chats: refused, nothing downloaded.
Gmail (lane M): in the fetch worker, for a message whose From is in `DOCTOR_EMAIL_ALLOWLIST` and whose subject carries
exactly one `P-\d{4}` token, each attachment part with `attachmentId` → `GmailApi.get_attachment(message_id,
attachment_id) -> bytes` (new port method, `users.messages.attachments.get`, through retry) → `accept_upload(
source="gmail", uploader_person_id=<doctor>, origin={channel:"gmail", message_id})`. Max 5 attachments per message;
others logged. Non-allowlisted senders: attachments ignored. No auto-reply to the doctor beyond the existing digest.

Templates (lane K, `confirmations.yaml`, audience patient, tier green, doctor_approved):
`document_ack_v1` en "We received your document. Your care team will review it." te "మీ పత్రం మాకు అందింది. మీ
సంరక్షణ బృందం దాన్ని పరిశీలిస్తుంది." (needs native-speaker review); `document_refused_v1` en "We could not accept this
file. Please send a clear photo or a PDF under 10 MB." + te.

## 10. Failure modes and retries
| Failure | Handling |
|---|---|
| Telegram getFile 429/5xx/timeout | `cm.core.retry`, task attempts 6; final failure: audit, no row, no ack (patient may resend) |
| Telegram file > 20 MB (Bot API limit) | refused before download |
| Storage write fails | `storage_failed`; no DB row (row insert happens after put) |
| Row insert fails after put | orphan file; same sha re-put is idempotent; nightly orphan sweep (later) |
| Extraction provider error / budget cap / real-data refusal | lifecycle `failed`, review item still created with `error`; doctor reads the original |
| Corrupt PDF / image | refused at validation (`bad_type`) |
| Approval hook crashes | `upload-apply-<doc>` task retried; events idempotent by key; lifecycle guard makes re-run a no-op |
| Embedding off | chunks stored with NULL embedding, FTS fallback; `upload-index` can re-run later |
| Consent withdrawn later | existing consent-withdrawal flip sets chunks/documents `withdrawn`; file delete job (later) |

## 11. Test plan (`tests/test_uploads_*.py`, fakes for storage, Telegram, Gmail, vision)
1. No consent → refused, no file on disk, no row. 2. `.jpg` name with PDF bytes → stored as pdf; `.pdf` name with
HTML/zip/exe bytes → `bad_type`. 3. 10 MB + 1 byte → `too_large`; 0 bytes → `empty`. 4. 11-page PDF → `too_many_pages`;
encrypted PDF → `bad_type`. 5. Same bytes twice → second `duplicate=True`, one file, one row; same bytes, two patients →
two rows. 6. Same Telegram `file_unique_id` twice (webhook redelivery) → one row. 7. Sixth upload in an hour → `rate_limited`.
8. Filename `../../etc/passwd` and `a\x00b.pdf` → sanitised, storage path is only `<tok>/<sha>`. 9. Decompression-bomb PNG
→ `bad_type`; JPEG with GPS EXIF → stored bytes have no EXIF. 10. Text PDF → `method=pypdf`, no model call; scanned
PDF without pypdfium2 → `method=none`. 11. Image with `CM_DATA_CLASS=real` → `failed`, `ModelConfigError`, no network.
12. PII: patient name in PDF text → tokenised in `extra.extraction` and in the vision/LLM prompt (`assert_clean`).
13. Review payload matches §6 exactly (golden JSON); `/requests` row carries `document`; `/review/queue` excludes it.
14. Approve lab_report → one LabResult per value, idempotent on re-run; reject → withdrawn, zero events, zero chunks.
15. Index: chunk sizes <= 400 tokens with 60 overlap, parents <= 1,500, all chunks carry patient_token, consent_id,
sensitivity; patient B's retrieval never returns patient A's chunks; `as_of` before `recorded_at` hides the document.
16. Patient strings: ack/refused templates pass `make banned-terms`; ack never contains filename or extracted values.
17. Doctor notify: SSE event `kind=document` published; email dry-run file written once (claim dedupe).
18. Gmail: non-allowlisted sender → ignored; allowlisted, no `P-` token → ignored; same message+attachment id twice → one row.

## 12. Risks
| Risk | Mitigation |
|---|---|
| `requirements.txt` pins (`pypdf==6.21.2`, `pillow==13.0.0`, `python-multipart==0.0.32`) are UNVERIFIED; local Python has pypdf 5.1.0, Pillow 12.2.0 | lane I verifies; code uses only `PdfReader`, `pages`, `extract_text`, `is_encrypted` (stable across 4-6) |
| Overloading `doc_type` (`checkin`/`email`) for unclassified uploads | `extra.doc_kind` is the truth; RFC for `0009_rag_v2` to add `upload`/`other` values |
| `gcs_uri` CHECK forbids local URIs | local pointer in `extra.storage_uri` until GCS |
| Vision accuracy on Telugu/handwriting is unverified | low-confidence flags; doctor edits every field; nothing auto-written |
| Doctor bypasses review by mistake | only `on_approved` writes events; hook is reachable only from `decide.py` |
| Disk growth / abuse | 10 MB cap, 5/hour/patient, dedupe, retention date |
| Telegram webhook latency | download in task, never in webhook |
