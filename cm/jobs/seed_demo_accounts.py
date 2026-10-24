"""Demo accounts with 3 / 30 / 60 days of mock history (additive, idempotent, deterministic).

    python -m cm.jobs.seed_demo_accounts                      # create (or no-op) on the DB_* target
    python -m cm.jobs.seed_demo_accounts --no-embed           # skip real embeddings (full-text only)
    python -m cm.jobs.seed_demo_accounts --skip-pipeline      # rows only, no memory nightly / rag index
    python -m cm.jobs.seed_demo_accounts --export out/demo_accounts.json
    python -m cm.jobs.seed_demo_accounts --import out/demo_accounts.json

Accounts (patient token -> code, history, archetype):
    P-0903 / PT-0903   3 days   steady adherer, English        user demo.pt0903
    P-0930 / PT-0930  30 days   market-day misses, Telugu      user demo.pt0930 + Supporter demo.sup0930 (S-93)
    P-0960 / PT-0960  60 days   payday misses, English         user demo.pt0960

Safety: refuses unless CM_DATA_CLASS=mock. Never wipes, never reseeds, never touches PT-0142 or any Telegram
binding. The target DB is the normal DB_* environment; the data is identical on every database (fixed seeds,
fixed sim day 0 = 2026-08-27, fixed as_of = sim day 59 18:00 IST, deterministic ids).
Passwords: env DEMO_ACCOUNT_PASSWORDS ('{"demo.pt0903": "..."}'), else out/demo_accounts_credentials.txt
(git-ignored, read if present, else generated there). Passwords are never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import secrets
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from cm.api.auth import hash_password
from cm.core import clock
from cm.core.config import REPO_ROOT, load_dotenv, load_settings
from cm.core.db import close_pool, connect_direct
from cm.core.ids import det_id
from cm.jobs import migrate
from cm.sim import gen, noise
from cm.store import events_repo as ev
from cm.store.events_repo import NewEvent

DAY0 = date(2026, 8, 27)  # same sim day 0 as the main seed
AS_OF_DAY = 59
CRED_FILE = REPO_ROOT / "out" / "demo_accounts_credentials.txt"
CLINIC = "anantapur"
BUNDLE_VERSION = 1
CONSENT_SOURCES = ("web", "telegram", "chemist", "supporter")
IST = clock.IST

ACCOUNTS: list[dict[str, Any]] = [
    {"code": "PT-0903", "token": "P-0903", "days": 3, "seed": 9007, "base": 0.93, "patterns": [],
     "market_dow": 1, "lang": "en", "sex": "F", "age": 38, "user": "demo.pt0903", "supporter": None},
    {"code": "PT-0930", "token": "P-0930", "days": 30, "seed": 9030, "base": 0.88, "patterns": ["market_day"],
     "market_dow": 1, "lang": "te", "sex": "M", "age": 46, "user": "demo.pt0930",
     "supporter": {"token": "S-93", "user": "demo.sup0930", "name": "Meena", "lang": "te"}},
    {"code": "PT-0960", "token": "P-0960", "days": 60, "seed": 9060, "base": 0.86, "patterns": ["payday"],
     "market_dow": 1, "lang": "en", "sex": "F", "age": 52, "user": "demo.pt0960", "supporter": None},
]
DEMO_TOKENS = [a["token"] for a in ACCOUNTS] + ["S-93"]

TEXT = {  # (lang, pattern) -> missed-day note, all free of clinical vocabulary
    ("en", "market_day"): "I went to the weekly market and forgot my tablets.",
    ("te", "market_day"): "సంతకు వెళ్లాను, మందులు మర్చిపోయాను.",
    ("en", "payday"): "I went to collect my wages and came home late, missed the dose.",
    ("te", "payday"): "కూలి డబ్బులు తీసుకోవడానికి వెళ్లాను, ఆలస్యమైంది.",
    ("en", "other"): "I forgot to take my tablets today.",
    ("te", "other"): "ఈ రోజు మందులు వేసుకోవడం మర్చిపోయాను.",
}
START_NOTE = {
    "en": "I take my tablets after breakfast every morning.",
    "te": "నేను రోజూ ఉదయం టిఫిన్ తర్వాత మందులు వేసుకుంటాను.",
}
SUPPORTER_NOTE = {
    "en": "Visited today. The patient is taking the tablets on most days.",
    "te": "ఈ రోజు ఇంటికి వెళ్లాను. చాలా రోజులు మందులు వేసుకుంటున్నారు.",
}


class DemoSeedError(RuntimeError):
    pass


def as_of_instant() -> datetime:
    return clock.sim_instant(DAY0, AS_OF_DAY)


def today_ist() -> date:
    return as_of_instant().astimezone(IST).date()


def _at(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=IST)


def _cid(token: str, source: str, purpose: str) -> str:
    return str(det_id("consent", token, source, purpose))


def _misses(rng: random.Random, a: dict[str, Any], d: date) -> bool | None:
    """One day of the cm.sim.gen behaviour model: true intake, then reporting noise (None = silent day)."""
    p = gen._p_taken((d - gen.DAY0).days, a["base"], a["patterns"], a["market_dow"])
    taken = rng.random() < p
    return noise.observe(rng, taken, False)


def _reason_key(a: dict[str, Any], d: date) -> str:
    gd = (d - gen.DAY0).days
    if "market_day" in a["patterns"] and d.weekday() == a["market_dow"]:
        return "market_day"
    if "payday" in a["patterns"] and gd % 30 in (0, 1, 2):
        return "payday"
    return "other"


def _ev(a: dict[str, Any], typ: str, occ: datetime, key: str, payload: dict[str, Any], **kw: Any) -> dict[str, Any]:
    lag = kw.pop("lag", timedelta(minutes=2))
    return {
        "event_id": str(det_id("event", key)), "patient": a["code"], "type": typ,
        "occurred_at": occ.isoformat(), "recorded_at": (occ + lag).isoformat(),
        "idempotency_key": key, "payload": payload, "source": kw.get("source", "web"),
        "reporter_mode": kw.get("reporter_mode", "self"), "channel": kw.get("channel", "portal"),
        "reporter": kw.get("reporter"), "consent_id": kw.get("consent_id"),
    }


def patient_events(a: dict[str, Any]) -> list[dict[str, Any]]:
    """All events of one account: dose check-ins, patient notes, refills, supporter visits, summary."""
    rng, lang, code = random.Random(a["seed"]), a["lang"], a["code"]  # noqa: S311
    end, n = today_ist(), a["days"]
    start = end - timedelta(days=n)
    web = _cid(a["token"], "web", "care_coordination")
    out: list[dict[str, Any]] = []
    missed_days: list[int] = []
    for i in range(n):
        d = start + timedelta(days=i)
        rep = _misses(rng, a, d)
        if rep is None:
            continue
        status = "taken" if rep else "missed"
        key = f"demo:{code}:dose:{d.isoformat()}"
        reason = _reason_key(a, d) if status == "missed" else None
        out.append(_ev(a, "DoseCheckin", _at(d, 8), key, {"status": status, "reason": reason},
                       reporter=a["token"], consent_id=web))
        if status == "missed":
            missed_days.append(i + 1)
            out.append(_ev(a, "ContextNote", _at(d, 21), f"demo:{code}:note:{d.isoformat()}",
                           {"kind": "free_text", "origin": "patient_text",
                            "text_tokenised": TEXT[(lang, reason)]},
                           reporter=a["token"], consent_id=web))
    out.append(_ev(a, "ContextNote", _at(start, 9), f"demo:{code}:startnote",
                   {"kind": "free_text", "origin": "patient_text", "text_tokenised": START_NOTE[lang]},
                   reporter=a["token"], consent_id=web))
    out += _dispenses(a, start, n)
    if a["supporter"]:
        out += _supporter_events(a, start, n)
    out.append(_summary(a, start, n, missed_days))
    return out


def _dispenses(a: dict[str, Any], start: date, n: int) -> list[dict[str, Any]]:
    chem = _cid(a["token"], "chemist", "care_coordination")
    return [
        _ev(a, "Dispense", _at(start + timedelta(days=k), 11), f"demo:{a['code']}:dispense:{k}",
            {"kind": "refill", "days_supply": 28}, source="chemist", reporter_mode="record",
            channel=None, consent_id=chem, lag=timedelta(days=1))
        for k in range(0, n, 28)
        if start + timedelta(days=k + 1) <= today_ist()
    ]


def _supporter_events(a: dict[str, Any], start: date, n: int) -> list[dict[str, Any]]:
    sup = _cid(a["token"], "supporter", "supporter_sharing")
    out = []
    for k in range(9, n, 10):
        d = start + timedelta(days=k)
        out.append(_ev(a, "SupporterVisit", _at(d, 17), f"demo:{a['code']}:visit:{k}",
                       {"visit_date": d.isoformat(), "mode": "witnessed"}, source="supporter",
                       reporter_mode="witnessed", channel=None, reporter=a["supporter"]["token"],
                       consent_id=sup))
        out.append(_ev(a, "ContextNote", _at(d, 17, 30), f"demo:{a['code']}:supnote:{k}",
                       {"kind": "free_text", "origin": "supporter_text",
                        "text_tokenised": SUPPORTER_NOTE[a["supporter"]["lang"]]},
                       source="supporter", reporter_mode="witnessed", channel=None,
                       reporter=a["supporter"]["token"], consent_id=sup))
    return out


def _summary(a: dict[str, Any], start: date, n: int, missed_days: list[int]) -> dict[str, Any]:
    recent = [d for d in missed_days if d > n - 7]
    base, tag = ("red", "RED") if len(recent) >= 3 else ("amb", "WATCH") if recent else ("grn", "ON TRACK")
    payload = {
        "kind": "summary", "sex": a["sex"], "age": a["age"], "base": base, "tag": tag,
        "why": f"{len(recent)} missed in the last 7 days" if recent else "Doses on track",
        "missed": missed_days[-8:], "no_data": 0, "next_step": "No action needed" if not recent else "Review",
        "visit_this_week": False, "quiet": False, "next_visit": "", "consent": "Active", "changes": [],
    }
    return _ev(a, "ContextNote", _at(today_ist(), 6), f"demo:{a['code']}:summary", payload,
               source="system", reporter_mode="record", channel=None)


def build_bundle() -> dict[str, Any]:
    """The full deterministic data set as portable JSON-able data (no passwords)."""
    persons, patients, links, consents, events, users = [], [], [], [], [], []
    for a in ACCOUNTS:
        start = today_ist() - timedelta(days=a["days"])
        persons.append({"token": a["token"], "role": "patient", "clinic": CLINIC, "lang": a["lang"],
                        "name": None, "phone": f"9000009{a['token'][-3:]}"})
        patients.append({"code": a["code"], "token": a["token"], "clinic": CLINIC,
                         "treatment_start": start.isoformat(), "regimen": "Standard six-month course",
                         "phase": "intensive", "nikshay_id": f"NK-{a['code'][3:]}"})
        users.append({"username": a["user"], "token": a["token"]})
        events += patient_events(a)
        for src in CONSENT_SOURCES:
            for purpose in ("care_coordination",) + (("supporter_sharing",) if src == "supporter" else ()):
                consents.append({"token": a["token"], "source": src, "purpose": purpose, "state": "granted",
                                 "effective_at": _at(start, 8).isoformat(), "via": "console",
                                 "consent_id": _cid(a["token"], src, purpose)})
        if s := a["supporter"]:
            persons.append({"token": s["token"], "role": "supporter", "clinic": CLINIC, "lang": s["lang"],
                            "name": s["name"], "phone": f"9000009{s['token'][-2:]}0"})
            links.append({"patient": a["code"], "supporter": s["token"], "from_date": start.isoformat()})
            users.append({"username": s["user"], "token": s["token"]})
    return {"version": BUNDLE_VERSION, "day0": DAY0.isoformat(), "as_of": as_of_instant().isoformat(),
            "persons": persons, "patients": patients, "links": links, "consents": consents,
            "events": events, "users": users}


# ------------------------------------------------------------------------------------------ apply
def _ensure_org(conn: Any) -> UUIDMap:
    did, bid, cid = det_id("district", "anantapur"), det_id("block", "Block A"), det_id("clinic", CLINIC)
    conn.execute("INSERT INTO cm.districts (district_id, name) VALUES (%s,'Anantapur District') "
                 "ON CONFLICT DO NOTHING", (did,))
    conn.execute("INSERT INTO cm.blocks (block_id, district_id, name) VALUES (%s,%s,'Block A') "
                 "ON CONFLICT DO NOTHING", (bid, did))
    conn.execute("INSERT INTO cm.clinics (clinic_id, block_id, name, facility_code) "
                 "VALUES (%s,%s,'Anantapur Urban Clinic','AP-ANT-01') ON CONFLICT DO NOTHING", (cid, bid))
    conn.execute(
        "INSERT INTO cm.sim_clock (run_id, seed, sim_day, day0_date, max_computed_day, status) "
        "SELECT %s, 42, %s, %s, %s, 'ready' WHERE NOT EXISTS (SELECT 1 FROM cm.sim_clock WHERE active)",
        (det_id("simclock"), AS_OF_DAY, DAY0, AS_OF_DAY))
    return {CLINIC: cid}


UUIDMap = dict[str, Any]


def _apply_people(conn: Any, b: dict[str, Any], clinics: UUIDMap) -> None:
    for p in b["persons"]:
        pid = det_id("person", p["token"])
        conn.execute("INSERT INTO cm.persons (person_id, role, token, clinic_id) VALUES (%s,%s,%s,%s) "
                     "ON CONFLICT DO NOTHING", (pid, p["role"], p["token"], clinics[p["clinic"]]))
        name = p["name"].encode() if p["name"] else None
        conn.execute(
            "INSERT INTO cm.identity_vault (person_id, enc_name, enc_phone, enc_email, lang) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (pid, name, p["phone"].encode(), f"{p['token'].lower()}@example.test".encode(), p["lang"]))
    for pt in b["patients"]:
        conn.execute(
            "INSERT INTO cm.patients (patient_id, person_id, clinic_id, treatment_start, regimen, phase, nikshay_id)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (det_id("patient", pt["code"]), det_id("person", pt["token"]), clinics[pt["clinic"]],
             date.fromisoformat(pt["treatment_start"]), pt["regimen"], pt["phase"], pt["nikshay_id"]))
    for ln in b["links"]:
        conn.execute("INSERT INTO cm.support_assignments (patient_id, supporter_id, from_date) VALUES (%s,%s,%s) "
                     "ON CONFLICT DO NOTHING",
                     (det_id("patient", ln["patient"]), det_id("person", ln["supporter"]),
                      date.fromisoformat(ln["from_date"])))


def _apply_consents(conn: Any, b: dict[str, Any]) -> None:
    for c in b["consents"]:
        conn.execute(
            "INSERT INTO cm.consents (consent_id, person_id, source, purpose, state, effective_at, via) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (consent_id) DO NOTHING",
            (UUID(c["consent_id"]), det_id("person", c["token"]), c["source"], c["purpose"], c["state"],
             datetime.fromisoformat(c["effective_at"]), c["via"]))


def _apply_events(conn: Any, b: dict[str, Any]) -> int:
    new = [NewEvent(
        event_id=UUID(e["event_id"]), patient_id=det_id("patient", e["patient"]), type=e["type"],
        occurred_at=datetime.fromisoformat(e["occurred_at"]), recorded_at=datetime.fromisoformat(e["recorded_at"]),
        source=e["source"], reporter_mode=e["reporter_mode"], channel=e["channel"],
        reporter_id=det_id("person", e["reporter"]) if e.get("reporter") else None,
        consent_id=UUID(e["consent_id"]) if e.get("consent_id") else None, payload=e["payload"], idempotency_key=e["idempotency_key"],
    ) for e in b["events"]]
    return ev.bulk_append(new, conn=conn)


def _load_passwords(usernames: list[str]) -> dict[str, str]:
    """env DEMO_ACCOUNT_PASSWORDS, else the git-ignored credentials file, else generate into that file."""
    raw = os.environ.get("DEMO_ACCOUNT_PASSWORDS")
    pw: dict[str, str] = json.loads(raw) if raw else {}
    if not raw and CRED_FILE.exists():
        for line in CRED_FILE.read_text(encoding="utf-8").splitlines():
            if "\t" in line and not line.startswith("#"):
                u, p = line.split("\t", 1)
                pw[u.strip()] = p.strip()
    missing = [u for u in usernames if u not in pw]
    if missing and not raw:
        for u in missing:
            pw[u] = secrets.token_urlsafe(12)
        CRED_FILE.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# demo accounts (mock data). username<TAB>password. Git-ignored; do not share.", *(
            f"{u}\t{pw[u]}" for u in usernames)]
        CRED_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return pw


def _apply_users(conn: Any, b: dict[str, Any]) -> int:
    pw = _load_passwords([u["username"] for u in b["users"]])
    made = 0
    for u in b["users"]:
        pid = det_id("person", u["token"])
        if conn.execute("SELECT 1 FROM cm.auth_credentials WHERE person_id=%s OR username=%s",
                        (pid, u["username"])).fetchone():
            continue
        if u["username"] not in pw:
            raise DemoSeedError(f"no password for {u['username']} (set DEMO_ACCOUNT_PASSWORDS)")
        conn.execute("INSERT INTO cm.auth_credentials (person_id, username, password_hash) VALUES (%s,%s,%s)",
                     (pid, u["username"], hash_password(pw[u["username"]])))
        made += 1
    return made


def apply_bundle(conn: Any, b: dict[str, Any]) -> dict[str, int]:
    """Additive + idempotent: every insert is ON CONFLICT DO NOTHING or guarded."""
    if b.get("version") != BUNDLE_VERSION:
        raise DemoSeedError("unsupported bundle version")
    clinics = _ensure_org(conn)
    _apply_people(conn, b, clinics)
    _apply_consents(conn, b)
    events_new = _apply_events(conn, b)
    users_new = _apply_users(conn, b)
    return {"events_new": events_new, "users_new": users_new, "events_in_bundle": len(b["events"])}


def run_pipeline(codes: list[str], *, embed: bool) -> dict[str, Any]:
    """Memory nightly (features, beliefs, risk, conflicts) then the RAG index, per demo patient."""
    from cm.jobs.rag_index import index_patient
    from cm.memory.pipeline import run_patient as run_memory

    as_of = as_of_instant()
    clock.pin(as_of)
    out: dict[str, Any] = {}
    for code in codes:
        with connect_direct() as conn:
            pid = det_id("patient", code)
            row = conn.execute("SELECT 1 FROM cm.patients WHERE patient_id=%s", (pid,)).fetchone()
        if not row:
            continue
        run_memory(pid, as_of, day0=DAY0)
        s = index_patient(code, as_of, embed=embed)
        out[code] = {"chunks_total": s.chunks_total, "chunks_new": s.chunks_new, "embedded": s.embedded}
    return out


# ------------------------------------------------------------------------------------ export / import
def export_bundle(conn: Any) -> dict[str, Any]:
    """Read the demo accounts back out of the DB as the same portable bundle (no passwords)."""
    b = build_bundle()  # persons/patients/links/consents/users are fixed data; events are read from the DB
    pids = [str(det_id("patient", p["code"])) for p in b["patients"]]
    rows = conn.execute(
        "SELECT e.event_id, pt.token, e.type, e.occurred_at, e.recorded_at, e.source, e.reporter_mode, "
        "e.channel, e.consent_id, e.payload, e.idempotency_key, rp.token AS reporter "
        "FROM cm.events e JOIN cm.patients p USING (patient_id) JOIN cm.persons pt ON pt.person_id=p.person_id "
        "LEFT JOIN cm.persons rp ON rp.person_id=e.reporter_id "
        "WHERE e.patient_id = ANY(%s::uuid[]) ORDER BY e.occurred_at, e.idempotency_key", (pids,)).fetchall()
    code_of_tok = {p["token"]: p["code"] for p in b["patients"]}
    b["events"] = [{
        "event_id": str(r["event_id"]), "patient": code_of_tok[r["token"]], "type": r["type"],
        "occurred_at": r["occurred_at"].isoformat(), "recorded_at": r["recorded_at"].isoformat(),
        "idempotency_key": r["idempotency_key"], "payload": r["payload"], "source": r["source"],
        "reporter_mode": r["reporter_mode"], "channel": r["channel"], "reporter": r["reporter"],
        "consent_id": str(r["consent_id"]) if r["consent_id"] else None} for r in rows]
    return b


def _guard() -> None:
    load_dotenv()
    load_settings.cache_clear()
    if os.environ.get("CM_DATA_CLASS", "").lower() != "mock":
        raise DemoSeedError("refusing to run: CM_DATA_CLASS must be 'mock'")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Additive, idempotent demo accounts (3 / 30 / 60 days)")
    ap.add_argument("--export", metavar="FILE")
    ap.add_argument("--import", dest="imp", metavar="FILE")
    ap.add_argument("--no-embed", action="store_true", help="full-text only, no embedding calls")
    ap.add_argument("--skip-pipeline", action="store_true")
    a = ap.parse_args(argv)
    _guard()
    migrate.run_migrations()
    try:
        if a.export:
            with connect_direct() as conn:
                bundle = export_bundle(conn)
            Path(a.export).parent.mkdir(parents=True, exist_ok=True)
            Path(a.export).write_text(json.dumps(bundle, indent=1, sort_keys=True), encoding="utf-8")
            print(f"exported {len(bundle['events'])} events, {len(bundle['patients'])} patients to {a.export}")
            return 0
        bundle = json.loads(Path(a.imp).read_text(encoding="utf-8")) if a.imp else build_bundle()
        with connect_direct() as conn:
            res = apply_bundle(conn, bundle)
            conn.commit()
        if not a.skip_pipeline:
            res["pipeline"] = run_pipeline([p["code"] for p in bundle["patients"]], embed=not a.no_embed)
        print(json.dumps(res, default=str))
        if CRED_FILE.exists():
            print(f"credentials file: {CRED_FILE}")
        return 0
    finally:
        close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
