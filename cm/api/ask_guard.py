"""Lane G: deterministic guards for the Ask box (output guard, PII masking, intent routing).

No LLM is involved. The output guard runs on model text only; canned answers are built from rows and are
masked for PII but not content-filtered (a patient note may legitimately be quoted back to the doctor).
"""

from __future__ import annotations

import re
from typing import Any

from cm.core.tokenize import tokenize

REFUSAL_TEXT = (
    "I can't answer that safely. I only report what is in the patient records, and I do not give dosing "
    "advice or a diagnosis; that decision stays with you."
)

# ------------------------------------------------------------------------------------------- output guard
_ADVICE = [
    re.compile(
        r"\b(double|increase|decrease|reduce|raise|lower|stop|start|skip|halve|change|switch|add|adjust)\b"
        r"[^.]{0,40}\b(dose|doses|dosage|medicine|medicines|medication|tablets?|pills?|drugs?|treatment|"
        r"regimen)\b",
        re.I,
    ),
    re.compile(r"\b\d+(?:\.\d+)?\s?mg\b", re.I),
    re.compile(r"\b(you should|i recommend|i suggest|we recommend|prescribe)\b", re.I),
    re.compile(r"మోతాదు\s*(పెంచ|తగ్గ)|మందులు\s*ఆప"),
]
_DIAGNOSIS = re.compile(r"\b(diagnos\w*|resistan(?:ce|t)|relapse|hepatitis|liver damage)\b", re.I)
_INJECTION = re.compile(
    r"ignore (?:all |any |the )?(?:previous|prior|above) instructions|system prompt|admin mode|"
    r"developer mode|jailbreak|\ball clear\b|\byou are now\b|reply only with",
    re.I,
)
_NEGATION = re.compile(
    r"\b(not|cannot|can't|don't|do not|unable|never|won't|only the (?:treating )?doctor)\b|"
    r"కాదు|లేదు|లేను|చెప్పలేను|సలహా ఇవ్వలేను",
    re.I,
)
_SENT = re.compile(r"(?<=[.!?])\s+")
_QUOTED = re.compile(r'"[^"]*"|“[^”]*”')
_EVREF = re.compile(r"\s+E-\d+$")


def _strings(x: Any) -> list[str]:
    if isinstance(x, str):
        return [x, _EVREF.sub("", x)]
    if isinstance(x, dict):
        return [s for v in x.values() for s in _strings(v)]
    if isinstance(x, (list, tuple)):
        return [s for v in x for s in _strings(v)]
    return []


def _own_text(text: str, rows: list[dict[str, Any]]) -> str:
    """Model text without verbatim record echoes or quotations (quoting a note is not obeying it)."""
    own = text
    for s in sorted({s for s in _strings(rows) if len(s) >= 12}, key=len, reverse=True):
        own = own.replace(s, "")
    return _QUOTED.sub("", own)


def output_guard(text: str, rows: list[dict[str, Any]]) -> str | None:
    """Return a refusal reason ('advice', 'diagnosis', 'injection', 'banned_term') or None when clean."""
    from cm.router.banned import find_banned
    from cm.validator.banned_terms import find_banned_terms

    if find_banned(text) or find_banned_terms(text):
        return "banned_term"
    own = _own_text(text, rows)
    if _INJECTION.search(own):
        return "injection"
    for s in _SENT.split(own):
        if _NEGATION.search(s):
            continue
        if any(p.search(s) for p in _ADVICE):
            return "advice"
        if _DIAGNOSIS.search(s):
            return "diagnosis"
    return None


# ------------------------------------------------------------------------------------------- PII masking
_TOKEN = re.compile(r"\[([A-Z]+)_\d+\]")
_LABELS = {"PHONE": "phone", "EMAIL": "email", "AADHAAR": "id"}


def mask_pii(text: str) -> str:
    """Replace phone numbers, emails and Aadhaar-like ids with '(phone hidden)' style marks (no digits)."""
    out = tokenize(text)
    if out == text:
        return text
    return _TOKEN.sub(lambda m: f"({_LABELS[m.group(1)]} hidden)" if m.group(1) in _LABELS else m.group(0), out)


def mask_value(x: Any) -> Any:
    if isinstance(x, str):
        return mask_pii(x)
    if isinstance(x, dict):
        return {k: mask_value(v) for k, v in x.items()}
    if isinstance(x, list):
        return [mask_value(v) for v in x]
    return x


# ------------------------------------------------------------------------------------------- intent routing
def _w(*words: str) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(words) + r")\b", re.I)


EN: list[tuple[str, re.Pattern[str]]] = [
    ("first", _w("first", "urgent", "red", "worst", "priority", r"needs? (?:me|attention|review)")),
    ("quiet", _w("quiet", "silent", "no reply", "no data", "not replied", "gone dark")),
    ("refill", _w("refills?", "chemist", "supply")),
    ("requests", _w("requests?", "asks?", "asked", "waiting")),
    ("approvals", _w("approv\\w*", "drafts?")),
]
# Telugu has no reliable word boundaries for \b, so these are plain substrings of whole words/stems.
TE: list[tuple[str, tuple[str, ...]]] = [
    ("first", ("ముందుగా", "మొదట", "అత్యవసర", "ఎరుపు", "రెడ్", "ప్రాధాన్య")),
    ("quiet", ("నిశ్శబ్ద", "స్పందన లేదు", "సమాధానం లేదు", "జవాబు లేదు", "మాట్లాడటం లేదు")),
    ("refill", ("రీఫిల్", "సరఫరా", "మందుల షాప్", "కెమిస్ట్")),
    ("requests", ("అభ్యర్థన", "రిక్వెస్ట్")),
    ("approvals", ("ఆమోద", "డ్రాఫ్ట్")),
]


def route(question: str) -> str | None:
    """Intent name for a list question, or None. Telugu keywords are checked first, then English words."""
    for name, kws in TE:
        if any(k in question for k in kws):
            return name
    for name, pat in EN:
        if pat.search(question):
            return name
    return None
