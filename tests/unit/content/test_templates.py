"""Every approved template parses, declares its placeholders and has both languages."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = REPO_ROOT / "cm" / "router" / "templates"
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
REQUIRED_KINDS = {
    "daily_checkin_reminder",
    "missed_dose_nudge",
    "visit_reminder",
    "lab_reminder",
    "refill_reminder",
    "reminder_time_changed",
    "visit_moved",
    "request_received",
    "supporter_weekly_summary",
    "consent_confirmation",
    "consent_revoke_confirmation",
    "emergency_note",
}
TE_COMMENT = re.compile(r"^\s+te:\s*\n\s+# needs native-speaker review", re.MULTILINE)


def _files() -> list[Path]:
    return sorted(TEMPLATE_DIR.glob("*.yaml"))


def _templates() -> list[tuple[str, dict]]:
    out = []
    for path in _files():
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for tpl in doc["templates"]:
            out.append((path.name, tpl))
    return out


def _strings(tpl: dict, lang: str) -> list[str]:
    block = tpl["languages"][lang]
    return [block["telegram"], block["email"]["subject"], block["email"]["body"]]


def test_template_files_exist_and_parse() -> None:
    assert _files(), "no template YAML files found"
    for path in _files():
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(doc.get("templates"), list), path.name


def test_all_required_kinds_present_once() -> None:
    kinds = [tpl["kind"] for _, tpl in _templates()]
    assert set(kinds) == REQUIRED_KINDS
    assert len(kinds) == len(set(kinds)), "duplicate kind"


def test_ids_are_unique() -> None:
    ids = [tpl["id"] for _, tpl in _templates()]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(("fname", "tpl"), _templates(), ids=lambda v: v if isinstance(v, str) else v["id"])
def test_template_fields(fname: str, tpl: dict) -> None:
    assert tpl["audience"] in {"patient", "supporter"}
    assert tpl["tier"] == "green"
    assert tpl["doctor_approved"] is True
    assert isinstance(tpl["placeholders"], list) and tpl["placeholders"]
    assert set(tpl["languages"]) == {"en", "te"}, "both en and te are required"


@pytest.mark.parametrize(("fname", "tpl"), _templates(), ids=lambda v: v if isinstance(v, str) else v["id"])
def test_placeholders_declared_and_used_in_both_languages(fname: str, tpl: dict) -> None:
    declared = set(tpl["placeholders"])
    assert len(declared) == len(tpl["placeholders"]), "duplicate placeholder declaration"
    for lang in ("en", "te"):
        used: set[str] = set()
        for text in _strings(tpl, lang):
            assert isinstance(text, str) and text.strip(), f"{tpl['id']} {lang} has an empty string"
            used.update(PLACEHOLDER.findall(text))
        assert used <= declared, f"{tpl['id']} {lang} uses undeclared {used - declared}"
        assert declared <= used, f"{tpl['id']} {lang} never uses {declared - used}"


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name)
def test_telugu_blocks_carry_review_comment(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    te_blocks = len(re.findall(r"^\s+te:\s*$", text, re.MULTILINE))
    assert te_blocks > 0
    assert len(TE_COMMENT.findall(text)) == te_blocks


def test_telugu_differs_from_english() -> None:
    for _, tpl in _templates():
        assert tpl["languages"]["te"]["telegram"] != tpl["languages"]["en"]["telegram"]
