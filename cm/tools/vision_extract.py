"""Document image -> DRAFT structured extraction (prescription / lab report / chemist bill).

Never writes events. The result is a ``DraftExtraction`` that must go through doctor review
(``cm/review``); nothing here touches the store. Provider access is only ``get_model("VISION")``
(CLAUDE.md rule 16); the budget governor, retry and the real-data image guard live in ``llm.py``.
Drug names exist only in the doctor-side draft; ``patient_view()`` never carries them (rule 5).

Telugu (and other Indic) text in images: mention only. Accuracy is unverified, so low-confidence
fields are flagged for the doctor; no transliteration or translation is attempted here.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cm.core.llm import get_model
from cm.core.retry import RetryPolicy, call_with_retry

DocType = Literal["prescription", "lab_report", "chemist_bill"]
LOW_CONFIDENCE = 0.6


class Field_(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)
    value: str | float | int | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class Medicine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Field_
    quantity: Field_ = Field_()
    dose: Field_ = Field_()


class LabValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    test: Field_
    value: Field_
    unit: Field_ = Field_()


class RawExtraction(BaseModel):
    """Strict schema the model must satisfy (unknown keys rejected)."""

    model_config = ConfigDict(extra="forbid")
    doc_type: DocType
    dates: list[Field_] = []
    medicines: list[Medicine] = []
    lab_values: list[LabValue] = []


class DraftExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["draft"] = "draft"
    requires_doctor_review: Literal[True] = True
    writes_events: Literal[False] = False
    doc_type: DocType
    data: RawExtraction
    low_confidence_fields: list[str] = []

    def patient_view(self) -> dict[str, Any]:
        """Patient/Supporter-safe projection: no drug names, no doses."""
        return {
            "status": self.status,
            "doc_type": self.doc_type,
            "dates": [d.value for d in self.data.dates],
            "medicine_count": len(self.data.medicines),
            "quantities": [m.quantity.value for m in self.data.medicines if m.quantity.value is not None],
        }


class _BadJSON(Exception):
    error_class = "retryable"  # model returned unparsable / off-schema JSON: ask again


_PROMPT = (
    "You read a photo of a {doc_type}. Return ONLY one JSON object with keys: doc_type, dates, medicines, "
    "lab_values. Each leaf is {{\"value\": ..., \"confidence\": 0..1}}. medicines items: name, quantity, dose. "
    "lab_values items: test, value, unit. Dates as printed. Use null value and confidence 0 when unreadable. "
    "Do not guess. Do not add keys."
)


def _parse(text: str, doc_type: str) -> RawExtraction:
    m = re.search(r"\{.*\}", text.strip(), re.S)
    try:
        obj = json.loads(m.group(0) if m else text)
        obj["doc_type"] = doc_type  # caller is authoritative; models sometimes wrap it
        return RawExtraction.model_validate(obj)
    except (ValueError, ValidationError) as e:
        raise _BadJSON(str(e)[:200]) from e


def _low_conf(r: RawExtraction) -> list[str]:
    out: list[str] = []
    for i, d in enumerate(r.dates):
        if d.confidence < LOW_CONFIDENCE:
            out.append(f"dates[{i}]")
    for i, med in enumerate(r.medicines):
        for k in ("name", "quantity", "dose"):
            if getattr(med, k).confidence < LOW_CONFIDENCE:
                out.append(f"medicines[{i}].{k}")
    for i, lv in enumerate(r.lab_values):
        for k in ("test", "value", "unit"):
            if getattr(lv, k).confidence < LOW_CONFIDENCE:
                out.append(f"lab_values[{i}].{k}")
    return out


def extract_document(image_bytes: bytes, doc_type: DocType, *, mime: str = "image/png",
                     model: Any | None = None, task_id: str = "vision_extract",
                     patient_id: str | None = None) -> DraftExtraction:
    """Return a DRAFT for doctor review. Raises ProviderCallFailed / ModelConfigError from the stack."""
    if doc_type not in ("prescription", "lab_report", "chemist_bill"):
        raise ValueError(f"unsupported doc_type {doc_type}")
    m = model or get_model("VISION")
    uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
    messages = [{"role": "user", "content": [
        {"type": "text", "text": _PROMPT.format(doc_type=doc_type.replace("_", " "))},
        {"type": "image_url", "image_url": {"url": uri}},
    ]}]

    def go() -> RawExtraction:
        out = m.invoke(messages, task_id=task_id, task_type="vision_extract", patient_id=patient_id)
        return _parse(str(getattr(out, "content", out)), doc_type)

    raw = call_with_retry(go, RetryPolicy(max_attempts=3, base_delay=0.0), sleep=lambda _s: None)
    return DraftExtraction(doc_type=doc_type, data=raw, low_confidence_fields=_low_conf(raw))
