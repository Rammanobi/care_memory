"""Real-adapter tests: no network, no Google credentials. Injected services, HttpMock, local RSA keys."""

import base64
import json
import time
from datetime import UTC, datetime
from email import message_from_bytes, policy
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from cm.channels import adapters_gmail_pg as pg
from cm.channels import gmail_google as gg
from cm.channels.calendar import sync_calendar_events
from cm.channels.fakes_gmail import FakeCalendarClient, FakeDecide, FakeTokens
from cm.channels.gmail import token_hash
from cm.channels.gmail_oidc import PushAuthError, bearer_token, verify_push_jwt
from cm.channels.gmail_reply import handle_reply
from cm.channels.ports_gmail import (
    CalendarApi,
    CursorLostError,
    GmailApi,
    GmailAuthError,
    GmailQuotaError,
    GmailTransientError,
)
from cm.contracts.review import ReviewDecisionIn


class Resp(dict):
    def __init__(self, status, **hdr):
        super().__init__(**hdr)
        self.status = status


class HttpErr(Exception):
    def __init__(self, status, reason="", **hdr):
        self.resp = Resp(status, **hdr)
        self.content = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode()


class Req:
    def __init__(self, result=None, err=None):
        self.result, self.err = result, err

    def execute(self):
        if self.err:
            raise self.err
        return self.result


class Rec:
    """Chainable fake: svc.users().messages().send(**kw) records the call and returns a Req."""

    def __init__(self, script, path=()):
        self.script, self.path = script, path

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return Rec(self.script, self.path + (name,))

    def __call__(self, **kw):
        key = ".".join(self.path)
        if key in ("users", "users.messages", "users.history", "events") or not self.path:
            return Rec(self.script, self.path)
        self.script["calls"].append((key, kw))
        q = self.script.get(key, [])
        item = q.pop(0) if q else {}
        return Req(err=item) if isinstance(item, Exception) else Req(item)


def svc(**script):
    s = {"calls": [], **{k.replace("__", "."): v for k, v in script.items()}}
    return Rec(s), s


def test_import_and_construct_without_credentials(monkeypatch):
    for k in ("GMAIL_OAUTH_CLIENT_JSON", "GMAIL_REFRESH_TOKEN", "GMAIL_MAILBOX"):
        monkeypatch.delenv(k, raising=False)
    api = gg.GoogleGmailApi()
    cal = gg.GoogleCalendarApi()
    assert isinstance(api, GmailApi) and isinstance(cal, CalendarApi)
    with pytest.raises(gg.GmailConfigError) as e:
        gg.GmailConfig.from_env()
    assert "GMAIL_REFRESH_TOKEN" in str(e.value)
    with pytest.raises(gg.GmailConfigError):
        _ = api.service  # lazy: fails only on first use


def test_config_from_env_names_only():
    cfg = gg.GmailConfig.from_env({"GMAIL_OAUTH_CLIENT_JSON": "p", "GMAIL_REFRESH_TOKEN": "t",
                                   "GMAIL_MAILBOX": "m@x.org", "DOCTOR_EMAIL_ALLOWLIST": " A@x.org, b@x.org "})
    assert cfg.doctor_allowlist == ("a@x.org", "b@x.org")


def test_send_builds_mime_and_thread():
    s, rec = svc(users__messages__send=[{"id": "m1"}])
    api = gg.GoogleGmailApi(s)
    mid = api.send(to="d@x.org", subject="Hi", body_text="plain", body_html="<b>h</b>", reply_to="a+r_tok@x.org",
                   thread_id="th1", in_reply_to="<p@x>", message_id="<digest@caremem>")
    assert mid == "m1"
    key, kw = rec["calls"][0]
    assert kw["body"]["threadId"] == "th1"
    m = message_from_bytes(base64.urlsafe_b64decode(kw["body"]["raw"]), policy=policy.default)
    assert m["To"] == "d@x.org" and m["Reply-To"] == "a+r_tok@x.org" and m["In-Reply-To"] == "<p@x>"
    assert m.get_body(("plain",)).get_content().strip() == "plain"


def test_history_list_paginates_dedups_and_cursor_lost():
    s, rec = svc(users__history__list=[
        {"history": [{"messagesAdded": [{"message": {"id": "a"}}]}], "historyId": "120", "nextPageToken": "p2"},
        {"history": [{"messagesAdded": [{"message": {"id": "a"}}, {"message": {"id": "b"}}]}], "historyId": "130"},
    ])
    ids, latest = gg.GoogleGmailApi(s).history_list(100)
    assert ids == ["a", "b"] and latest == 130
    s2, _ = svc(users__history__list=[HttpErr(404)])
    with pytest.raises(CursorLostError):
        gg.GoogleGmailApi(s2).history_list(1)


