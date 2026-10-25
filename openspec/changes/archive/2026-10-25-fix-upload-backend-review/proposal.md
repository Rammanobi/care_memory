## Why
Independent review of upload ingestion found: portal uploads never enqueued extraction (critical); a failing post-commit hook or extract left uploads stuck; raw images reached the vision model without a data-class gate; filename-only guesses could become LabResult/Dispense events; rate limit race; "of 7 doses" wrong for new patients; storage root CWD-relative.

## What Changes
Enqueue docx-<id> from POST /portal/documents; failed state plus docidx-<id> retry task (document_index) on hook/extract failure; vision gated by CM_DATA_CLASS=mock or UPLOAD_VISION_LIVE=1; no result events from needs_vision/empty excerpt, confident-only tablet total shown to doctor; advisory lock on rate limit; own-data window capped to days since start (template placeholder window); storage root REPO_ROOT/data/uploads; as_of param on list_for_patient; make_demo_env strips both quote kinds.

Out of scope: channels (tg_upload, gmail_attach, gmail). Owning lane: G (plus scripts one-liner, templates wording).
Symptom/root cause/fix/verification: see What Changes; verified by tests/unit/uploads, tests/integration/test_upload_core.py, tests/unit/api/test_own_data.py.
