## Why
The document upload pipeline (portal, Telegram, Gmail -> intake -> extraction -> doctor review -> index) had only
happy-path and basic refusal tests. This change adds adversarial tests in three NEW files and fixes the real bugs
they found. Lane: Integration (tests) with minimal fixes in the owning files (A `cm/store`, G `cm/api` +
`cm/uploads`, F `tg_upload.py`, M `gmail_reply.py`). Implements docs/design/UPLOAD_INGESTION.md sections 4, 7, 9, 10.

## What Changes
New tests (caremem_test only, FakeEmbedder, fake vision model, no network):
- `tests/integration/test_upload_edge.py` (79 cases): polyglots (PNG/JPEG with HTML/SVG/iframe tail, PDF with JS,
  Launch, hex-escaped JS, JS inside an object stream, EmbeddedFiles, zip named pdf, pdf with zip tail, SVG, late
  markup in text), PDF flate bomb, PNG pixel bomb, more than 30 pages, truncated/corrupt files, zero byte, exact
  cap and one byte over, hostile filenames (traversal, NUL, RTL/bidi, CRLF, 5000 chars, double extension,
  Telugu), consent revoked between upload and approval, patient isolation (chunks, search, list, same bytes),
  prompt injection (text and image), PII masking in payload and chunks, banned terms, low-confidence approve,
  reject, double approve, hook failure, task re-run, storage failure and retry, budget RED, portal streaming 413,
  exact limit, list isolation, status after approval, Telegram replay / forged size / token leak / after /stop,
  Gmail allowlist / display-name and DMARC spoof / two codes / duplicate message id / hostile attachment.
- `tests/property/test_upload_props.py` (21, hypothesis): filename cleanup, validation codes, markup anywhere,
  size boundary, pixel and flate bombs, obfuscated PDF actions, PII masking, idempotency keys, Gmail codes and
  two-address From, body-limit middleware.
- `tests/concurrency/test_upload_concurrency.py` (9): identical uploads, rate limit under a race (exactly 5),
  per-patient limit, Telegram origin race, extract task race, double approve, hook race, approve vs reject,
  two patients same bytes.

### Fix list (real bugs found by these tests)
1. `cm/uploads/validate.py`: markup was only checked in the first 1 KB of binaries / 4 KB of text, so a PNG or
   JPEG with an HTML/SVG tail and text with a late `<script>` were accepted. Now the whole body is checked.
2. `cm/uploads/validate.py`: PDFs with JavaScript, Launch actions, embedded files or RichMedia (also hex-escaped
   or inside compressed object streams) were accepted. Now `bad_type`.
3. `cm/uploads/validate.py`: a 50 KB PDF whose Flate stream inflates to hundreds of MB was accepted (pypdf 5
   then inflated it during extraction). Now one stream over 64 MB or a file over 512 MB inflated is refused,
   counted incrementally. PNG headers over 40 M pixels (and Pillow-detected JPEG bombs) are refused.
4. `cm/uploads/validate.py`: Telugu file names lost their vowel signs (combining marks were stripped).
5. `cm/store/uploads_repo.py` + `cm/uploads/intake.py`: one patient's concurrent uploads were not serialised:
   the same Telegram file raced in with different bytes made 5 rows, and the hourly limit could be exceeded.
   Now a per-patient transaction advisory lock (`uploads_repo.lock_patient`).
6. `cm/uploads/review.py` + `cm/uploads/intake.py`: consent withdrawn between upload and approval still wrote
   events and chunks. `on_approved` now re-checks consent (`intake.has_upload_consent`) and marks the upload
   rejected; the decision itself stands.
7. `cm/api/body_limit.py` (new) + `cm/api/main.py`: `POST /portal/documents` parsed and spooled the whole
   multipart body before its size check. New ASGI middleware answers 413 from Content-Length without reading,
   and stops reading a streamed body past the cap.
8. `cm/api/routers/portal.py`: an approved upload (state `indexed`) showed "received"; now "added to your record".
9. `cm/channels/tg_upload.py`: a file queued before /stop was still downloaded after consent was withdrawn;
   `run_tgfile_task` now checks consent before the download.
10. `cm/channels/gmail_reply.py`: `parseaddr("doc@clinic <evil@x>")` returns doc@clinic while DMARC aligns on
    evil@x, so a spoofed From passed the allowlist (attachments and approve-by-reply). A From header with more
    than one address is now never trusted.

Wrong tests corrected (not bugs): budget RED surfaces as `vision_failed:ProviderCallFailed` (the retry layer
wraps TemplateOnlyMode; no model is ever built); Gmail codes are exactly 4 digits (`PT-10000` is not a code).

Open (noted, not fixed): a transient storage read failure during extraction gives an empty review item (the
doctor still opens the file); a code in the subject wins over a different code in the body (documented rule).

### Out of scope
Contracts (no change), web UI, the live API / Telegram poller / live database. No migration.
