## Why
DeepSeek chat (deepseek-flash) was verified live to read text from an image sent as an image_url data URI. The VISION role was openai-only, blocking cheap document-photo extraction (prescriptions, lab reports, chemist bills).

## What Changes
- `cm/core/llm.py`: VISION may use `deepseek:*`; EMBEDDING stays openai-only. `deepseek:` still refused when `CM_DATA_CLASS=real`; new guard refuses any image part when data class is real. Text parts (including `{"type":"text"}` parts) are still checked by `assert_clean`.
- `cm/tools/vision_extract.py`: `extract_document(image_bytes, doc_type)` returns a DRAFT (strict pydantic schema, per-field confidence, JSON retries via `cm.core.retry`). Never writes events. `patient_view()` hides drug names.
- `.env.example`: VISION_MODEL documented (name + placeholder only).
- Telugu text in images: mention-only note in module docstring; accuracy unverified.

## Out of scope
Wiring the draft into doctor review/ingestion, OCR for Telugu, web/ UI.

## Owning lane
A (cm/core) for llm.py; E/N-adjacent cm/tools for the new module; I for .env.example. Spec section: RAG_STRATEGY_v2 document ingestion. No contract changes.
