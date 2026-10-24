"""Lane B: ground truth (evaluator only). Never imported by the engine path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .gen import SimPatient


def truth_of(patients: list[SimPatient]) -> dict[str, Any]:
    return {
        p.token: {"taken": [int(x) for x in p.taken], "patterns": p.patterns, "base_rate": p.base_rate}
        for p in patients
    }


def write_truth(path: str | Path, patients: list[SimPatient]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(truth_of(patients), sort_keys=True), encoding="utf-8")


def load_truth(path: str) -> Any:
    """Read truth.json (evaluator only)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
