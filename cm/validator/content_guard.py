"""Deterministic content guard for narrator sentences (no LLM): dosing advice, diagnosis claims, blaming tone.

Cite-or-cut proves a sentence is grounded; this proves it stays in scope. Regex and keyword lists, English and
Telugu. ``content_violation`` returns a cut reason or None. Pure and side-effect free.
"""

from __future__ import annotations

import re

_DOSE_NOUN = r"(?:dose|doses|dosage|medicine|medicines|medication|tablets?|pills?|drugs?|treatment|regimen)"
_ADVICE_VERB = r"(?:double|increase|decrease|reduce|raise|lower|stop|start|skip|halve|change|switch|add|adjust|take extra)"
_DOSING_EN = [
    # imperative at sentence start, or after a modal / recommendation
    re.compile(
        rf"(?:^|[.;:]\s*|\b(?:should|must|need to|needs to|please|recommend|advise|suggest|to|try to|consider)\s+)"
        rf"{_ADVICE_VERB}\b[^.]{{0,40}}\b{_DOSE_NOUN}\b",
        re.I,
    ),
    re.compile(r"\b(?:make up for|compensate for|catch up on)\b[^.]{0,30}\b(?:missed )?" + _DOSE_NOUN, re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|ml)\b", re.I),
    re.compile(r"\b(?:you should|i recommend|i suggest|we recommend|prescribe[sd]?|should be given)\b", re.I),
]
_DOSING_TE = [
    re.compile(r"మోతాదు\s*(?:పెంచ|తగ్గ|మార్చ|రెట్టింపు)"),
    re.compile(r"మందులు\s*(?:ఆపండి|ఆపేయ|ఆపి|మానేయ|మార్చ)"),
    re.compile(r"(?:రెట్టింపు|అదనపు)\s*(?:మోతాదు|మందు)"),
]
_DIAGNOSIS_EN = [
    re.compile(r"\b(?:diagnos\w*|resistan(?:ce|t)|relapse[sd]?|hepatitis|liver damage|treatment failure|"
               r"default(?:ed|er)|infectious|contagious|drug[- ]induced)\b", re.I),
    re.compile(r"\b(?:suggests?|indicates?|points? to|consistent with|likely|probably|signs? of)\b"
               r"[^.]{0,40}\b(?:infection|disease|condition|failure|resistance|relapse|deterioration|worsening)\b", re.I),
]
_DIAGNOSIS_TE = [re.compile(r"నిర్ధారణ|నిరోధకత|రోగ నిర్ధారణ|కాలేయ|హెపటైటిస్|తిరగబెట్ట")]
_BLAME_EN = [
    re.compile(r"\b(?:careless|lazy|irresponsible|non-?complian\w*|defaulter|stubborn|negligent|reckless|"
               r"uncooperative|unreliable|deliberately|refuses?|refusing|own fault|to blame|blame[sd]?|excuses?)\b",
               re.I),
]
_BLAME_TE = [re.compile(r"నిర్లక్ష్య|సోమరి|బాధ్యతారహిత|మొండి|తప్పు\s*(?:వారిదే|అతనిదే|ఆమెదే)")]
_CAPS = re.compile(r"\b[A-Z]{4,}\b")
_ID_LIKE = re.compile(r"\[[^\]]*\]")


def content_violation(sentence: str) -> str | None:
    """Return ``dosing_advice`` | ``diagnosis`` | ``blame_tone`` when the sentence breaks scope, else None."""
    s = _ID_LIKE.sub("", sentence).strip()
    if any(p.search(s) for p in (*_DOSING_EN, *_DOSING_TE)):
        return "dosing_advice"
    if any(p.search(s) for p in (*_DIAGNOSIS_EN, *_DIAGNOSIS_TE)):
        return "diagnosis"
    if any(p.search(s) for p in (*_BLAME_EN, *_BLAME_TE)) or "!" in s or _CAPS.search(s):
        return "blame_tone"
    return None
