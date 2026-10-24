"""fixtures/text_bank.json holds 30 patient replies and 30 doctor drafts, fictional and clean."""

from __future__ import annotations

import json
from pathlib import Path

from tests.unit.content.conftest import load_banned_terms

REPO_ROOT = Path(__file__).resolve().parents[3]
BANK = REPO_ROOT / "fixtures" / "text_bank.json"
INTENTS = {"taken", "missed", "unwell", "unclear"}


def _bank() -> dict:
    return json.loads(BANK.read_text(encoding="utf-8"))


def test_counts() -> None:
    bank = _bank()
    assert len(bank["patient_replies"]) == 30
    assert len(bank["doctor_drafts"]) == 30


def test_patient_replies_well_formed() -> None:
    replies = _bank()["patient_replies"]
    assert len({r["id"] for r in replies}) == 30
    for r in replies:
        assert r["lang"] in {"en", "te"}
        assert r["intent"] in INTENTS
        assert isinstance(r["text"], str) and r["text"].strip()


def test_doctor_drafts_well_formed() -> None:
    drafts = _bank()["doctor_drafts"]
    assert len({d["id"] for d in drafts}) == 30
    assert all(isinstance(d["text"], str) and d["text"].strip() for d in drafts)


def test_patient_replies_pass_banned_terms() -> None:
    banned = load_banned_terms()
    hits = banned.scan_repo(REPO_ROOT)
    assert [h for h in hits if h.path == "fixtures/text_bank.json"] == []
