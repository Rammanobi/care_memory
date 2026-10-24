"""scripts/banned_terms.py: clean on the repo, and catches a deliberately bad sample."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.unit.content.conftest import load_banned_terms

REPO_ROOT = Path(__file__).resolve().parents[3]
banned = load_banned_terms()


def test_repo_is_clean() -> None:
    hits = banned.scan_repo(REPO_ROOT)
    assert hits == [], "\n".join(f"{h.path}:{h.line} {h.term!r}" for h in hits)


def test_cli_exit_zero_on_repo() -> None:
    assert banned.main([]) == 0


@pytest.mark.parametrize(
    "sample",
    [
        "Your TB medicine is ready.",
        "Mild tuberculosis symptoms.",
        "Take isoniazid tonight.",
        "rifampicin is next.",
        "Ask about Linezolid.",
        "టీబీ గురించి",
        "క్షయ వ్యాధి",
        "DOTS visit today",
    ],
)
def test_bad_samples_are_caught(sample: str) -> None:
    assert banned.scan_text(sample), sample


@pytest.mark.parametrize("sample", ["TBD: call the clinic", "Please see the table", "tb is a variable name"])
def test_word_boundary_avoids_false_positives(sample: str) -> None:
    assert banned.scan_text(sample) == [], sample


def test_hit_reports_file_and_line(tmp_path: Path) -> None:
    bad = tmp_path / "bad_template.yaml"
    bad.write_text("ok line\nsecond line\nYour TB medicine is ready.\n", encoding="utf-8")
    hits = banned.scan_file(bad, root=tmp_path)
    assert len(hits) == 1
    assert hits[0].path == "bad_template.yaml"
    assert hits[0].line == 3
    assert hits[0].term == "TB"


def test_text_bank_patient_field_is_checked(tmp_path: Path) -> None:
    bank = tmp_path / "fixtures" / "text_bank.json"
    bank.parent.mkdir(parents=True)
    payload = {
        "patient_replies": [{"id": "x", "text": "I took my isoniazid this morning."}],
        "doctor_drafts": [{"id": "y", "text": "TB screen is due."}],
    }
    bank.write_text(json.dumps(payload), encoding="utf-8")
    hits = banned._text_bank_hits(bank, tmp_path)
    assert [h.term for h in hits] == ["isoniazid"]
