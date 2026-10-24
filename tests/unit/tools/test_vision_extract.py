import io
import json
import os
from types import SimpleNamespace

import pytest

from cm.core import budget as b
from cm.core import llm
from cm.core.retry import ProviderCallFailed, RateLimiter
from cm.tools.vision_extract import extract_document

GOOD = {
    "doc_type": "chemist_bill",
    "dates": [{"value": "12 Oct", "confidence": 0.9}],
    "medicines": [{"name": {"value": "Isoniazid", "confidence": 0.8},
                   "quantity": {"value": 28, "confidence": 0.9}, "dose": {"value": None, "confidence": 0.2}}],
    "lab_values": [],
}
ENV = {"VISION_MODEL": "deepseek:deepseek-flash"}


class Fake:
    def __init__(self, replies):
        self.replies, self.n, self.seen = list(replies), 0, None

    def invoke(self, messages, **kw):
        self.n += 1
        self.seen = messages
        r = self.replies[min(self.n - 1, len(self.replies) - 1)]
        return SimpleNamespace(content=r, usage_metadata={"input_tokens": 100, "output_tokens": 50})


def _governed(fake, env=ENV):
    g = b.BudgetGovernor(b.BudgetLimits(daily_usd=10, demo_reserve_usd=0, event_usd=1000, per_task_usd=1000),
                         b.PriceTable({"deepseek-flash": (0.1, 0.1)}))
    return llm.get_model("VISION", governor=g, env=env, limiter=RateLimiter(1e6, 1e9),
                         builder=lambda s, r: fake), g


def test_draft_only_and_patient_view_hides_drugs():
    m, g = _governed(Fake([json.dumps(GOOD)]))
    d = extract_document(b"\x89PNG", "chemist_bill", model=m)
    assert d.status == "draft" and d.requires_doctor_review and d.writes_events is False
    assert d.data.medicines[0].name.value == "Isoniazid"
    assert "medicines[0].dose" in d.low_confidence_fields
    assert "Isoniazid" not in json.dumps(d.patient_view())


def test_image_sent_as_data_uri_and_json_retry():
    f = Fake(["not json", "```json\n" + json.dumps(GOOD) + "\n```"])
    m, _ = _governed(f)
    d = extract_document(b"abc", "chemist_bill", model=m)
    assert f.n == 2 and d.data.dates[0].value == "12 Oct"
    parts = f.seen[0]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_off_schema_exhausts_retries():
    m, _ = _governed(Fake([json.dumps({**GOOD, "extra": 1})]))
    with pytest.raises(ProviderCallFailed):
        extract_document(b"abc", "chemist_bill", model=m)


def test_bad_doc_type():
    with pytest.raises(ValueError):
        extract_document(b"x", "selfie", model=object())  # type: ignore[arg-type]


def test_real_data_blocks_images_and_deepseek():
    with pytest.raises(llm.ModelConfigError):
        llm.get_model("VISION", env={**ENV, "CM_DATA_CLASS": "real"})
    m, _ = _governed(Fake([json.dumps(GOOD)]), env={"VISION_MODEL": "openai:v", "CM_DATA_CLASS": "real"})
    with pytest.raises(ProviderCallFailed) as ei:
        extract_document(b"abc", "chemist_bill", model=m)
    assert isinstance(ei.value.__cause__, llm.ModelConfigError) and "images" in str(ei.value.__cause__)


def test_text_part_still_pii_checked():
    m, _ = _governed(Fake(["{}"]))
    from cm.core.tokenize import PIILeak
    with pytest.raises(PIILeak):
        m.invoke([{"role": "user", "content": [{"type": "text", "text": "call 9876543210"}]}])


@pytest.mark.live
def test_live_synthetic_image():
    from PIL import Image, ImageDraw, ImageFont

    if not os.environ.get("VISION_MODEL"):
        pytest.skip("VISION_MODEL not set")
    img = Image.new("RGB", (900, 300), "white")
    dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    dr.text((30, 60), "Refill: 28 tablets", fill="black", font=font)
    dr.text((30, 140), "Date 12 Oct", fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    d = extract_document(buf.getvalue(), "chemist_bill")
    blob = json.dumps(d.data.model_dump()).lower()
    assert d.status == "draft" and "28" in blob and "12" in blob
