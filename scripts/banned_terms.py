"""Banned-term scanner for patient- and Supporter-facing text (CLAUDE.md non-negotiable 5).

Scans:
  - cm/router/templates/*.yaml (every line)
  - fixtures/text_bank.json (patient_replies[].text only; doctor drafts are not patient-facing)
  - web/src/pages/PatientApp, web/src/pages/Supporter (.ts, .tsx)
  - web/src/components/i18n*.ts and i18n*.tsx

Matching:
  - "TB" is an uppercase whole word (so TBD, table and the code identifier tb do not match).
  - "tuberculosis" and the drug names are case-insensitive whole words.
  - Non-Latin terms from architecture section 3.11 (टीबी, क्षय, క్షయ) and "DOTS" are substring matches
    (DOTS is case-sensitive).

Usage: python scripts/banned_terms.py   (exit 0 when clean, exit 1 and file:line on each hit)
Make target: `make banned-terms` is declared in the Makefile (owned by L0); it currently points at
tests/unit/router/test_banned_terms.py, so run this script or tests/unit/content/ directly.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DRUG_NAMES = (
    "isoniazid",
    "rifampicin",
    "rifampin",
    "pyrazinamide",
    "ethambutol",
    "streptomycin",
    "rifapentine",
    "bedaquiline",
    "linezolid",
)

_LATIN_CI = re.compile(r"\b(tuberculosis|" + "|".join(DRUG_NAMES) + r")\b", re.IGNORECASE)
_TB_UPPER = re.compile(r"\bTB\b")
_DOTS = re.compile(r"\bDOTS\b")
_NON_LATIN = ("टीबी", "क्षय", "క్షయ", "టీబీ")

TEMPLATE_GLOB = "cm/router/templates/*.yaml"
TEXT_BANK = "fixtures/text_bank.json"
WEB_DIRS = ("web/src/pages/PatientApp", "web/src/pages/Supporter")
WEB_I18N_GLOBS = ("web/src/components/i18n*.ts", "web/src/components/i18n*.tsx")


@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    term: str
    text: str


def scan_text(text: str, source: str = "<text>") -> list[Hit]:
    """Return every banned-term hit in ``text``, with 1-based line numbers."""
    hits: list[Hit] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern in (_LATIN_CI, _TB_UPPER, _DOTS):
            for m in pattern.finditer(line):
                hits.append(Hit(source, lineno, m.group(0), line.strip()))
        for term in _NON_LATIN:
            if term in line:
                hits.append(Hit(source, lineno, term, line.strip()))
    return hits


def scan_file(path: Path, root: Path = REPO_ROOT) -> list[Hit]:
    rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    return scan_text(path.read_text(encoding="utf-8"), rel)


def _text_bank_hits(path: Path, root: Path) -> list[Hit]:
    """Scan only patient-facing fields of the text bank, reporting the line of each value."""
    rel = path.relative_to(root).as_posix()
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    hits: list[Hit] = []
    for item in data.get("patient_replies", []):
        value = item.get("text", "")
        for hit in scan_text(value, rel):
            needle = json.dumps(value, ensure_ascii=False)[1:-1]
            line = next((i for i, ln in enumerate(raw.splitlines(), 1) if needle in ln), 0)
            hits.append(Hit(rel, line, hit.term, hit.text))
    return hits


def scan_repo(root: Path = REPO_ROOT) -> list[Hit]:
    """Scan every patient- and Supporter-facing source listed in the module docstring."""
    hits: list[Hit] = []
    for p in sorted(root.glob(TEMPLATE_GLOB)):
        hits.extend(scan_file(p, root))
    text_bank = root / TEXT_BANK
    if text_bank.exists():
        hits.extend(_text_bank_hits(text_bank, root))
    for d in WEB_DIRS:
        base = root / d
        if base.is_dir():
            for p in sorted(base.rglob("*")):
                if p.suffix in (".ts", ".tsx") and p.is_file():
                    hits.extend(scan_file(p, root))
    for g in WEB_I18N_GLOBS:
        for p in sorted(root.glob(g)):
            hits.extend(scan_file(p, root))
    return hits


def main(argv: list[str] | None = None) -> int:
    hits = scan_repo()
    for h in hits:
        print(f"{h.path}:{h.line}: banned term {h.term!r}: {h.text}")
    if hits:
        print(f"banned-terms: {len(hits)} hit(s)", file=sys.stderr)
        return 1
    print("banned-terms: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
