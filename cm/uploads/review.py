"""Document upload review: approval row, extract task, post-decision events and RAG indexing.

Flow: intake saves the file and enqueues task ``document_extract`` {document_id} (task_id ``docx-<id>``).
``run_document_extract`` extracts, sets state extracted -> pending_review, creates ONE doctor review item
(``payload.subkind = 'document_review'``), publishes the SSE ``review`` event ``patient_document`` and emails the
doctor (category ``document``). The doctor decides ONLY through ``cm.review.decide.decide``; that function calls
``on_decided`` after its transaction commits. Approve (or edit) writes events from the confirmed text excerpt
(never the raw file) and indexes the document into cm.documents / cm.text_chunks; reject sets state ``rejected``
and indexes nothing. Every step is idempotent. The patient-facing text is the fixed ``ACK_TEXT`` only.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any
from uuid import UUID

from cm.core import clock, tasks
from cm.core.logging import get_logger
from cm.store import ai_repo, approvals_repo, chunks_repo, events_repo, stream_repo
from cm.uploads import extract as ex

log = get_logger()
TASK_KIND = "document_extract"
SUBKIND = "document_review"
ACK_TEXT = "We received your document. Your care team will look at it and contact you if they need anything else."
EXCERPT_MAX = 400
CHUNK_TOKENS, CHUNK_OVERLAP = 400, 60
_DOC_TYPE = {"lab_report": "lab", "prescription": "prescription", "chemist_bill": "sales_csv"}
_REVIEWED = {"approved", "edited"}
LOW_CONF = 0.6


def task_id(document_id: str) -> str:
    return f"docx-{document_id}"


def enqueue_extract(document_id: str) -> None:
    """Idempotent per document (same task_id twice is a no-op). Call AFTER the upload row is committed."""
    tasks.enqueue(
        "agent-runs", task_id(document_id), {"kind": TASK_KIND, "document_id": str(document_id)}
    )


def _tier(e: ex.Extraction) -> str:
    low = [f for f in e.fields if (f.get("confidence") or 0) < LOW_CONF]
    return "amber" if (e.needs_vision or not e.fields or low) else "green"


def _document_block(row: dict[str, Any], did: str, e: ex.Extraction) -> dict[str, Any]:
    return {
        "id": did,
        "filename": ex.mask(str(ex._pick(row, "filename", default="")), 120),  # names can carry phone/ids
        "mime": ex._pick(row, "mime", default=""),
        "size": ex._pick(row, "size", "size_bytes", "bytes", default=0),
        "pages": e.pages,
        "status": "needs_vision" if e.needs_vision else ("empty" if not e.text else "extracted"),
        "extraction": {
            "doc_type": e.doc_type,
            "fields": e.fields,
            "text_excerpt": ex.mask(e.text, EXCERPT_MAX),
            "needs_vision": e.needs_vision,
            "reason": e.reason,
            **({"tablets": _tablets(e.fields)} if e.doc_type == "chemist_bill" else {}),
        },
    }


def create_review_item(document_id: str, *, extraction: ex.Extraction | None = None) -> UUID | None:
    """Create (or find) the doctor review approval for one upload. Returns approval_id, None if unknown upload."""
    did = str(document_id)
    row = ex.load_upload(did)
    if row is None:
        return None
    e = extraction or ex.extract_document_text(did)
    token = str(ex._pick(row, "patient_token", default=""))
    pid, token = ai_repo.resolve_patient(token)
    at = clock.now()
    tier = _tier(e)
    block = _document_block(row, did, e)
    payload = {
        "audience": "patient",
        "title": f"Document review: {e.doc_type.replace('_', ' ')}",
        "channel": "web",
        "recipients": [],
        "body": ACK_TEXT,
        "subkind": SUBKIND,
        "data": {
            "kind": "Document upload",
            "document": block,
            "extracted_text": e.text,  # masked, capped; used only to index after approval
            "refs": [],
            "source": "upload",
            "priority": "high" if tier == "amber" else "normal",
        },
    }
    return approvals_repo.upsert(
        {
            "patient_id": pid,
            "thread_id": f"doc-{did}",
            "interrupt_id": "review",
            "tier": tier,
            "kind": "needs_human",
            "payload": payload,
            "created_at": at,
            "due_at": at + timedelta(hours=4 if tier == "green" else 1),
            "expires_at": at + timedelta(hours=48),
        }
    )


def run_document_extract(document_id: str) -> dict[str, Any]:
    """Task handler. Idempotent: a document already past extraction is not processed or announced again."""
    did = str(document_id)
    row = ex.load_upload(did)
    if row is None:
        return {"status": "missing"}
    if str(row.get("state") or "") in ("pending_review", "accepted", "indexed", "rejected"):
        return {"status": "duplicate"}
    ex.set_state(did, "extracting")
    try:
        e = ex.extract_document_text(did)
        aid = create_review_item(did, extraction=e)
        if aid is None:
            ex.set_state(did, "failed", fail_reason="upload_missing")
            return {"status": "missing"}
        ex.set_state(
            did, "pending_review", approval_id=str(aid), doc_kind=e.doc_type, needs_vision=e.needs_vision
        )
    except Exception as exc:  # noqa: BLE001  (never leave the upload stuck in 'extracting')
        ex.set_state(did, "failed", fail_reason=f"extract_error:{type(exc).__name__}")
        raise
    _tell_doctor(aid, str(ex._pick(row, "patient_token", default="")), e)
    return {"status": "pending_review", "approval_id": str(aid), "needs_vision": e.needs_vision}


def _tell_doctor(aid: UUID, token: str, e: ex.Extraction) -> None:
    from cm.api.deps import display_code

    code = display_code(token)
    try:
        stream_repo.publish(
            "review",
            {
                "type": "patient_document",
                "kind": "patient_document",
                "ref": str(aid),
                "approval_id": str(aid),
                "patient_code": code,
                "category": "document",
                "doc_type": e.doc_type,
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("stream publish failed", error=type(exc).__name__)
    try:
        from cm.channels import doctor_notify

        doctor_notify.notify_doctor_new_question(
            str(aid),
            patient_code=code,
            category="document",
            priority="normal",
            question_excerpt="A new document was uploaded and needs your review.",
            channel="web",
        )
    except Exception as exc:  # noqa: BLE001  (a failed email must not fail the task)
        log.warning("doctor notify failed", error=type(exc).__name__)


# ---- after the doctor decides ---------------------------------------------------------------------------
def on_decided(approval_id: UUID | str) -> dict[str, Any]:
    """Called by cm.review.decide after commit. Approve/edit -> on_approved; reject/expired -> rejected."""
    aid = UUID(str(approval_id))
    row = approvals_repo.get(aid, clock.now())
    if row is None or (row["payload"] or {}).get("subkind") != SUBKIND:
        return {"status": "ignored"}
    if row["status"] in _REVIEWED:
        return on_approved(aid)
    if row["status"] in ("rejected", "expired"):
        did = str(((row["payload"].get("data") or {}).get("document") or {}).get("id") or "")
        if did:
            ex.set_state(did, "rejected")
        return {"status": "rejected"}
    return {"status": "pending"}


def index_task_id(document_id: str) -> str:
    return f"docidx-{document_id}"


def mark_index_failed(approval_id: UUID | str, exc: BaseException) -> None:
    """The post-commit hook raised: show the upload as failed and queue an idempotent re-run of on_approved."""
    aid = UUID(str(approval_id))
    row = approvals_repo.get(aid, clock.now())
    if row is None or (row["payload"] or {}).get("subkind") != SUBKIND:
        return
    did = str(((row["payload"].get("data") or {}).get("document") or {}).get("id") or "")
    if not did:
        return
    ex.set_state(did, "failed", fail_reason=f"index_error:{type(exc).__name__}")
    if row["status"] in _REVIEWED:
        tasks.enqueue(
            "agent-runs",
            index_task_id(did),
            {"kind": "document_index", "approval_id": str(aid), "document_id": did},
        )


def _sha(*parts: str) -> bytes:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()


def _num(v: Any) -> int:
    try:
        return max(0, int(float(str(v).strip().split()[0])))
    except (ValueError, IndexError):
        return 0


def _tablets(fields: list[dict[str, Any]]) -> int:
    """Total tablets from confident quantity fields only (confidence >= LOW_CONF); shown to the doctor too."""
    return sum(
        _num(f.get("value"))
        for f in fields
        if str(f.get("name", "")).endswith(".quantity") and float(f.get("confidence") or 0) >= LOW_CONF
    )


def _write_events(
    pid: UUID,
    did: str,
    doc_type: str,
    fields: list[dict[str, Any]],
    excerpt: str,
    row: dict[str, Any],
    needs_vision: bool = False,
) -> str:
    """Events from the doctor-approved excerpt (text only, never the raw file). Idempotent per document."""
    at = clock.now()
    sha = str(ex._pick(row, "sha256", "content_hash", default=did))
    kind = "ContextNote"
    payload: dict[str, Any] = {
        "origin": "doctor",
        "kind": f"{doc_type}_upload",
        "text_tokenised": excerpt,
        "data": {"document_id": did, "doc_type": doc_type},
    }
    solid = not needs_vision and bool(excerpt.strip())  # a filename-only guess never becomes a result
    if doc_type == "lab_report" and solid:
        conf = [float(f.get("confidence") or 0) for f in fields]
        kind = "LabResult"
        payload = {
            "test": "other",
            "result": "reviewed_upload",
            "rif_resistant": None,
            "report_date": at.date().isoformat(),
            "lab_ref": did,
            "upload_sha256": sha,
            "extraction_confidence": min(conf) if conf else None,
            "edited_fields": [],
            "text_excerpt": excerpt,
        }
    elif doc_type == "chemist_bill" and solid and _tablets(fields) > 0:
        kind = "Dispense"
        payload = {
            "tablets": _tablets(fields),
            "row_sha1": sha[:40],
            "text_excerpt": excerpt,
            "document_id": did,
        }
    events_repo.append_event(
        events_repo.NewEvent(
            patient_id=pid,
            type=kind,
            occurred_at=at,
            recorded_at=at,
            source="console",
            reporter_mode="record",
            channel="web",
            payload=payload,
            idempotency_key=f"doc:{did}:{kind}",
        )
    )
    return kind


def _index(
    token: str, did: str, doc_type: str, text: str, embedder: Any, row: dict[str, Any]
) -> dict[str, int]:
    """Chunk (400 tokens, 60 overlap, parents up to 1500) and embed into cm.documents / cm.text_chunks."""
    from cm.core.tokenize import assert_clean
    from cm.rag import chunk as _chunk

    assert_clean(text)
    at = clock.now()
    consent_id = _consent(row)
    doc = {
        "doc_type": _DOC_TYPE.get(doc_type, "checkin"),
        "extra": {"kind": "uploaded_document", "chunk_kind": "uploaded_document", "document_id": did,
                  "upload_doc_type": doc_type, "source_event_ids": []},
    }
    did_row = UUID(did)  # the upload row itself is the parent document
    chunks = _chunk.chunk_text(
        text, size_tokens=CHUNK_TOKENS, overlap_tokens=CHUNK_OVERLAP, strategy="dynamic"
    )
    texts = [c.text for c in chunks if c.role == "chunk"]
    vecs = _embed(embedder, texts, token)
    by_text = dict(zip(texts, vecs, strict=True)) if vecs else {}
    ids: dict[int, Any] = {}
    new = 0
    for c in chunks:
        r: dict[str, Any] = {
            "document_id": did_row,
            "patient_token": token,
            "doc_type": doc["doc_type"],
            "occurred_at": at,
            "recorded_at": at,
            "consent_id": consent_id,
            "language": "en",
            "content": c.text,
            "content_hash": _sha(c.text),
            "sensitivity": "normal",
            "parent_id": ids.get(c.parent_seq) if c.parent_seq is not None else None,
            "extra": {
                **doc["extra"],
                "role": c.role,
                "seq": c.seq,
                "tokens": c.tokens,
                "strategy": "dynamic",
            },
        }
        if c.role == "chunk" and c.text in by_text:
            r.update(
                embedding=by_text[c.text], embedding_model=getattr(embedder, "model", "embedder")
            )
        cid, ins = chunks_repo.upsert_chunk(r)
        ids[c.seq] = cid
        new += int(ins)
    return {"chunks": len(chunks), "new": new}


def _consent(row: dict[str, Any]) -> Any:
    cid = ex._pick(row, "consent_id")
    return UUID(str(cid)) if cid else None


def _embed(embedder: Any, texts: list[str], token: str) -> list[list[float]]:
    if not texts:
        return []
    try:
        emb = embedder
        if emb is None:
            import os

            if not os.environ.get("OPENAI_API_KEY"):
                from cm.rag.embed import FakeEmbedder

                emb = FakeEmbedder()
            else:
                from cm.rag.embed import Embedder

                emb = Embedder()
        return emb.embed_documents(texts, task_id="upload_embed", patient_id=token)
    except Exception as exc:  # noqa: BLE001  (index without vectors: BM25 still finds it)
        log.warning("upload embedding failed", error=type(exc).__name__)
        return []


def on_approved(approval_id: UUID | str, *, embedder: Any | None = None) -> dict[str, Any]:
    """After a doctor approves/edits: write events, index the text, set state ``indexed``. Idempotent."""
    aid = UUID(str(approval_id))
    row = approvals_repo.get(aid, clock.now())
    if row is None or (row["payload"] or {}).get("subkind") != SUBKIND:
        return {"status": "ignored"}
    if row["status"] not in _REVIEWED:
        return {"status": "not_approved"}
    data = row["payload"].get("data") or {}
    block = data.get("document") or {}
    did = str(block.get("id") or "")
    token = row.get("patient_token") or ""
    if not did or not token:
        return {"status": "invalid"}
    up = ex.load_upload(did) or {}
    if up.get("state") == "indexed":
        return {"status": "duplicate"}
    from cm.uploads.intake import has_upload_consent

    if not has_upload_consent(token, str(up.get("channel") or "portal")):
        ex.set_state(did, "rejected", reason="consent_withdrawn")  # withdrawn after upload: nothing written
        return {"status": "no_consent"}
    extr = block.get("extraction") or {}
    text = str(data.get("extracted_text") or "")
    kind = _write_events(
        row["patient_id"],
        did,
        str(extr.get("doc_type") or "other"),
        list(extr.get("fields") or []),
        str(extr.get("text_excerpt") or ""),
        up,
        bool(extr.get("needs_vision")),
    )
    stats = (
        _index(token, did, str(extr.get("doc_type") or "other"), text, embedder, up)
        if text.strip()
        else {"chunks": 0, "new": 0}
    )
    ex.set_state(did, "accepted")
    ex.set_state(did, "indexed", chunk_count=stats["chunks"], event=kind)
    return {"status": "indexed", "event": kind, **stats}


__all__ = [
    "ACK_TEXT",
    "create_review_item",
    "enqueue_extract",
    "on_approved",
    "mark_index_failed",
    "on_decided",
    "run_document_extract",
    "task_id",
]
