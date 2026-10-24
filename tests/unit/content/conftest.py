"""Load scripts/banned_terms.py without making scripts/ a package."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_banned_terms() -> ModuleType:
    spec = importlib.util.spec_from_file_location("banned_terms", REPO_ROOT / "scripts" / "banned_terms.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
