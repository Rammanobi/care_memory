"""Telegram photo and document intake. Fakes only: no Telegram API, no database, no real intake."""

from __future__ import annotations

import logging
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from cm.channels import sim_updates as sim
from cm.channels import tg_upload
from cm.channels.tg_http import HttpTelegramClient, TgFileError, TgFileTooLarge
from tests.unit.channels.test_telegram_lane import CHAT, World

FAKE_TOKEN = "000:FAKE-UPLOAD-TOKEN"
MB = 1024 * 1024


class FakeMessages:
    """MessagePort: stores free text once per update id; one ack per person per window."""

    def __init__(self) -> None:
        self.saved: list[tuple[int, str, str]] = []
        self.acks: dict[UUID, datetime] = {}

    def save(self, b, update_id, text, category, at, *, chat_id=None, message_id=None):  # noqa: ANN001
        if any(u == update_id for u, _, _ in self.saved):
            return False, None
        self.saved.append((update_id, text, category))
        return True, uuid4()

    def claim_ack(self, person_id, urgent, at, window_s):  # noqa: ANN001
        key = person_id if not urgent else UUID(int=person_id.int ^ 1)
        last = self.acks.get(key)
        if last is not None and (at - last).total_seconds() < window_s:
            return False
        self.acks[key] = at
        return True

    def first_name(self, person_id):  # noqa: ANN001
        return "Asha"


