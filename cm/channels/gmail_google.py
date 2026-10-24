"""Lane M: real Gmail and Calendar adapters over googleapiclient.

Nothing here touches the network or credentials at import time. The Google libraries are imported and
the service is built lazily on first use, so importing this module works with no credentials and even
without the Google packages installed. Pass ``service`` (an injected object or HttpMock-backed resource)
for tests.

Env names (values never in code or logs): GMAIL_OAUTH_CLIENT_JSON (path to the OAuth client file),
GMAIL_REFRESH_TOKEN, GMAIL_MAILBOX, DOCTOR_EMAIL_ALLOWLIST, GOOGLE_CALENDAR_ID.
Retries are NOT done here: callers wrap calls in ``gmail.call_with_retry``; this layer only maps errors
to the typed errors in ports_gmail.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

from cm.channels.ports_gmail import (
    CursorLostError,
    GmailAuthError,
    GmailQuotaError,
    GmailTransientError,
)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.events",
]
TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105 (public endpoint, not a secret)
_RATE_REASONS = {"ratelimitexceeded", "userratelimitexceeded", "quotaexceeded", "dailylimitexceeded"}


class GmailConfigError(Exception):
    """A required env name is unset. The message names the variable, never a value."""


@dataclass(frozen=True)
class GmailConfig:
    client_json_path: str
    refresh_token: str
    mailbox: str
    doctor_allowlist: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> GmailConfig:
        e = os.environ if env is None else env
        missing = [k for k in ("GMAIL_OAUTH_CLIENT_JSON", "GMAIL_REFRESH_TOKEN", "GMAIL_MAILBOX") if not e.get(k)]
        if missing:
            raise GmailConfigError("missing env: " + ", ".join(missing))
        allow = tuple(a.strip().lower() for a in e.get("DOCTOR_EMAIL_ALLOWLIST", "").split(",") if a.strip())
        return cls(e["GMAIL_OAUTH_CLIENT_JSON"], e["GMAIL_REFRESH_TOKEN"], e["GMAIL_MAILBOX"], allow)


def build_credentials(cfg: GmailConfig) -> Any:
    """Refresh-token credentials from the OAuth client file (path from env). Lazy google-auth import."""
    from google.oauth2.credentials import Credentials

    with open(cfg.client_json_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    client = raw.get("installed") or raw.get("web") or {}
    return Credentials(
        token=None,
        refresh_token=cfg.refresh_token,
        token_uri=client.get("token_uri", TOKEN_URI),
        client_id=client.get("client_id"),
        client_secret=client.get("client_secret"),
        scopes=SCOPES,
    )


def build_service(api: str, version: str, cfg: GmailConfig | None = None) -> Any:
    from googleapiclient.discovery import build

    return build(api, version, credentials=build_credentials(cfg or GmailConfig.from_env()), cache_discovery=False)


def _status(exc: BaseException | None) -> int | None:
    s = getattr(getattr(exc, "resp", None), "status", None)
    return int(s) if s is not None else None


def _reason(exc: BaseException) -> str:
    try:
        data = json.loads(getattr(exc, "content", b"") or b"{}")
        errs = data.get("error", {}).get("errors") or [{}]
        return str(errs[0].get("reason", "")).lower()
    except (ValueError, AttributeError, TypeError):
        return ""


def map_google_error(exc: BaseException) -> BaseException:
    """HttpError / auth / network exception -> typed port error. Duck-typed, no google import needed.

    Returns the exception itself when it has no mapping (404 is left for the caller to interpret).
    """
    name = type(exc).__name__
    if name in ("RefreshError", "DefaultCredentialsError"):
        return GmailAuthError(name)
    status = _status(exc)
    if status is not None:
        reason = _reason(exc)
        if status == 429 or (status == 403 and reason in _RATE_REASONS):
            ra = None
            try:
                hdr = exc.resp.get("retry-after")  # type: ignore[attr-defined]
                ra = float(hdr) if hdr else None
            except (TypeError, ValueError, AttributeError):
                ra = None
            return GmailQuotaError(ra)
        if status in (401, 403):
            return GmailAuthError(f"http {status}")
        if status >= 500:
            return GmailTransientError(f"http {status}")
    if isinstance(exc, TimeoutError | ConnectionError) or name in ("ServerNotFoundError", "HttpLib2Error"):
        return GmailTransientError(name)
    return exc


class _Lazy:
    """Holds an injected service or a factory; builds on first use."""

    def __init__(self, service: Any = None, factory: Callable[[], Any] | None = None) -> None:
        self._service, self._factory = service, factory

    @property
    def service(self) -> Any:
        if self._service is None:
            if self._factory is None:
                raise GmailConfigError("no service or factory configured")
            self._service = self._factory()
        return self._service

    def _exec(self, request: Any, *, passthrough: tuple[int, ...] = ()) -> Any:
        """Execute; map errors. Statuses in ``passthrough`` re-raise the original HttpError unmapped."""
        try:
            return request.execute()
        except Exception as exc:  # noqa: BLE001 - mapped, original chained
            if _status(exc) in passthrough:
                raise
            mapped = map_google_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc


class GoogleGmailApi(_Lazy):
    """Implements ports_gmail.GmailApi."""

    def __init__(self, service: Any = None, *, cfg: GmailConfig | None = None, user_id: str = "me") -> None:
        super().__init__(service, None if service is not None else (lambda: build_service("gmail", "v1", cfg)))
        self.user_id = user_id

    @property
    def _users(self) -> Any:
        return self.service.users()

    def send(self, *, to: str, subject: str, body_text: str, body_html: str | None = None,
             reply_to: str | None = None, thread_id: str | None = None,
             in_reply_to: str | None = None, message_id: str | None = None) -> str:
        msg = EmailMessage()
        msg["To"], msg["Subject"] = to, subject
        if reply_to:
            msg["Reply-To"] = reply_to
        if message_id:
            msg["Message-ID"] = message_id
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg.set_content(body_text)
        if body_html:
            msg.add_alternative(body_html, subtype="html")
        body: dict[str, Any] = {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}
        if thread_id:
            body["threadId"] = thread_id
        out = self._exec(self._users.messages().send(userId=self.user_id, body=body))
        return str(out["id"])

    def history_list(self, start_history_id: int) -> tuple[list[str], int]:
        ids: list[str] = []
        latest = start_history_id
        page: str | None = None
        while True:
            req = self._users.history().list(userId=self.user_id, startHistoryId=start_history_id,
                                             historyTypes=["messageAdded"], pageToken=page)
            try:
                out = self._exec(req, passthrough=(404,))
            except Exception as exc:
                if _status(exc) == 404:
                    raise CursorLostError() from exc
                raise
            for h in out.get("history", []):
                for added in h.get("messagesAdded", []):
                    mid = added["message"]["id"]
                    if mid not in ids:
                        ids.append(mid)
            latest = max(latest, int(out.get("historyId", latest)))
            page = out.get("nextPageToken")
            if not page:
                return ids, latest

    def list_recent(self, query: str) -> list[str]:
        ids: list[str] = []
        page: str | None = None
        while True:
            out = self._exec(self._users.messages().list(userId=self.user_id, q=query, maxResults=100, pageToken=page))
            ids += [m["id"] for m in out.get("messages", [])]
            page = out.get("nextPageToken")
            if not page or len(ids) >= 500:
                return ids

    def profile_history_id(self) -> int:
        return int(self._exec(self._users.getProfile(userId=self.user_id))["historyId"])

    def get_message(self, message_id: str) -> dict[str, Any]:
        return self._exec(self._users.messages().get(userId=self.user_id, id=message_id, format="full"))

    def watch(self, topic: str) -> dict[str, Any]:
        out = self._exec(self._users.watch(userId=self.user_id, body={"topicName": topic, "labelIds": ["INBOX"]}))
        return {"historyId": int(out["historyId"]), "expiration": int(out["expiration"])}


class GoogleCalendarApi(_Lazy):
    """Implements ports_gmail.CalendarApi. A deterministic event id makes a re-run an update, not a duplicate."""

    def __init__(self, service: Any = None, *, cfg: GmailConfig | None = None) -> None:
        super().__init__(service, None if service is not None else (lambda: build_service("calendar", "v3", cfg)))

    def upsert_event(self, calendar_id: str, event_id: str, body: dict[str, Any]) -> str:
        events = self.service.events()
        try:
            self._exec(events.insert(calendarId=calendar_id, body={**body, "id": event_id}, sendUpdates="none"),
                       passthrough=(409,))
        except Exception as exc:
            if _status(exc) != 409:
                raise
            self._exec(events.update(calendarId=calendar_id, eventId=event_id, body=body, sendUpdates="none"))
        return event_id
