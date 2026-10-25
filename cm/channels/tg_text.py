"""Lane F: free-text handling for the Telegram chat. Plain Python, no LLM, no network.

* ``classify``: danger words (English and Telugu) and medicine-advice questions. Both are only ever
  routed to the doctor; the system never answers them.
* ``ack_text``: the ONE pre-approved acknowledgement (templates in confirmations.yaml, doctor_approved).
  Nothing the patient typed is echoed back (non-negotiable 4 and 5).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from cm.core.config import REPO_ROOT
from cm.router.banned import find_banned

MAX_TEXT = 2000  # Telegram allows 4096; the doctor needs the gist, not a novel
ACK_WINDOW_S = 10 * 60
ACK_TEMPLATE = "telegram_ack_v1"
ACK_URGENT_TEMPLATE = "telegram_ack_urgent_v1"
YAML_PATH = Path(REPO_ROOT) / "cm" / "router" / "templates" / "confirmations.yaml"
FALLBACK_NAME = "friend"

# English danger words: whole-word regex on the lower-cased text. Over-triage is the safe error.
_DANGER_EN = re.compile(
    r"\b(blood|bleeding|vomit\w*|jaundice|yellow\s+(eyes?|skin)|breathless\w*|can'?t\s+breathe|"
    r"cannot\s+breathe|short\s+of\s+breath|difficulty\s+breathing|chest\s+pain|faint\w*|"
    r"unconscious|seizure|fits|severe|very\s+(sick|unwell|ill)|emergency|dying|rash|"
    r"blurred?\s+vision|cannot\s+see|can'?t\s+see)\b"
)
# Telugu danger words: substring match (agglutinative suffixes follow the stem).
_DANGER_TE = (
    "రక్తం", "రక్త", "వాంతి", "వాంతు", "కామెర్లు", "పసుపు", "ఊపిరి", "శ్వాస", "ఛాతీ", "ఛాతి",
    "స్పృహ", "మూర్ఛ", "తలతిరుగ", "తల తిరుగ", "చాలా బాగోలేదు", "చాలా నొప్పి", "దద్దుర్లు", "కళ్ళు కనిపించ",
)
# Medicine-advice requests: stop, skip, double, change, side effects.
_ADVICE_EN = re.compile(
    r"\b(should\s+i|can\s+i|may\s+i|shall\s+i|do\s+i\s+need\s+to|is\s+it\s+ok(ay)?\s+to|what\s+if\s+i)\b"
    r".{0,60}\b(stop|skip|miss|quit|leave|double|extra|more|less|reduce|increase|change|take|taking|"
    r"drink|alcohol|eat|mix)\b"
    r"|\b(stop|stopped|skip|quit|leave|reduce)\w*\s+(taking\s+)?(the\s+|my\s+)?(tablets?|pills?|medicines?|"
    r"medication|doses?|treatment)\b"
    r"|\b(side\s+effects?|too\s+many\s+(tablets?|pills?)|overdose|double\s+dose)\b"
)
_ADVICE_TE = ("ఆపాలా", "ఆపవచ్చా", "మానేయ", "ఆపేయ", "మాత్రలు ఆప", "మందు ఆప", "ఎక్కువ మాత్ర", "రెండు మాత్ర",
              "దుష్ప్రభావ", "తీసుకోవచ్చా", "వేసుకోవచ్చా")


def normalise(text: str) -> str:
    return unicodedata.normalize("NFC", text or "").strip()


def classify(text: str) -> str:
    """``"danger"``, ``"advice"`` or ``"normal"``. Danger wins over advice."""
    t = normalise(text).lower().replace("’", "'")
    if _DANGER_EN.search(t) or any(w in t for w in _DANGER_TE):
        return "danger"
    if _ADVICE_EN.search(t) or any(w in t for w in _ADVICE_TE):
        return "advice"
    return "normal"


def clip(text: str) -> tuple[str, bool]:
    """Text as stored: normalised and cut at MAX_TEXT characters. Second value says it was cut."""
    t = normalise(text)
    return (t[:MAX_TEXT], True) if len(t) > MAX_TEXT else (t, False)


def text_sha(text: str) -> str:
    return hashlib.sha256(" ".join(normalise(text).lower().split()).encode()).hexdigest()[:32]


def load_template(template_id: str) -> dict[str, Any]:
    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    for t in data["templates"]:
        if t["id"] == template_id:
            if not t.get("doctor_approved"):
                raise ValueError(f"template {template_id} is not doctor approved")
            return t
    raise KeyError(template_id)


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return ""


def template_text(template_id: str, lang: str, first_name: str | None = None) -> str:
    """Telegram text of an approved template, EN or TE. Same name and banned-term rules as ``ack_text``."""
    langs = load_template(template_id)["languages"]
    use = lang if lang in langs else "en"
    name = first_name if first_name and not find_banned(first_name) else FALLBACK_NAME
    text = langs[use]["telegram"].format_map(_Safe(first_name=name))
    if find_banned(text):
        raise ValueError(f"template {template_id} contains a banned term")
    return text


def ack_text(urgent: bool, lang: str, first_name: str | None = None) -> tuple[str, str]:
    """(template_id, text) for the acknowledgement, EN or TE. The name is the safe vault first name or
    the neutral fallback; banned words never get through (the template itself is also banned-term clean)."""
    tid = ACK_URGENT_TEMPLATE if urgent else ACK_TEMPLATE
    langs = load_template(tid)["languages"]
    use = lang if lang in langs else "en"
    name = first_name if first_name and not find_banned(first_name) else FALLBACK_NAME
    text = langs[use]["telegram"].format(first_name=name)
    if find_banned(text):
        raise ValueError(f"template {tid} contains a banned term")
    return tid, text
