"""Narrator: ORCHESTRATOR-model prose over computed features, then cite-or-cut, else a template card.

The model never sees raw rows, only the features and the citation ids it may use. It returns JSON that is
validated with Pydantic; any failure, budget stop or RED state yields the deterministic template card.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from cm.core.budget import BudgetError, TemplateOnlyMode
from cm.core.retry import ProviderCallFailed
from cm.core.tokenize import PIILeak, tokenize
from cm.memory.features import PatientFeatures
from cm.validator.banned_terms import find_banned_terms
from cm.validator.content_guard import content_violation
from cm.validator.cite_or_cut import Evidence, cite_or_cut

MAX_SENTENCES = 5


class NarratorOut(BaseModel):
    sentences: list[str] = Field(min_length=1, max_length=8)


@dataclass
class Card:
    sentences: list[str]
    source: str  # "model" | "template"
    cut: list[tuple[str, str]] = field(default_factory=list)
    reason: str = ""

    @property
    def text(self) -> str:
        return " ".join(self.sentences)


def evidence_for(f: PatientFeatures) -> Evidence:
    ids = set(f.event_ids) | {f"B-{k}" for k in (*f.numbers, *f.cites)}
    return Evidence.of(ids, f.numbers.values())


def _b(name: str) -> str:
    return f"[B-{name}]"


def _refs(f: PatientFeatures, key: str) -> str:
    return "".join(f"[{c}]" for c in dict.fromkeys(f.cites.get(key, [])[:3])) + _b(key)


def template_card(f: PatientFeatures, reason: str = "template") -> Card:
    """Deterministic card straight from the features; every sentence is cited and number-exact."""
    s: list[str] = []
    if f.missed_7d:
        s.append(f"Missed {f.missed_7d} doses in the last 7 days, {f.missed_3d} of them in the last 3 days {_refs(f, 'missed_7d')}.")
    if f.top_miss_weekday:
        n = f.weekday_misses[f.top_miss_weekday]
        s.append(f"Misses cluster on {f.top_miss_weekday}s ({n} so far) {_refs(f, 'weekday_pattern')}.")
    if f.refill_gap_days:
        s.append(f"Supply ran out {f.refill_gap_days} days ago with no refill recorded {_refs(f, 'refill_gap_days')}.")
    for c in f.conflicts:
        s.append(f"Self-report says {c['taken_7d']} doses taken in 7 days but the chemist shows no refill for "
                 f"{c['refill_gap_days']} days {_refs(f, 'taken_7d')}.")
    if f.quiet_days:
        s.append(f"No contact from the patient for {f.quiet_days} days {_refs(f, 'quiet_days')}.")
    if not s:
        s.append(f"No missed doses in the last 7 days; longest run taken {f.longest_streak} days {_b('longest_streak')}.")
    return Card(s, "template", reason=reason)


PROMPT = """You write a short memory card for a treating doctor from computed facts.
Rules: at most {n} sentences, plain words, no advice, no diagnosis, no drug or disease names.
Use ONLY the numbers in FACTS. End every sentence with one or more citation ids copied from CITES
(like [E-1a2b3c4d] or [B-missed_7d]), placed before the full stop. Never invent an id.
Reply with JSON only: {{"sentences": ["...", "..."]}}
FACTS: {facts}
CITES: {cites}"""


def _parse(raw: str) -> NarratorOut:
    m = re.search(r"\{.*\}", raw, re.S)
    return NarratorOut.model_validate_json(m.group(0) if m else raw)


def _invoke(model: Any, prompt: str, meta: dict[str, Any]) -> str:
    out = model.invoke(prompt, **meta) if hasattr(model, "gov") else model.invoke(prompt)
    c = out.content if hasattr(out, "content") else str(out)
    return c if isinstance(c, str) else json.dumps(c)


def write_card(f: PatientFeatures, model: Any, *, task_id: str = "adhoc", patient_id: str | None = None) -> Card:
    ev = evidence_for(f)
    facts = {k: v for k, v in f.as_dict().items() if k != "cites"}
    cites = {**f.cites, **{f"B-{n}": [f"B-{n}"] for n in f.numbers}}
    prompt = tokenize(PROMPT.format(n=MAX_SENTENCES, facts=json.dumps(facts, default=str), cites=json.dumps(cites)))
    meta = {"task_id": task_id, "task_type": "nightly_patient", "patient_id": patient_id}
    try:
        out = _parse(_invoke(model, prompt, meta))
    except TemplateOnlyMode:
        return template_card(f, "budget_red")
    except (BudgetError, ProviderCallFailed, PIILeak) as e:
        return template_card(f, f"model_unavailable:{type(e).__name__}")
    except (ValidationError, ValueError):
        return template_card(f, "bad_model_output")
    res = cite_or_cut(out.sentences[:MAX_SENTENCES], ev)
    kept = [s for s in res.kept if not find_banned_terms(s, "en")]
    res.cut += [(s, "banned_term") for s in res.kept if s not in kept]
    scoped: list[str] = []
    for s in kept:
        why = content_violation(s)
        (res.cut.append((s, why)) if why else scoped.append(s))
    kept = scoped
    if not kept:
        c = template_card(f, "all_cut")
        c.cut = res.cut
        return c
    return Card(kept, "model", res.cut)