class Intake:
    """Stands in for cm.uploads.intake.accept_upload: scripted outcome, records every call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.reason: str | None = None
        self.duplicate_origins: set[str] = set()

    def __call__(self, **kw: Any) -> SimpleNamespace:
        self.calls.append(kw)
        origin = kw["origin"].get("telegram_file_unique_id")
        if origin in self.duplicate_origins:
            return SimpleNamespace(document_id="doc-1", status="received", duplicate=True, reason="duplicate")
        if self.reason:
            return SimpleNamespace(document_id=None, status="rejected", duplicate=False, reason=self.reason)
        self.duplicate_origins.add(origin)
        return SimpleNamespace(document_id=f"doc-{len(self.calls)}", status="received", duplicate=False, reason=None)


class Files:
    def __init__(self, data: bytes = b"%PDF-1.4 fake") -> None:
        self.data, self.calls, self.exc = data, [], None

    def __call__(self, file_id: str, max_bytes: int) -> bytes:
        self.calls.append((file_id, max_bytes))
        if self.exc:
            raise self.exc
        return self.data


class UploadWorld(World):
    def __init__(self, monkeypatch, **kw) -> None:  # noqa: ANN001
        super().__init__(**kw)
        self.intake, self.files = Intake(), Files()
        self.msgs = FakeMessages()
        self.deps.messages = self.msgs
        self.deps.files = self.files
        self.deps.patient_token = lambda pid: "P-0142" if pid == self.person else None
        monkeypatch.setattr(tg_upload, "_accept_upload", self.intake)
        self.origins: set[str] = set()
        self.recent = 0
        self.order: list[str] = []
        monkeypatch.setattr(tg_upload, "_find_by_origin",
                            lambda token, key: ({"document_id": "x"} if key in self.origins else None))
        monkeypatch.setattr(tg_upload, "_count_recent", lambda token: self.recent)
        self.deps.inline_files = True  # poller path; the webhook path is tested separately below


@pytest.fixture
def w(monkeypatch):
    return UploadWorld(monkeypatch)


def photo(uid: int, chat: int = CHAT, caption: str | None = None, big: int = 90_000) -> dict:
    upd = sim.message(uid, chat, "")
    m = upd["message"]
    m.pop("text")
    m["photo"] = [
        {"file_id": "small-id", "file_unique_id": "u-small", "file_size": 1_000, "width": 90, "height": 90},
        {"file_id": "big-id", "file_unique_id": "u-big", "file_size": big, "width": 1280, "height": 960},
        {"file_id": "mid-id", "file_unique_id": "u-mid", "file_size": 20_000, "width": 320, "height": 240},
    ]
    if caption:
        m["caption"] = caption
    return upd


def document(uid: int, chat: int = CHAT, name="report.pdf", mime="application/pdf", size=5_000, unique="u-doc",
             caption: str | None = None) -> dict:
    upd = sim.message(uid, chat, "")
    m = upd["message"]
    m.pop("text")
    m["document"] = {"file_id": f"doc-{unique}", "file_unique_id": unique, "file_name": name,
                     "mime_type": mime, "file_size": size}
    if caption:
        m["caption"] = caption
    return upd


def reply_text(body: dict) -> str:
    return body.get("text", "")


# ---- accepted files ----


def test_photo_uses_largest_size_and_acks(w):
    status, body = w.send(photo(10))
    assert status == 200
    assert w.files.calls == [("big-id", 10 * MB)]
    call = w.intake.calls[0]
    assert call["source"] == "telegram" and call["patient_token"] == "P-0142"
    assert call["mime"] == "image/jpeg" and call["filename"] == "photo_u-big.jpg"
    assert call["uploader_person_id"] == w.person
    assert call["origin"] == {"telegram_file_unique_id": "u-big", "telegram_chat_id": CHAT, "telegram_message_id": 10}
    assert body["method"] == "sendMessage" and "received your document" in body["text"] and "Asha" in body["text"]
    assert w.tasks.calls == [("agent-runs", "docx-doc-1", {"kind": "document_extract", "document_id": "doc-1"})]


def test_pdf_document_stored_with_name_and_mime(w):
    _, body = w.send(document(11))
    call = w.intake.calls[0]
    assert call["filename"] == "report.pdf" and call["mime"] == "application/pdf" and call["data"] == w.files.data
    assert call["origin"]["telegram_file_unique_id"] == "u-doc"
    assert "received your document" in body["text"]


def test_path_in_file_name_is_stripped(w):
    w.send(document(12, name="../../etc/passwd.pdf"))
    assert w.intake.calls[0]["filename"] == "passwd.pdf"


def test_missing_mime_guessed_from_name(w):
    upd = document(13, name="notes.txt")
    del upd["message"]["document"]["mime_type"]
    w.send(upd)
    assert w.intake.calls[0]["mime"] == "text/plain"


def test_telugu_ack_for_telugu_patient(w):
    w.binding.lang = "te"
    _, body = w.send(document(14))
    assert "మీ పత్రం మాకు అందింది" in body["text"]


# ---- refusals ----


def test_oversize_declared_refused_before_download(w):
    _, body = w.send(document(20, size=10 * MB + 1))
    assert w.files.calls == [] and w.intake.calls == [] and w.tasks.calls == []
    assert "could not accept that file" in body["text"] and "10 MB" in body["text"]


def test_exactly_ten_mb_declared_is_allowed(w):
    w.send(document(21, size=10 * MB))
    assert len(w.files.calls) == 1


def test_oversize_found_while_streaming_refused(w):
    w.files.exc = TgFileTooLarge("file larger than the limit")
    _, body = w.send(document(22, size=1000))  # the declared size lied
    assert w.intake.calls == [] and "could not accept that file" in body["text"]


def test_wrong_type_refused_by_intake(w):
    w.intake.reason = "bad_type"
    _, body = w.send(document(23, name="virus.exe", mime="application/x-msdownload"))
    assert "could not accept that file" in body["text"] and w.tasks.calls == []


@pytest.mark.parametrize("reason", ["too_large", "storage_error", "unknown_patient", "internal_error"])
def test_other_intake_refusals_use_the_rejected_template(w, reason):
    w.intake.reason = reason
    _, body = w.send(document(24))
    assert "could not accept that file" in body["text"] and w.tasks.calls == []


def test_download_failure_replies_rejected_and_stores_nothing(w):
    w.files.exc = TgFileError("telegram 503", error_class="retryable")
    _, body = w.send(document(25))
    assert w.intake.calls == [] and "could not accept that file" in body["text"]
    assert any(a[0] == "tg_upload_fetch_failed" for a in w.audit.rows)


def test_rate_limited_by_intake_is_silent(w):
    w.intake.reason = "rate_limited"
    _, body = w.send(document(26))
    assert body == {"ok": True} and w.tasks.calls == []


def test_intake_no_consent_gets_existing_stopped_text(w):
    w.intake.reason = "no_consent"
    _, body = w.send(document(27))
    assert "turned off" in body["text"] and w.tasks.calls == []


def test_unbound_chat_stores_nothing(w):
    _, body = w.send(document(30, chat=999))
    assert "invitation" in body["text"] and w.files.calls == [] and w.intake.calls == []


def test_after_stop_nothing_is_fetched_or_stored(w):
    w.send(sim.stop(1, CHAT))
    for upd in (document(31), photo(32)):
        _, body = w.send(upd)
        assert "turned off" in body["text"]
    assert w.files.calls == [] and w.intake.calls == [] and w.tasks.calls == []


def test_supporter_files_are_ignored(monkeypatch):
    w2 = UploadWorld(monkeypatch, role="supporter")
    w2.send(document(33))
    assert w2.files.calls == [] and w2.intake.calls == []


def test_group_chat_files_ignored(w):
    upd = document(34)
    upd["message"]["chat"]["type"] = "group"
    assert w.send(upd) == (200, {"ok": True}) and w.files.calls == []


def test_upload_not_wired_is_a_quiet_noop(monkeypatch):
    w2 = UploadWorld(monkeypatch)
    w2.deps.files = None
    assert w2.send(document(35)) == (200, {"ok": True}) and w2.intake.calls == []


def test_intake_exception_never_escapes(w, monkeypatch):
    def boom(**kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(tg_upload, "_accept_upload", boom)
    status, body = w.send(document(36))
    assert status == 200 and "could not accept that file" in body["text"]
    assert any(a[0] == "tg_upload_error" for a in w.audit.rows)


# ---- idempotency and rate limit ----


def test_duplicate_update_stores_once_acks_once(w):
    upd = document(40)
    _, first = w.send(upd)
    _, second = w.send(upd)
    assert "received your document" in first["text"] and second == {"ok": True}
    assert len(w.tasks.calls) == 1


def test_ack_rate_limited_to_one_per_window(w):
    _, a = w.send(document(41, unique="a"))
    _, b = w.send(document(42, unique="b"))
    assert "received your document" in a["text"] and b == {"ok": True}
    assert len(w.tasks.calls) == 2  # both stored, only the first answered
    w.clock.t = w.clock.t.replace(hour=w.clock.t.hour + 1)
    _, c = w.send(document(43, unique="c"))
    assert "received your document" in c["text"]


# ---- captions ----


def test_caption_goes_through_free_text_once_with_one_reply(w):
    _, body = w.send(photo(50, caption="This is my new lab report"))
    assert w.msgs.saved == [(50, "This is my new lab report", "normal")]
    assert body["method"] == "sendMessage"  # exactly one reply dict
    assert len(w.intake.calls) == 1 and len(w.tasks.calls) == 2  # tg-50 free text + docx-doc-1


def test_caption_not_routed_twice_on_repeat(w):
    upd = photo(51, caption="question about my tablets")
    w.send(upd)
    w.send(upd)
    assert len(w.msgs.saved) == 1


def test_danger_caption_raises_red_and_urgent_ack_wins(w):
    _, body = w.send(photo(52, caption="I am vomiting blood"))
    assert len(w.fast.red) == 1
    assert "call 108" in body["text"] and len(body["text"]) > 0


def test_rejected_file_beats_a_normal_caption_ack(w):
    w.intake.reason = "bad_type"
    _, body = w.send(document(53, caption="please look at this"))
    assert "could not accept that file" in body["text"]
    assert len(w.msgs.saved) == 1  # the question itself is still kept


def test_no_caption_no_free_text(w):
    w.send(photo(54))
    assert w.msgs.saved == []


# ---- the bot token never leaks (real client over a mock transport) ----


class Net:
    def __init__(self, file_bytes=b"%PDF-1.4 body", get_file_status=200, file_status=200) -> None:
        self.urls: list[str] = []
        self.file_bytes, self.gf, self.fs = file_bytes, get_file_status, file_status

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.urls.append(str(req.url))
        if req.url.path.endswith("/getFile"):
            if self.gf != 200:
                return httpx.Response(self.gf, json={"ok": False, "error_code": self.gf, "description": "x"})
            return httpx.Response(200, json={"ok": True, "result": {
                "file_id": "x", "file_size": len(self.file_bytes), "file_path": "documents/file_1.pdf"}})
        return httpx.Response(self.fs, content=self.file_bytes if self.fs == 200 else b"nope")


def test_token_never_in_logs_audit_payloads_or_replies(monkeypatch, caplog):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    caplog.set_level(logging.DEBUG)
    net = Net()
    w = UploadWorld(monkeypatch)
    w.deps.files = HttpTelegramClient(transport=httpx.MockTransport(net), sleep=lambda s: None).fetch_file
    _, body = w.send(document(60))
    assert any(FAKE_TOKEN in u for u in net.urls)  # the client did use it on the wire
    assert w.intake.calls[0]["data"] == net.file_bytes
    blob = repr((w.audit.rows, w.intake.calls, w.tasks.calls, body, w.events.rows)) + caplog.text
    assert FAKE_TOKEN not in blob and "FAKE-UPLOAD" not in blob


def test_token_never_leaks_when_download_fails(monkeypatch, caplog):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    caplog.set_level(logging.DEBUG)
    w = UploadWorld(monkeypatch)
    net = Net(file_status=502)
    w.deps.files = HttpTelegramClient(transport=httpx.MockTransport(net), sleep=lambda s: None).fetch_file
    _, body = w.send(document(61))
    assert len(net.urls) == 1 + 3  # getFile once, the file download retried to the cap
    blob = repr((w.audit.rows, body)) + caplog.text
    assert FAKE_TOKEN not in blob and w.intake.calls == []


# ---- the client: getFile, download, retry, limits ----


def client(monkeypatch, net, sleeps=None) -> HttpTelegramClient:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    return HttpTelegramClient(transport=httpx.MockTransport(net), sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_fetch_file_happy_path(monkeypatch):
    net = Net()
    assert client(monkeypatch, net).fetch_file("abc") == net.file_bytes
    assert net.urls[1].endswith("/file/bot" + FAKE_TOKEN + "/documents/file_1.pdf")


def test_download_retries_5xx_then_succeeds(monkeypatch):
    seq = [502, 503, 200]
    net = Net()
    base = net.__call__

    def handler(req):
        if req.url.path.endswith("/getFile"):
            return base(req)
        code = seq.pop(0)
        return httpx.Response(code, content=net.file_bytes if code == 200 else b"x")

    sleeps: list[float] = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    cl = HttpTelegramClient(transport=httpx.MockTransport(handler), sleep=sleeps.append)
    assert cl.fetch_file("abc") == net.file_bytes and len(sleeps) == 2


def test_get_file_429_honours_retry_after(monkeypatch):
    seq = [httpx.Response(429, json={"ok": False, "error_code": 429, "parameters": {"retry_after": 3}}),
           httpx.Response(200, json={"ok": True, "result": {"file_path": "p/x.jpg", "file_size": 3}}),
           httpx.Response(200, content=b"abc")]
    sleeps: list[float] = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    cl = HttpTelegramClient(transport=httpx.MockTransport(lambda r: seq.pop(0)), sleep=sleeps.append)
    assert cl.fetch_file("abc") == b"abc" and sleeps == [3.0]


@pytest.mark.parametrize("status", [400, 404])
def test_get_file_client_errors_are_not_retried(monkeypatch, status):
    net = Net(get_file_status=status)
    with pytest.raises(TgFileError) as e:
        client(monkeypatch, net).fetch_file("abc")
    assert len(net.urls) == 1 and FAKE_TOKEN not in str(e.value) and e.value.__cause__ is None


def test_auth_error_not_retried(monkeypatch):
    net = Net(get_file_status=401)
    with pytest.raises(TgFileError):
        client(monkeypatch, net).fetch_file("abc")
    assert len(net.urls) == 1


def test_declared_size_over_limit_skips_download(monkeypatch):
    net = Net(file_bytes=b"x" * 50)
    with pytest.raises(TgFileTooLarge):
        client(monkeypatch, net).fetch_file("abc", max_bytes=10)
    assert len(net.urls) == 1


def test_stream_cut_off_past_limit_when_size_lies(monkeypatch):
    def handler(req):
        if req.url.path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "p/x.pdf", "file_size": 1}})
        return httpx.Response(200, content=b"x" * 500)

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    with pytest.raises(TgFileTooLarge):
        HttpTelegramClient(transport=httpx.MockTransport(handler)).fetch_file("abc", max_bytes=100)


def test_network_error_wrapped_without_token(monkeypatch):
    def boom(req):
        raise httpx.ConnectError("refused " + str(req.url))

    with pytest.raises(TgFileError) as e:
        client(monkeypatch, boom).fetch_file("abc")
    assert FAKE_TOKEN not in str(e.value) and FAKE_TOKEN not in repr(e.value.__cause__)


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "a/../../b", ""])
def test_unsafe_file_path_refused(monkeypatch, path):
    net = Net()
    with pytest.raises(TgFileError):
        client(monkeypatch, net).download_file(path)
    assert net.urls == []


def test_missing_token_is_a_file_error(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    cl = HttpTelegramClient(transport=httpx.MockTransport(Net()))
    with pytest.raises(TgFileError):
        cl.fetch_file("abc")


# ---- webhook path: ack + tgfile task, no download in the request ----


def test_webhook_path_enqueues_tgfile_and_does_not_download(w):
    w.deps.inline_files = False
    _, body = w.send(document(60, unique="uq/1"))
    assert w.files.calls == [] and w.intake.calls == []
    name, payload = w.tasks.calls[0][1], w.tasks.calls[0][2]
    assert w.tasks.calls[0][0] == "agent-runs" and name == "tgfile-uq_1"
    assert payload["kind"] == "tgfile" and payload["file_id"] == "doc-uq/1" and payload["person_id"] == str(w.person)
    assert "token" not in repr(payload).lower()
    assert body["method"] == "sendMessage"


def test_webhook_path_checks_run_before_enqueue(w):
    w.deps.inline_files = False
    w.origins.add("telegram:u-doc")
    assert w.send(document(61)) == (200, {"ok": True}) and w.tasks.calls == []
    w.origins.clear()
    w.recent = 5
    assert w.send(document(62, unique="u2")) == (200, {"ok": True}) and w.tasks.calls == []


def test_checks_run_before_download_inline(w):
    w.origins.add("telegram:u-doc")
    w.send(document(63))
    w.origins.clear()
    w.recent = 5
    w.send(document(64, unique="u3"))
    w.deps.patient_token = lambda pid: None
    _, body = w.send(document(65, unique="u4"))
    assert w.files.calls == [] and w.intake.calls == [] and "could not accept" in body["text"]


def test_tgfile_task_fetches_and_intakes(monkeypatch):
    from cm.store import upload_channels_repo as repo

    pid = uuid4()
    monkeypatch.setattr(repo, "person_token", lambda p: "P-0142")
    monkeypatch.setattr(tg_upload, "_find_by_origin", lambda t, k: None)
    intake = Intake()
    monkeypatch.setattr(tg_upload, "_accept_upload", intake)
    got, enq = [], []
    payload = {"kind": "tgfile", "person_id": str(pid), "chat_id": str(CHAT), "message_id": 7, "file_id": "f1",
               "unique_id": "u9", "name": "a.pdf", "mime": "application/pdf", "size": 10}
    out = tg_upload.run_tgfile_task(payload, fetch=lambda fid, mb: got.append((fid, mb)) or b"%PDF-1.4 x",
                                    audit=SimpleNamespace(audit=lambda *a, **k: None),
                                    enqueue=lambda q, n, p: enq.append((q, n, p)))
    assert out == "accepted" and got == [("f1", tg_upload.max_bytes())]
    assert intake.calls[0]["origin"]["telegram_file_unique_id"] == "u9" and intake.calls[0]["uploader_person_id"] == pid
    assert enq == [("agent-runs", "docx-doc-1", {"kind": "document_extract", "document_id": "doc-1"})]


def test_tgfile_task_retryable_reraises_permanent_acks(monkeypatch):
    from cm.store import upload_channels_repo as repo

    monkeypatch.setattr(repo, "person_token", lambda p: "P-0142")
    monkeypatch.setattr(tg_upload, "_find_by_origin", lambda t, k: None)
    payload = {"person_id": str(uuid4()), "file_id": "f", "unique_id": "u", "chat_id": "1"}
    aud = SimpleNamespace(audit=lambda *a, **k: None)

    def boom(exc):
        def f(fid, mb):
            raise exc
        return f

    with pytest.raises(TgFileError):
        tg_upload.run_tgfile_task(payload, fetch=boom(TgFileError("503", error_class="retryable")), audit=aud)
    assert tg_upload.run_tgfile_task(payload, fetch=boom(TgFileError("bad")), audit=aud) == "storage_error"
    assert tg_upload.run_tgfile_task(payload, fetch=boom(TgFileTooLarge("big")), audit=aud) == "too_large"


def test_tasks_dispatch_routes_tgfile(monkeypatch):
    from cm.api.routers import tasks

    seen = []
    monkeypatch.setattr(tg_upload, "run_tgfile_task", lambda p: seen.append(p))
    tasks.dispatch("agent-runs", "tgfile-u", {"kind": "tgfile", "x": 1})
    assert seen == [{"kind": "tgfile", "x": 1}] and tasks._TASK_TYPE["tgfile"]