def test_profile_get_watch_list_recent():
    s, _ = svc(users__getProfile=[{"historyId": "77"}], users__messages__get=[{"id": "x"}],
               users__watch=[{"historyId": "5", "expiration": "1700000000000"}],
               users__messages__list=[{"messages": [{"id": "1"}, {"id": "2"}]}])
    api = gg.GoogleGmailApi(s)
    assert api.profile_history_id() == 77
    assert api.get_message("x") == {"id": "x"}
    assert api.watch("projects/p/topics/t") == {"historyId": 5, "expiration": 1700000000000}
    assert api.list_recent("newer_than:2d") == ["1", "2"]


@pytest.mark.parametrize("err,typ", [
    (HttpErr(429, retry_after="7"), GmailQuotaError),
    (HttpErr(403, "rateLimitExceeded"), GmailQuotaError),
    (HttpErr(403, "forbidden"), GmailAuthError),
    (HttpErr(401), GmailAuthError),
    (HttpErr(503), GmailTransientError),
    (TimeoutError(), GmailTransientError),
])
def test_error_mapping(err, typ):
    s, _ = svc(users__getProfile=[err])
    with pytest.raises(typ):
        gg.GoogleGmailApi(s).profile_history_id()


def test_quota_retry_after_header():
    e = gg.map_google_error(HttpErr(429, **{"retry-after": "7"}))
    assert isinstance(e, GmailQuotaError) and e.retry_after == 7.0


def test_httpmock_real_discovery_client():
    """googleapiclient's own HttpMock: a real resource object, no network."""
    from googleapiclient.discovery import build_from_document
    from googleapiclient.http import HttpMock

    doc = {
        "kind": "discovery#restDescription", "name": "gmail", "version": "v1", "rootUrl": "http://localhost/",
        "servicePath": "gmail/v1/", "baseUrl": "http://localhost/gmail/v1/", "protocol": "rest",
        "resources": {"users": {"methods": {"getProfile": {
            "id": "gmail.users.getProfile", "path": "users/{userId}/profile", "httpMethod": "GET",
            "parameters": {"userId": {"type": "string", "required": True, "location": "path"}},
            "parameterOrder": ["userId"], "response": {"$ref": "Profile"}}}}},
        "schemas": {"Profile": {"id": "Profile", "type": "object", "properties": {"historyId": {"type": "string"}}}},
    }
    import os
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump({"historyId": "4242"}, fh)
        path = fh.name
    try:
        http = HttpMock(path, {"status": "200"})
        service = build_from_document(doc, http=http)
        assert gg.GoogleGmailApi(service).profile_history_id() == 4242
    finally:
        os.unlink(path)


def test_calendar_upsert_insert_then_update_on_conflict():
    s, rec = svc(events__insert=[HttpErr(409)], events__update=[{}])
    out = gg.GoogleCalendarApi(s).upsert_event("cal", "abc123", {"summary": "Visit"})
    assert out == "abc123"
    assert [c[0] for c in rec["calls"]] == ["events.insert", "events.update"]
    assert rec["calls"][0][1]["body"]["id"] == "abc123"


# ------------------------------------------------------------------ OIDC
@pytest.fixture(scope="module")
def keys():
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    def pem(key):
        return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())

    return {"priv": pem(k), "pub": k.public_key(), "other": pem(other)}


AUD, SA = "https://api.example.test/webhooks/gmail", "push@proj.iam.gserviceaccount.com"


def _tok(priv, **over):
    claims = {"iss": "https://accounts.google.com", "aud": AUD, "email": SA, "email_verified": True,
              "exp": int(time.time()) + 300, "iat": int(time.time()), **over}
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, priv, algorithm="RS256", headers={"kid": "k1"})


def _verify(token, keys, **kw):
    fetch = kw.pop("key_fetcher", lambda kid: keys["pub"] if kid == "k1" else None)
    return verify_push_jwt(token, audience=kw.pop("audience", AUD), expected_email=kw.pop("email", SA),
                           key_fetcher=fetch, **kw)


def test_oidc_valid(keys):
    assert _verify(_tok(keys["priv"]), keys)["email"] == SA


@pytest.mark.parametrize("over,reason", [
    ({"aud": "https://evil.test"}, "bad_audience"),
    ({"email": "other@proj.iam.gserviceaccount.com"}, "bad_email"),
    ({"email_verified": False}, "bad_email"),
    ({"iss": "https://evil.test"}, "bad_issuer"),
    ({"exp": int(time.time()) - 600}, "expired"),
])
def test_oidc_rejects_bad_claims(keys, over, reason):
    with pytest.raises(PushAuthError) as e:
        _verify(_tok(keys["priv"], **over), keys)
    assert e.value.reason == reason


