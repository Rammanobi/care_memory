"""firebase.json / .firebaserc templates: separate doctor + patient sites, API rewrites, no internal routes."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CFG = json.loads((ROOT / "firebase.json").read_text(encoding="utf-8"))
RC = json.loads((ROOT / ".firebaserc").read_text(encoding="utf-8"))


def _sites() -> dict[str, dict]:
    return {s["target"]: s for s in CFG["hosting"]}


def test_separate_doctor_and_patient_sites() -> None:
    sites = _sites()
    assert {"doctor", "patient"} <= set(sites)
    assert sites["doctor"]["redirects"][0]["destination"] == "/doctor"
    assert sites["patient"]["redirects"][0]["destination"] == "/patient"


def test_rewrites_api_to_cloud_run_and_spa_last() -> None:
    for s in _sites().values():
        rw = s["rewrites"]
        assert rw[-1] == {"source": "**", "destination": "/index.html"}
        run_sources = {r["source"] for r in rw if "run" in r}
        for p in ("auth", "review", "patients", "portal", "admin", "dashboard", "consents"):
            assert f"/{p}{{,/**}}" in run_sources
        assert all(r["run"] == {"serviceId": "cm-api", "region": "asia-south1"} for r in rw if "run" in r)
        for internal in ("tasks", "webhooks", "stream"):
            assert not any(src.startswith(f"/{internal}") for src in run_sources)


def _vars_default(name: str) -> str:
    """Default of `export NAME="${NAME:-value}"` in infra/vars.sh (the one place for project and site ids)."""
    text = (ROOT / "infra" / "vars.sh").read_text(encoding="utf-8")
    m = re.search(rf'^export {name}="\$\{{{name}:-([^}}]*)\}}"', text, re.M)
    assert m, name
    return m.group(1)


def test_firebaserc_matches_infra_vars() -> None:
    project = RC["projects"]["default"]
    assert project == _vars_default("PROJECT")
    targets = RC["targets"][project]["hosting"]
    assert set(targets) == {"doctor", "patient"}
    assert targets["doctor"] == [_vars_default("DOCTOR_SITE")]
    assert targets["patient"] == [_vars_default("PATIENT_SITE")]
