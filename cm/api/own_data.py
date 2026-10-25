"""Lane G: instant, code-computed answers about the patient's OWN record (website only).

Every number comes from ``cm.memory.features`` or the events store; sentences are the approved templates in
``cm/router/templates/own_data.yaml``. No model, no advice, no comparison with other patients.
Pure functions: events and ``as_of`` in, cards out (non-negotiables 3, 4, 5, 9).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from cm.api.suppress import is_clean
from cm.core.config import REPO_ROOT
from cm.core.tokenize import tokenize
from cm.memory.features import _checkins, _day, compute_features

YAML_PATH = Path(REPO_ROOT) / "cm" / "router" / "templates" / "own_data.yaml"
MIN_CHECKINS = 3
LANGS = ("en", "te")

# Static card titles (fixed labels, no data in them).
QUESTIONS: dict[str, dict[str, str]] = {
    "taken_week": {"en": "How many doses did I take this week?", "te": "ఈ వారం నేను ఎన్ని డోసులు తీసుకున్నాను?"},
    "missed_week": {"en": "How many doses did I miss this week?", "te": "ఈ వారం నేను ఎన్ని డోసులు తీసుకోలేదు?"},
    "streak": {"en": "How many days in a row have I taken my medicine?", "te": "వరుసగా ఎన్ని రోజులు మందు తీసుకున్నాను?"},
    "next_visit": {"en": "When is my next visit?", "te": "నా తదుపరి సందర్శన ఎప్పుడు?"},
    "last_refill": {"en": "When was my last refill?", "te": "నా చివరి రీఫిల్ ఎప్పుడు?"},
    "history": {"en": "How is my record so far?", "te": "ఇప్పటి వరకు నా రికార్డు ఎలా ఉంది?"},
    "advice": {"en": "Questions about medicines, food or symptoms", "te": "మందులు, ఆహారం లేదా లక్షణాల గురించి ప్రశ్నలు"},
}


@lru_cache(maxsize=1)
def _templates() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    return {t["kind"]: t for t in data["templates"] if t.get("doctor_approved")}


def render(kind: str, lang: str, **slots: Any) -> str:
    """Approved template text in ``lang`` (EN fallback) with code-computed slots filled in."""
    langs = _templates()[kind]["languages"]
    return str(langs[lang if lang in langs else "en"]["telegram"]).format(**slots)


def current_streak(events: Iterable[dict[str, Any]], as_of: datetime) -> int:
    """Days taken in a row ending today; a day not yet recorded today does not break the run."""
    evs = [e for e in events if e["occurred_at"] <= as_of and e["recorded_at"] <= as_of]
    by_day = _checkins(evs)
    d = _day(as_of)

    def taken(x: date) -> bool:
        return x in by_day and by_day[x]["payload"].get("status") == "taken"

    if d not in by_day:
        d -= timedelta(days=1)
    n = 0
    while taken(d):
        n += 1
        d -= timedelta(days=1)
    return n


def last_refill(events: Iterable[dict[str, Any]], as_of: datetime) -> date | None:
    days = [
        _day(e["occurred_at"])
        for e in events
        if e["type"] == "Dispense" and e["occurred_at"] <= as_of and e["recorded_at"] <= as_of
    ]
    return max(days) if days else None


def next_visit_text(summary: dict[str, Any], appointments: list[dict[str, Any]]) -> str | None:
    """The clinic's recorded next visit (summary first, else first upcoming visit); None if absent or unsafe."""
    nv = summary.get("next_visit")
    if isinstance(nv, str) and safe_when(nv):
        return nv.strip()
    for a in appointments:
        if a.get("bucket") == "upcoming" and a.get("appt_kind") == "visit":
            when = str(a.get("when") or "").strip()
            if safe_when(when):
                return when
    return None


_WHEN = re.compile(r"[A-Za-z0-9ఀ-౿ ,:./-]{1,40}")


def safe_when(text: str) -> bool:
    """The {when} slot holds a short date/time phrase only ('Wed 6 pm'): no sentence, no phone or id, no banned
    term. Anything else is free text, which an approved template must never carry (withheld, never rewritten)."""
    s = (text or "").strip()
    return (
        bool(_WHEN.fullmatch(s))
        and len(s.split()) <= 6
        and not re.search(r"\.(\s|$)|\d{5,}", s)
        and tokenize(s) == s
        and is_clean(s)
    )


def week_window(events: Iterable[dict[str, Any]], as_of: datetime, treatment_start: date | None = None) -> int:
    """Days the '7 day' counts really cover: capped by days since treatment start (else the first check-in)."""
    start = treatment_start
    if start is None:
        days = [_day(e["occurred_at"]) for e in events if e["type"] == "DoseCheckin" and e["occurred_at"] <= as_of]
        start = min(days) if days else None
    if start is None:
        return 7
    return max(1, min(7, (_day(as_of) - start).days + 1))


def _card(topic: str, lang: str, text: str, numbers: dict[str, Any], as_of: datetime) -> dict[str, Any]:
    return {
        "topic": topic,
        "question": QUESTIONS[topic][lang],
        "answer_text": text,
        "numbers": numbers,
        "as_of": as_of,
        "lang": lang,
    }


def build_answers(
    events: list[dict[str, Any]],
    summary: dict[str, Any],
    appointments: list[dict[str, Any]],
    as_of: datetime,
    lang: str,
    treatment_start: date | None = None,
) -> list[dict[str, Any]]:
    """Answer cards visible at ``as_of`` (events after it are ignored), advice footer last."""
    lang = lang if lang in LANGS else "en"
    f = compute_features(events, as_of)
    cards: list[dict[str, Any]] = []
    if f.checkins_total < MIN_CHECKINS:
        cards.append(_card("history", lang, render("own_data_none_v1", lang), {"checkins_total": f.checkins_total}, as_of))
    else:
        streak = current_streak(events, as_of)
        w = week_window(events, as_of, treatment_start)
        cards += [
            _card("taken_week", lang, render("own_data_taken_week_v1", lang, taken=f.taken_7d, window=w), {"taken_7d": f.taken_7d, "window": w}, as_of),
            _card("missed_week", lang, render("own_data_missed_week_v1", lang, missed=f.missed_7d, window=w), {"missed_7d": f.missed_7d, "window": w}, as_of),
            _card("streak", lang, render("own_data_streak_v1", lang, days=streak), {"streak_days": streak}, as_of),
        ]
    nv = next_visit_text(summary, appointments)
    cards.append(
        _card("next_visit", lang, render("own_data_next_visit_v1", lang, when=nv), {}, as_of)
        if nv
        else _card("next_visit", lang, render("own_data_no_visit_v1", lang), {}, as_of)
    )
    rf = last_refill(events, as_of)
    cards.append(
        _card("last_refill", lang, render("own_data_last_refill_v1", lang, date=rf.strftime("%d-%m-%Y")), {}, as_of)
        if rf
        else _card("last_refill", lang, render("own_data_no_refill_v1", lang), {}, as_of)
    )
    cards.append(_card("advice", lang, render("own_data_advice_v1", lang), {}, as_of))
    return cards