def test_oidc_rejects_wrong_key_unknown_kid_garbage_and_unconfigured(keys):
    with pytest.raises(PushAuthError) as e:
        _verify(_tok(keys["other"]), keys)
    assert e.value.reason == "invalid_signature_or_claims"
    with pytest.raises(PushAuthError) as e:
        _verify(_tok(keys["priv"]), keys, key_fetcher=lambda kid: None)
    assert e.value.reason == "unknown_kid"
    with pytest.raises(PushAuthError):
        _verify("not.a.jwt", keys)
    with pytest.raises(PushAuthError) as e:
        _verify(_tok(keys["priv"]), keys, audience="")
    assert e.value.reason == "not_configured"
    hs = jwt.encode({"aud": AUD}, "secret" * 8, algorithm="HS256")
    with pytest.raises(PushAuthError) as e:
        _verify(hs, keys)
    assert e.value.reason == "bad_alg"


def test_bearer_token():
    assert bearer_token("Bearer abc") == "abc"
    with pytest.raises(PushAuthError):
        bearer_token(None)


# ------------------------------------------------------------------ DB adapters (repo layer mocked)
def test_pg_adapters_delegate_to_repo(monkeypatch):
    calls = []
    from cm.store import gmail_repo as r
    did = uuid4()
    monkeypatch.setattr(r, "consume_token", lambda th, d, now: (calls.append(("c", th, d)) or ("ok", uuid4())))
    monkeypatch.setattr(r, "advance_cursor", lambda mb, h: max(h, 5))
    monkeypatch.setattr(r, "is_processed", lambda m, now: m == "seen")
    st = pg.PgGmailState("m@x.org", now=lambda: datetime(2026, 10, 24, tzinfo=UTC))
    assert st.advance_cursor(3) == 5 and st.is_processed("seen") and not st.is_processed("new")
    status, _ = pg.PgTokenStore().consume("ab" * 32, str(did), datetime.now(UTC))
    assert status == "ok" and calls[0][2] == did


def test_pg_decide_routes_via_review_decide_and_maps_errors():
    from cm.review import decide as dec
    seen = {}
    aid, doc = uuid4(), uuid4()

    def fake(approval_id, body, *, via, actor_id):
        seen.update(via=via, actor=actor_id)
        raise dec.DecisionError("already_decided", 409, "x")

    out = pg.PgDecide(fake)(aid, ReviewDecisionIn(action="approve"), via="gmail", actor=str(doc))
    assert seen == {"via": "gmail", "actor": doc} and out.error_code == "already_decided"


def test_approve_1_reply_goes_only_through_decide():
    """'approve 1' -> handle_reply -> DecideFn (the single decision function), via=gmail."""
    doctor, email, tok = "doc-1", "doc@x.org", "T0KEN12345678"
    aid = uuid4()
    tokens, decide = FakeTokens(), FakeDecide()
    now = datetime(2026, 10, 24, 12, tzinfo=UTC)
    tokens.mint([(token_hash(tok, 1), aid)], doctor, datetime(2026, 10, 26, tzinfo=UTC))
    msg = {"id": "g1", "thread_id": "t", "text": "approve 1", "headers": {
        "from": email, "to": f"cm+r_{tok}@x.org", "in-reply-to": f"<digest-{doctor}-2026-10-24@caremem>",
        "authentication-results": "mx; dmarc=pass", "subject": "Re: review"}}
    out = handle_reply(msg, doctor_id=doctor, doctor_email=email, tokens=tokens, decide=decide, now=now)
    assert out.applied == [1]
    assert decide.calls[0][0] == aid and decide.calls[0][2] == "gmail" and decide.calls[0][1].action == "approve"


# ------------------------------------------------------------------ calendar sync skeleton
def _row():
    return {"approval_id": uuid4(), "patient_id": uuid4(), "payload": {"calendar_event": {
        "kind": "visit", "summary": "Clinic visit", "start": "2026-11-01T10:00:00+00:00",
        "end": "2026-11-01T10:30:00+00:00", "attendee_person_id": str(uuid4())}}}


def test_sync_calendar_events_idempotent_and_dry_run():
    rows = [_row(), {"approval_id": uuid4(), "patient_id": uuid4(), "payload": {}}]
    cal = FakeCalendarClient()
    r1 = sync_calendar_events(datetime.now(UTC), api=cal, calendar_id="c", list_approved=lambda a: rows)
    r2 = sync_calendar_events(datetime.now(UTC), api=cal, calendar_id="c", list_approved=lambda a: rows)
    assert r1["upserted"] == 1 and r1["skipped"] == 1 and len(cal.events) == 1 and r2["upserted"] == 1
    dry = sync_calendar_events(datetime.now(UTC), list_approved=lambda a: rows)
    assert dry["dry_run"] == 1 and dry["upserted"] == 0
