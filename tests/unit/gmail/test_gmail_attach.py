"""Doctor email attachments become patient uploads. Fakes only: FakeGmailClient, no Google, no database."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from cm.channels import gmail as g
from cm.channels import gmail_attach as ga
from cm.channels.fakes_gmail import FakeAudit, FakeGmailClient, FakeOutboxWriter, FakeState
from cm.channels.gmail_google import GoogleGmailApi
from cm.channels.ports_gmail import GmailAuthError, GmailQuotaError, GmailTransientError

BOX, DOC = "clinic@example.org", "doc@example.org"
AUTH = "mx; dmarc=pass; dkim=pass; spf=pass"
DOCTOR_ID = uuid4()
MB = 1024 * 1024


class Intake:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.reason: str | None = None
        self.seen: set[str] = set()

    def __call__(self, **kw: Any) -> SimpleNamespace:
        self.calls.append(kw)
        key = f"{kw['origin']['gmail_message_id']}:{kw['origin']['gmail_attachment_id']}"
        if key in self.seen:
            return SimpleNamespace(document_id="d", status="received", duplicate=True, reason="duplicate")
        if self.reason:
            return SimpleNamespace(document_id=None, status="rejected", duplicate=False, reason=self.reason)
        self.seen.add(key)
        return SimpleNamespace(document_id=f"doc-{len(self.seen)}", status="received", duplicate=False, reason=None)


class Env:
    def __init__(self, monkeypatch) -> None:  # noqa: ANN001
        self.api, self.audit, self.state = FakeGmailClient(), FakeAudit(), FakeState()
        self.intake, self.enq = Intake(), []
        self.outbox = FakeOutboxWriter()
        self.mp = monkeypatch
        monkeypatch.setattr(ga, "_accept_upload", self.intake)
        self.kw = dict(api=self.api, allowlist=[DOC], resolve_doctor=lambda e: DOCTOR_ID if e == DOC else None,
                       audit=self.audit, enqueue=lambda q, n, p: self.enq.append((q, n, p)), sleep=lambda s: None)

    def msg(self, *, mid="m1", sender=DOC, subject="Lab report for PT-0906", text="", auth=AUTH,
            atts=(("a1", "lab.pdf", "application/pdf", 1000, b"%PDF-1.4 x"),)) -> dict[str, Any]:
        out = []
        for aid, name, mime, size, data in atts:
            self.api.attachments[(mid, aid)] = data
            out.append({"filename": name, "mime": mime, "size": size, "attachment_id": aid})
        return {"id": mid, "thread_id": "t", "labels": ["INBOX"], "attachments": out, "text": text,
                "headers": {"from": sender, "subject": subject, "authentication-results": auth}}

    def run(self, m, **over):  # noqa: ANN001
        return ga.handle_attachments(m, **{**self.kw, **over})


@pytest.fixture
def env(monkeypatch):
    return Env(monkeypatch)


def reasons(env: Env, event: str) -> list[str]:
    return [f["reason"] for e, f in env.audit.events if e == event]


def test_allowlisted_sender_with_code_in_subject(env):
    res = env.run(env.msg())
    assert res.accepted == ["a1"] and res.refused is None and res.patient_token == "P-0906"
    call = env.intake.calls[0]
    assert call["source"] == "gmail" and call["patient_token"] == "P-0906" and call["data"] == b"%PDF-1.4 x"
    assert call["filename"] == "lab.pdf" and call["mime"] == "application/pdf"
    assert call["uploader_person_id"] == DOCTOR_ID
    assert call["origin"] == {"gmail_message_id": "m1", "gmail_attachment_id": "a1"}
    assert env.enq == [("agent-runs", "docx-doc-1", {"kind": "document_extract", "document_id": "doc-1"})]
    assert ("gmail_upload_accepted", {"message_id": "m1", "attachment_id": "a1"}) in env.audit.events


def test_code_in_body_when_subject_has_none(env):
    res = env.run(env.msg(subject="Scan", text="Hello,\nthis is for patient pt-0123 please file it."))
    assert res.accepted == ["a1"] and env.intake.calls[0]["patient_token"] == "P-0123"


def test_no_patient_code_stores_nothing(env):
    res = env.run(env.msg(subject="Some report", text="no code here, call 9000000001"))
    assert res.refused == "no_patient_code" and env.intake.calls == [] and env.api.calls == []
    assert reasons(env, "gmail_upload_refused") == ["no_patient_code"]


def test_two_different_codes_are_ambiguous(env):
    res = env.run(env.msg(subject="PT-0906 and PT-0907"))
    assert res.refused == "no_patient_code" and env.intake.calls == []


def test_same_code_twice_is_fine(env):
    assert env.run(env.msg(subject="PT-0906 re PT-0906")).accepted == ["a1"]


def test_non_allowlisted_sender_ignored_and_audited(env):
    res = env.run(env.msg(sender="stranger@evil.test"))
    assert res.refused == "sender_not_allowlisted" and env.intake.calls == [] and env.api.calls == []
    assert reasons(env, "gmail_upload_refused") == ["sender_not_allowlisted"]


def test_allowlisted_address_without_authentication_refused(env):
    res = env.run(env.msg(auth="mx; spf=fail; dkim=none"))
    assert res.refused == "sender_not_allowlisted" and env.intake.calls == []


def test_allowlist_is_case_insensitive_and_display_name_ok(env):
    res = env.run(env.msg(sender="Dr Rao <DOC@Example.org>"))
    assert res.accepted == ["a1"]


def test_empty_allowlist_refuses_everyone(env):
    assert env.run(env.msg(), allowlist=[]).refused == "sender_not_allowlisted"


def test_message_without_attachments_is_not_handled(env):
    res = env.run(env.msg(atts=()))
    assert res.handled is False and env.audit.events == []


def test_duplicate_message_is_idempotent(env):
    m = env.msg()
    env.run(m)
    res = env.run(m)
    assert res.duplicates == ["a1"] and res.accepted == []
    assert len(env.enq) == 1  # second pass did not enqueue extraction again


def test_duplicate_message_id_skipped_by_fetch_worker(env):
    m = env.msg(mid="m9")
    env.api.add_inbound(m)
    seen: list[dict] = []

    def on_msg(msg):
        seen.append(ga.dispatch(msg, **env.kw))

    g.fetch_worker(env.api.latest, api=env.api, state=env.state, mailbox=BOX, on_message=on_msg, sleep=lambda s: None)
    g.fetch_worker(env.api.latest, api=env.api, state=env.state, mailbox=BOX, on_message=on_msg, sleep=lambda s: None)
    assert len(seen) == 1 and len(env.intake.calls) == 1


def test_bad_type_rejected_by_intake(env):
    env.intake.reason = "bad_type"
    res = env.run(env.msg(atts=(("a1", "x.exe", "application/octet-stream", 10, b"MZ"),)))
    assert res.rejected == {"a1": "bad_type"} and env.enq == []
    assert reasons(env, "gmail_upload_rejected") == ["bad_type"]


def test_oversize_declared_not_fetched(env):
    res = env.run(env.msg(atts=(("a1", "big.pdf", "application/pdf", 10 * MB + 1, b"x"),)))
    assert res.rejected == {"a1": "too_large"} and env.intake.calls == [] and "fetch_attachment" not in env.api.calls


def test_oversize_actual_bytes_refused_even_if_declared_small(env):
    res = env.run(env.msg(atts=(("a1", "big.pdf", "application/pdf", 10, b"x" * 100),)), max_bytes=50)
    assert res.rejected == {"a1": "too_large"} and env.intake.calls == []


def test_intake_rate_limit_and_unknown_patient_recorded(env):
    env.intake.reason = "unknown_patient"
    assert env.run(env.msg()).rejected == {"a1": "unknown_patient"}


def test_several_attachments_each_handled_one_bad_does_not_stop_the_rest(env):
    atts = (("a1", "a.pdf", "application/pdf", 5, b"A"), ("a2", "b.pdf", "application/pdf", 5, b"B"))
    calls = {"n": 0}
    real = env.intake

    def flaky(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(**kw)

    env.mp.setattr(ga, "_accept_upload", flaky)
    res = env.run(env.msg(atts=atts))
    assert res.rejected == {"a1": "storage_error"} and res.accepted == ["a2"]


def test_nothing_is_sent_or_decided(env):
    env.run(env.msg())
    assert env.api.sent == [] and env.outbox.rows == {}
    assert not any("approve" in e or "decid" in e for e, _ in env.audit.events)


def test_audit_never_holds_file_names_or_bytes(env):
    env.run(env.msg(atts=(("a1", "secret-name.pdf", "application/pdf", 5, b"PRIVATEBYTES"),)))
    blob = repr(env.audit.events)
    assert "secret-name" not in blob and "PRIVATEBYTES" not in blob


def test_quota_error_retried_then_ok(env):
    env.api.errors = [GmailQuotaError(2.0)]
    sleeps: list[float] = []
    res = env.run(env.msg(), sleep=sleeps.append)
    assert res.accepted == ["a1"] and sleeps == [2.0]


def test_transient_exhaustion_and_auth_propagate_for_task_retry(env):
    m = env.msg()
    env.api.errors = [GmailTransientError()] * 6
    with pytest.raises(GmailTransientError):
        env.run(m)
    env.api.errors = [GmailAuthError("x")]
    with pytest.raises(GmailAuthError):
        env.run(m)
    assert env.intake.calls == []


def test_dispatch_routes_reply_mail_to_the_reply_handler(env):
    replies: list[str] = []
    plain = env.msg(atts=())
    plain["attachments"] = []
    out = ga.dispatch(plain, on_reply=lambda m: replies.append(m["id"]), **env.kw)
    assert replies == ["m1"] and out.handled is False
    ga.dispatch(env.msg(mid="m2"), on_reply=lambda m: replies.append("WRONG"), **env.kw)
    assert replies == ["m1"]


def test_reply_with_logo_attachment_still_applies_the_approval(env):
    replies: list[str] = []
    m = env.msg(sender=DOC, subject="Re: digest", atts=())
    m["headers"]["delivered-to"] = "clinic+r_abcdefgh12@example.org"
    m["attachments"] = []  # logo already dropped by the normaliser
    ga.dispatch(m, on_reply=lambda x: replies.append(x["id"]), **env.kw)
    assert replies == ["m1"]
    # even if a leftover attachment survives, the reply handler runs first and uploads run in addition
    m2 = env.msg(mid="m2", subject="Re: digest")
    m2["headers"]["in-reply-to"] = "<digest-abc-1@x>"
    out = ga.dispatch(m2, on_reply=lambda x: replies.append(x["id"]), **env.kw)
    assert replies == ["m1", "m2"] and out.refused == "no_patient_code"


def test_real_attachment_with_code_still_uploads_via_dispatch(env):
    replies: list[str] = []
    out = ga.dispatch(env.msg(), on_reply=lambda x: replies.append(x["id"]), **env.kw)
    assert replies == [] and out.accepted == ["a1"]


@pytest.mark.parametrize("subject", ["PT-906", "PT-09061", "PT-90"])
def test_code_needs_exactly_four_digits(env, subject):
    res = env.run(env.msg(subject=subject))
    assert res.refused == "no_patient_code" and env.intake.calls == []


def test_max_bytes_follows_upload_max_mb(env, monkeypatch):
    monkeypatch.setenv("UPLOAD_MAX_MB", "0.0001")
    res = env.run(env.msg(atts=(("a1", "x.pdf", "application/pdf", 5000, b"x"),)))
    assert res.rejected == {"a1": "too_large"}


def test_inline_signature_images_are_not_attachments():
    def part(name, mime, size, headers=()):
        return {"mimeType": mime, "filename": name, "headers": [{"name": k, "value": v} for k, v in headers],
                "body": {"attachmentId": name, "size": size}}

    raw = {"id": "r", "payload": {"headers": [], "mimeType": "multipart/mixed", "parts": [
        part("logo.png", "image/png", 4000),
        part("sig.jpg", "image/jpeg", 50_000, [("Content-ID", "<x>"), ("Content-Disposition", "inline")]),
        part("scan.jpg", "image/jpeg", 400_000, [("Content-Disposition", "attachment")]),
        part("lab.pdf", "application/pdf", 3000, [("Content-ID", "<y>")])]}}
    assert [a["filename"] for a in g.normalize_message(raw)["attachments"]] == ["scan.jpg", "lab.pdf"]


# ---- normalising real Gmail payloads, and the real API's attachments.get ----


def test_normalize_message_lists_attachments():
    raw = {"id": "r1", "threadId": "t", "labelIds": ["INBOX"], "payload": {
        "headers": [{"name": "From", "value": DOC}, {"name": "Subject", "value": "PT-0906"}],
        "mimeType": "multipart/mixed", "parts": [
            {"mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(b"hi").decode()}},
            {"mimeType": "application/pdf", "filename": "lab.pdf", "body": {"attachmentId": "ATT1", "size": 1234}},
            {"mimeType": "multipart/related", "parts": [
                {"mimeType": "image/png", "filename": "scan.png", "body": {"attachmentId": "ATT2", "size": 90000}}]},
            {"mimeType": "text/html", "filename": "", "body": {"data": ""}}]}}
    msg = g.normalize_message(raw)
    assert [(a["attachment_id"], a["filename"], a["mime"], a["size"]) for a in msg["attachments"]] == [
        ("ATT1", "lab.pdf", "application/pdf", 1234), ("ATT2", "scan.png", "image/png", 90000)]
    assert msg["text"] == "hi"


def test_google_api_fetch_attachment_decodes_base64url():
    data = bytes(range(256)) * 3

    class Req:
        def __init__(self, out): self.out = out
        def execute(self): return self.out

    class Atts:
        def __init__(self): self.args = None
        def get(self, **kw):
            self.args = kw
            return Req({"size": len(data), "data": base64.urlsafe_b64encode(data).decode().rstrip("=")})

    atts = Atts()
    svc = SimpleNamespace(users=lambda: SimpleNamespace(messages=lambda: SimpleNamespace(attachments=lambda: atts)))
    assert GoogleGmailApi(svc).fetch_attachment("m1", "ATT1") == data
    assert atts.args == {"userId": "me", "messageId": "m1", "id": "ATT1"}


def test_google_api_attachment_errors_are_mapped():
    class Boom:
        def execute(self):
            err = TimeoutError("t")
            raise err

    atts = SimpleNamespace(get=lambda **kw: Boom())
    svc = SimpleNamespace(users=lambda: SimpleNamespace(messages=lambda: SimpleNamespace(attachments=lambda: atts)))
    with pytest.raises(GmailTransientError):
        GoogleGmailApi(svc).fetch_attachment("m", "a")


def test_allowlist_from_env():
    assert ga.allowlist_from_env({"DOCTOR_EMAIL_ALLOWLIST": " A@x.org, b@x.org ,"}) == ("a@x.org", "b@x.org")
    assert ga.allowlist_from_env({}) == ()
