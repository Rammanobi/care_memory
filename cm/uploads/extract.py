"""Document upload -> text + draft fields for doctor review. Never raises, never writes events.

``extract_document_text(document_id) -> Extraction``: .txt direct, .pdf text layer via pypdf (lazy import; a PDF
without a text layer is flagged ``needs_vision`` and is NOT rendered), images via the governed vision extractor
(``cm.tools.vision_extract.extract_document``, mock data only). Text from txt/pdf never goes to a model, so
instructions inside a document cannot steer anything: the text is stored as data and shown to the doctor only.
Every text that leaves this module is PII tokenised. Drug names live only in doctor-side fields (rule 5).
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from cm.core.logging import get_logger
from cm.core.tokenize import tokenize

log = get_logger()

MAX_TEXT_CHARS = 20_000
MAX_PAGES = 50
MIN_TEXT_CHARS = 20
DOC_TYPES = ("prescription", "lab_report", "chemist_bill", "other")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_DATE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b"
)
_KV = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _./()-]{1,40})\s*[:=]\s*(.{1,80}?)\s*$")

def _words(*ws: str) -> re.Pattern[str]:
    """Whole words only ('lab' must not match 'available' or 'label', 'mg' not 'among'); '_' and digits
    separate words so 'rx_photo.jpg' and '10mg' still match. Telugu words are matched as substrings."""
    en = [w for w in ws if w.isascii()]
    te = [re.escape(w) for w in ws if not w.isascii()]
    return re.compile(r"(?<![a-z])(?:" + "|".join(en) + r")(?![a-z])" + "".join("|" + t for t in te), re.I)


_GUESS = (
    ("lab_report", _words("lab", "laboratory", "smear", "cbnaat", "truenat", "culture", "sputum",
                          "investigations?", "ల్యాబ్", "కఫం")),
    ("chemist_bill", _words("chemist", "pharmacy", "medical stores?", "medicals", "dispens\\w*",
                            "మందుల షాపు", "ఫార్మసీ")),
    ("prescription", _words("prescription", "rx", "tablets?", "tab", "mg", "doses?", "refill",
                            "ప్రిస్క్రిప్షన్", "మాత్ర", "మోతాదు")),
)
# A bill, invoice or receipt is a chemist bill only with a medicine cue (an electricity bill is not).
_BILL = _words("bill", "invoice", "receipt", "బిల్లు", "రసీదు")
_MED_CUE = _words("medical", "medicines?", "tablets?", "strips?", "qty", "mg", "మందు", "మాత్ర")


@dataclass
class Extraction:
    doc_type: str = "other"
    text: str = ""
    pages: int = 0
    fields: list[dict[str, Any]] = field(default_factory=list)
    needs_vision: bool = False
    reason: str = ""


# ---- upload store access (cm.store.uploads_repo rows are cm.documents rows; state is extra.upload_state) -----
_storage_override: Any = None


def set_storage(port: Any | None) -> None:
    """Inject a StoragePort (tests). ``None`` restores ``cm.uploads.storage.get_storage``."""
    global _storage_override
    _storage_override = port


def _uuid(document_id: Any) -> UUID:
    return document_id if isinstance(document_id, UUID) else UUID(str(document_id))


def load_upload(document_id: Any) -> dict[str, Any] | None:
    """Flat view of an upload: top-level columns plus ``extra`` keys, and ``state`` = extra.upload_state."""
    from cm.store import uploads_repo

    row = uploads_repo.get(_uuid(document_id))
    if not row:
        return None
    extra = dict(row.get("extra") or {})
    return {**extra, **{k: v for k, v in dict(row).items() if k != "extra"}, "state": extra.get("upload_state"),
            "extra": extra}


def read_bytes(row: dict[str, Any]) -> bytes:
    from cm.uploads.storage import get_storage

    uri = _pick(row, "storage_uri", "gcs_uri")
    return bytes((_storage_override or get_storage()).get(uri))


def set_state(document_id: Any, state: str, **detail: Any) -> None:
    from cm.store import uploads_repo

    uploads_repo.set_state(_uuid(document_id), state, detail or None)


def _pick(row: dict[str, Any], *names: str, default: Any = None) -> Any:
    for n in names:
        if row.get(n) not in (None, ""):
            return row[n]
    return default


# ---- helpers --------------------------------------------------------------------------------------------
def mask(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    """Control characters removed, PII tokenised, whitespace tidied, length capped."""
    t = _CTRL.sub(" ", text or "")
    t = tokenize(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t[:limit]


def guess_doc_type(text: str, filename: str = "", hint: str | None = None) -> str:
    if hint in DOC_TYPES:
        return str(hint)
    blob = f"{filename} {text[:2000]}".lower()
    for dt, rx in _GUESS:
        if rx.search(blob) or (dt == "chemist_bill" and _BILL.search(blob) and _MED_CUE.search(blob)):
            return dt
    return "other"


def _text_fields(text: str) -> list[dict[str, Any]]:
    """Cheap rule-based fields (dates and 'label: value' lines). Low confidence: the doctor decides."""
    out: list[dict[str, Any]] = []
    for m in list(_DATE.finditer(text))[:5]:
        out.append({"name": "date", "value": m.group(1), "confidence": 0.5})
    for line in text.splitlines()[:200]:
        m = _KV.match(line)
        if m and len(out) < 40:
            out.append({"name": m.group(1).strip().lower(), "value": m.group(2), "confidence": 0.5})
    return out


def _printable_ratio(s: str) -> float:
    return sum(c.isprintable() or c in "\n\t" for c in s) / len(s) if s else 0.0


def _from_txt(data: bytes) -> tuple[str, str]:
    s = data.decode("utf-8", errors="replace")
    if not s.strip():
        return "", "empty"
    if _printable_ratio(s) < 0.85 or s.count("�") / len(s) > 0.2:
        return "", "unreadable"
    return s, ""


def _from_pdf(data: bytes) -> tuple[str, int, str]:
    try:
        from pypdf import PdfReader  # lazy: only needed for PDFs
    except ImportError:
        return "", 0, "pypdf_missing"
    try:
        rd = PdfReader(io.BytesIO(data))
        if rd.is_encrypted:
            return "", 0, "encrypted"
        n = len(rd.pages)
        parts = [(rd.pages[i].extract_text() or "") for i in range(min(n, MAX_PAGES))]
    except Exception as exc:  # noqa: BLE001  (a bad PDF must never raise out of extraction)
        return "", 0, f"pdf_unreadable:{type(exc).__name__}"
    return "\n".join(parts), n, ""


def _vision_fields(draft: Any) -> list[dict[str, Any]]:
    d = draft.data
    out: list[dict[str, Any]] = []
    for x in d.dates:
        out.append({"name": "date", "value": x.value, "confidence": x.confidence})
    for i, m in enumerate(d.medicines):
        for k in ("name", "quantity", "dose"):
            f = getattr(m, k)
            out.append(
                {"name": f"medicines[{i}].{k}", "value": f.value, "confidence": f.confidence}
            )
    for i, lv in enumerate(d.lab_values):
        for k in ("test", "value", "unit"):
            f = getattr(lv, k)
            out.append(
                {"name": f"lab_values[{i}].{k}", "value": f.value, "confidence": f.confidence}
            )
    return out


def vision_allowed() -> bool:
    return (
        os.environ.get("CM_DATA_CLASS", "").strip().lower() == "mock"
        or os.environ.get("UPLOAD_VISION_LIVE", "").strip() == "1"
    )


def _from_image(data: bytes, mime: str, doc_type: str, token: str, model: Any) -> Extraction:
    dt = doc_type if doc_type in ("prescription", "lab_report", "chemist_bill") else "prescription"
    if not vision_allowed():  # raw images go to a model only for mock data or an explicit live opt-in
        return Extraction(dt, "", 1, [], True, "vision_disabled")
    try:
        from cm.tools.vision_extract import extract_document

        draft = extract_document(
            data,
            dt,
            mime=mime,
            model=model,
            task_id="upload_vision",
            patient_id=token or None,  # type: ignore[arg-type]
        )
    except Exception as exc:  # noqa: BLE001
        return Extraction(dt, "", 1, [], True, f"vision_failed:{type(exc).__name__}")
    fields = _vision_fields(draft)
    lines = [f"{f['name']}: {f['value']}" for f in fields if f["value"] not in (None, "")]
    text = mask("\n".join(lines))
    for f in fields:
        if isinstance(f["value"], str):
            f["value"] = mask(f["value"], 200)
    return Extraction(dt, text, 1, fields, not fields, "" if fields else "no_fields_read")


def _kind(row: dict[str, Any]) -> str:
    mime = str(_pick(row, "mime", default="")).lower()
    name = str(_pick(row, "filename", default="")).lower()
    if mime == "application/pdf" or name.endswith(".pdf"):
        return "pdf"
    if mime.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "image"
    if mime.startswith("text/") or name.endswith(".txt"):
        return "txt"
    return "other"


def extract_document_text(document_id: str, *, model: Any | None = None) -> Extraction:
    """Extract text and draft fields for one stored upload. Never raises."""
    did = str(document_id)
    try:
        row = load_upload(did)
        if row is None:
            return Extraction(reason="upload_not_found")
        kind = _kind(row)
        name = str(_pick(row, "filename", default=""))
        hint = _pick(row, "doc_type")
        token = str(_pick(row, "patient_token", default=""))
        data = read_bytes(row)
        if kind == "image":
            return _from_image(
                data,
                str(_pick(row, "mime", default="image/png")),
                guess_doc_type("", name, hint),
                token,
                model,
            )
        if kind == "pdf":
            raw, pages, why = _from_pdf(data)
            text = mask(raw)
            if why or len(text) < MIN_TEXT_CHARS:
                return Extraction(
                    guess_doc_type(text, name, hint), text, pages, [], True, why or "no_text_layer"
                )
        elif kind == "txt":
            raw, why = _from_txt(data)
            pages, text = 1, mask(raw)
            if why or not text:
                return Extraction(
                    guess_doc_type("", name, hint), "", pages, [], False, why or "empty"
                )
        else:
            return Extraction(guess_doc_type("", name, hint), "", 0, [], False, "unsupported_type")
        return Extraction(
            guess_doc_type(text, name, hint), text, pages, _text_fields(text), False, ""
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("document extraction failed", error=type(exc).__name__)
        return Extraction(reason=f"extract_failed:{type(exc).__name__}")
