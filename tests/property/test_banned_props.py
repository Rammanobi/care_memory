"""Banned-term scanners (non-negotiable 5) on the approved templates (EN + TE) and on fuzzed text.

Every runtime gate must agree: cm.router.banned (router + Telegram sender), cm.api.suppress (decide()),
cm.validator.banned_terms (narrator/orchestrator). A term that one gate misses reaches a patient.
"""

from __future__ import annotations

import re
import string
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cm.api import suppress
from cm.router import banned as router_banned
from cm.validator.banned_terms import find_banned_terms

REPO = Path(__file__).resolve().parents[2]
PROPS = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])

SCANNERS: dict[str, Callable[[str], list[str]]] = {
    "router": router_banned.find_banned,
    "suppress": suppress.find_banned,
    "validator_en": lambda t: find_banned_terms(t, "en"),
    "validator_te": lambda t: find_banned_terms(t, "te"),
}
# Terms every gate must catch (union of the CI list in scripts/banned_terms.py).
CORE_TERMS = [
    "TB", "tuberculosis", "Tuberculosis", "TUBERCULOSIS", "isoniazid", "Rifampicin", "rifampin",
    "pyrazinamide", "Ethambutol", "streptomycin", "rifapentine", "bedaquiline", "Linezolid",
    "DOTS", "టీబీ", "క్షయ", "टीबी", "क्षय",
]  # fmt: skip


def _strings(node: Any) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _templates() -> list[tuple[str, str, dict[str, Any], list[str]]]:
    out = []
    for f in sorted((REPO / "cm/router/templates").glob("*.yaml")):
        for t in yaml.safe_load(f.read_text(encoding="utf-8"))["templates"]:
            for lang, body in t["languages"].items():
                out.append((f"{t['id']}:{lang}", lang, body, t.get("placeholders") or []))
    return out


TEMPLATES = _templates()


def test_templates_cover_en_and_te() -> None:
    langs = {lang for _, lang, _, _ in TEMPLATES}
    assert {"en", "te"} <= langs and len(TEMPLATES) >= 20


@pytest.mark.parametrize("tid,lang,body,slots", TEMPLATES, ids=[t[0] for t in TEMPLATES])
def test_every_template_string_is_clean_for_every_gate(
    tid: str, lang: str, body: dict[str, Any], slots: list[str]
) -> None:
    for text in _strings(body):
        for name, scan in SCANNERS.items():
            assert scan(text) == [], f"{tid} flagged by {name}: {text!r}"


safe_slot = st.text(alphabet=string.ascii_letters + " 0123456789:-", min_size=1, max_size=20).filter(
    lambda s: all(not scan(s) for scan in SCANNERS.values())
)


@PROPS
@given(st.sampled_from(TEMPLATES), st.data())
def test_rendering_clean_slots_stays_clean(tpl: tuple, data: st.DataObject) -> None:
    tid, _lang, body, slots = tpl
    values = {s: data.draw(safe_slot, label=s) for s in slots}
    for text in _strings(body):
        rendered = text.format(**values) if slots else text
        for name, scan in SCANNERS.items():
            assert scan(rendered) == [], f"{tid} rendered dirty via {name}: {rendered!r}"


sep = st.sampled_from([" ", ", ", ". ", "\n", " (", "! ", ": "])
words = st.text(alphabet=string.ascii_lowercase + " ", max_size=15)
te_words = st.sampled_from(["", "మీ మందు ", "ఈరోజు ", "దయచేసి "])


@PROPS
@given(words, te_words, sep, st.sampled_from(CORE_TERMS), sep, words)
def test_injected_banned_term_is_caught_by_every_gate(
    pre: str, te: str, s1: str, term: str, s2: str, post: str
) -> None:
    text = f"{pre}{te}{s1}{term}{s2}{post}"
    for name, scan in SCANNERS.items():
        assert scan(text), f"{name} missed {term!r} in {text!r}"


def test_tb_variants_router_gate() -> None:
    for v in ("T.B.", "t.b", "T B", "tb"):
        assert router_banned.find_banned(f"your {v} check"), v
    # whole-word rule: "tb"/"dots" inside ordinary words is not a hit
    for ok in ("outbound", "hotbed", "anecdotes", "tablet"):
        assert router_banned.find_banned(ok) == [], ok
    assert re.search("tb", "outbound")  # sanity: the substring really is there
