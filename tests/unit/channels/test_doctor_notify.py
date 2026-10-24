"""Doctor email notification: offline, fakes only (no Google, no network, no real email)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cm.channels import doctor_notify as dn
from cm.channels.fakes_gmail import FakeGmailClient
from cm.channels.ports_gmail import has_banned_term

T0 = datetime(2026, 10, 25, 6, 30, tzinfo=UTC)
GMAIL = {"GMAIL_OAUTH_CLIENT_JSON": "x.json", "GMAIL_REFRESH_TOKEN": "r", "GMAIL_MAILBOX": "clinic@example.test"}
BASE = {"DOCTOR_NOTIFY_EMAIL": "owner@example.test"}


def call(aid="a1", *, code="PT-0903", prio="urgent", text="My chest hurts", now=T0, **kw):
    return dn.notify_doctor_new_question(
        aid, patient_code=code, category="symptom", priority=prio, question_excerpt=text, now=now, **kw
    )


def test_render_subject_priorities_and_body():
    s, t, h = dn.render_question_email("a1", patient_code="PT-0903", category="symptom", priority="urgent",
                                       question_excerpt="Cough for a week", now=T0)
    assert s == "[CareMemory] Urgent patient question PT-0903 (symptom)"
    assert "[CareMemory] High patient question" in dn.render_question_email(
        "a", patient_code="PT-1", category="c", priority="High", question_excerpt="x", now=T0)[0]
    assert dn.render_question_email("a", patient_code="PT-1", category="c", priority="normal",
                                    question_excerpt="x", now=T0)[0].startswith("[CareMemory] New patient question")
    assert "Patient: PT-0903" in t and "Cough for a week" in t and dn.REMINDER in t
    assert "http://localhost:5173/requests?approval=a1" in t and "<a href=" in h
    assert "12:00 IST" in t


def test_masking_and_length():
    raw = "call me 98765 43210 or a@b.com, aadhaar 1234 5678 9012, mrn 12345678 " + "z" * 400
    _, t, h = dn.render_question_email("a1", patient_code="PT-1", category="c", priority="new",
                                       question_excerpt=raw, now=T0)
    for leak in ("98765", "a@b.com", "1234 5678", "12345678"):
        assert leak not in t and leak not in h
    excerpt = t.split("Question (masked excerpt):\n")[1].split("\n\n")[0]
    assert len(excerpt) <= dn.EXCERPT_MAX


def test_no_header_injection_and_html_escape():
    s, t, h = dn.render_question_email("a1", patient_code="PT-1\r\nBcc: x@y.z", category="s\nBcc: q",
                                       priority="urgent", question_excerpt="<script>alert(1)</script>", now=T0)
    assert "\n" not in s and "\r" not in s and "unknown" in s
    assert "<script>" not in h and "&lt;script&gt;" in h


def test_static_text_has_no_banned_terms():
    s, t, h = dn.render_question_email("a1", patient_code="PT-1", category="symptom", priority="urgent",
                                       question_excerpt="hello", now=T0)
    assert not has_banned_term(s + t + h)


def test_dry_run_writes_file_and_never_contacts_gmail(tmp_path):
    api = FakeGmailClient()
    r = call(env={**BASE, "DOCTOR_NOTIFY_MODE": "dry-run"}, api=api, store=dn.MemoryNotifyStore(), outbox_dir=tmp_path)
    assert r["status"] == "dry_run" and r["path"].endswith(".eml")
    body = Path(r["path"]).read_text(encoding="utf-8")
    assert "Urgent patient question PT-0903" in body and api.sent == []


def test_default_mode_is_dry_run(tmp_path):
    assert call(env=BASE, store=dn.MemoryNotifyStore(), outbox_dir=tmp_path)["status"] == "dry_run"


def test_off_mode_skips(tmp_path):
    r = call(env={**BASE, "DOCTOR_NOTIFY_MODE": "off"}, store=dn.MemoryNotifyStore(), outbox_dir=tmp_path)
    assert r == {"status": "skipped", "reason": "off"} and list(tmp_path.iterdir()) == []


def test_duplicate_approval_skipped(tmp_path):
    st = dn.MemoryNotifyStore()
    assert call("a1", env=BASE, store=st, outbox_dir=tmp_path)["status"] == "dry_run"
    assert call("a1", env=BASE, store=st, outbox_dir=tmp_path) == {"status": "skipped", "reason": "duplicate"}


def test_throttle_normal_10_min(tmp_path):
    kw = dict(env=BASE, store=dn.MemoryNotifyStore(), outbox_dir=tmp_path, prio="normal")
    assert call("a1", now=T0, **kw)["status"] == "dry_run"
    assert call("a2", now=T0 + timedelta(minutes=5), **kw) == {"status": "skipped", "reason": "throttled"}
    assert call("a3", code="PT-0001", now=T0 + timedelta(minutes=5), **kw)["status"] == "dry_run"
    assert call("a4", now=T0 + timedelta(minutes=11), **kw)["status"] == "dry_run"


def test_urgent_always_sends_but_max_3_per_hour(tmp_path):
    kw = dict(env=BASE, store=dn.MemoryNotifyStore(), outbox_dir=tmp_path, prio="urgent")
    out = [call(f"u{i}", now=T0 + timedelta(seconds=i), **kw)["status"] for i in range(4)]
    assert out == ["dry_run"] * 3 + ["skipped"]
    assert call("u9", now=T0 + timedelta(minutes=61), **kw)["status"] == "dry_run"


def test_send_mode_uses_fake_gmail(tmp_path):
    api = FakeGmailClient()
    env = {**BASE, **GMAIL, "DOCTOR_NOTIFY_MODE": "send", "CONSOLE_BASE_URL": "https://console.example.test/"}
    r = call(env=env, api=api, store=dn.MemoryNotifyStore(), outbox_dir=tmp_path)
    assert r["status"] == "sent" and len(api.sent) == 1
    m = api.sent[0]
    assert m["to"] == "owner@example.test" and m["subject"].startswith("[CareMemory] Urgent")
    assert "https://console.example.test/requests?approval=a1" in m["body_text"]
    assert list(tmp_path.iterdir()) == []


def test_send_mode_without_gmail_config_skipped(tmp_path):
    api = FakeGmailClient()
    r = call(env={**BASE, "DOCTOR_NOTIFY_MODE": "send"}, api=api, store=dn.MemoryNotifyStore(), outbox_dir=tmp_path)
    assert r == {"status": "skipped", "reason": "gmail not configured"} and api.sent == []


def test_send_failure_returns_failed_and_releases_claim(tmp_path):
    api = FakeGmailClient()
    api.errors = [RuntimeError("boom")]
    st = dn.MemoryNotifyStore()
    env = {**BASE, **GMAIL, "DOCTOR_NOTIFY_MODE": "send"}
    assert call(env=env, api=api, store=st, outbox_dir=tmp_path) == {"status": "failed", "reason": "RuntimeError"}
    assert call(env=env, api=api, store=st, outbox_dir=tmp_path)["status"] == "sent"


@pytest.mark.parametrize("bad", [None, 5, "", "x" * 5000, "\x00\x01"])
def test_never_raises_on_bad_input(bad, tmp_path):
    r = dn.notify_doctor_new_question(bad, patient_code=bad, category=bad, priority=bad, question_excerpt=bad,
                                      now=T0, env=BASE, store=dn.MemoryNotifyStore(), outbox_dir=tmp_path)
    assert r["status"] in {"skipped", "dry_run", "failed"}


def test_never_raises_when_store_explodes(tmp_path):
    class Boom:
        def claim(self, *a):
            raise OSError("db")

        def release(self, *a):
            raise OSError("db")

    assert call(env=BASE, store=Boom(), outbox_dir=tmp_path) == {"status": "failed", "reason": "OSError"}


def test_cli_prints_and_exits_0_without_confirmation(capsys):
    api = FakeGmailClient()
    env = {**BASE, **GMAIL, "DOCTOR_NOTIFY_MODE": "send"}
    assert dn._cli(["--send-test", "--to-env"], env=env, api=api) == 0
    out = capsys.readouterr().out
    assert "NOT SENT" in out and "owner@example.test" not in out and api.sent == []


def test_cli_dry_run_mode_never_sends_even_with_flag():
    api = FakeGmailClient()
    env = {**BASE, **GMAIL, "DOCTOR_NOTIFY_MODE": "dry-run"}
    assert dn._cli(["--send-test", "--to-env", "--i-confirm-owner-approved"], env=env, api=api) == 0
    assert api.sent == []


def test_cli_sends_one_labelled_test_only_with_all_conditions():
    api = FakeGmailClient()
    env = {**BASE, **GMAIL, "DOCTOR_NOTIFY_MODE": "send"}
    assert dn._cli(["--send-test", "--to-env", "--i-confirm-owner-approved"], env=env, api=api) == 0
    assert len(api.sent) == 1 and "TEST" in api.sent[0]["subject"]


@pytest.mark.db
def test_pg_store_claim_throttle_duplicate(seeded_db):
    from cm.store import gmail_repo as g

    code = f"PT-T{int(datetime.now(UTC).timestamp())}"
    n = datetime.now(UTC)
    assert g.doctor_notify_claim("pg-a1-" + code, code, False, n) == "ok"
    assert g.doctor_notify_claim("pg-a1-" + code, code, False, n) == "duplicate"
    assert g.doctor_notify_claim("pg-a2-" + code, code, False, n) == "throttled"
    g.doctor_notify_release("pg-a1-" + code, n)
    assert g.doctor_notify_claim("pg-a1-" + code, code, False, n + timedelta(seconds=1)) == "ok"
