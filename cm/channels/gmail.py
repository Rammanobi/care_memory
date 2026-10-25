"""Lane M: Gmail adapter logic (F4 outbound digest, F5 inbound push + fetch).

Pure logic over Protocols in ports_gmail; no network, no clock reads (``now`` is passed in).
Env names (values never in code): GMAIL_OAUTH_CLIENT_JSON, GMAIL_REFRESH_TOKEN, GMAIL_MAILBOX,
DOCTOR_EMAIL_ALLOWLIST, GMAIL_PUBSUB_TOPIC, PUBSUB_PUSH_AUDIENCE, PUBSUB_PUSH_SA_EMAIL.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import parseaddr
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from cm.channels.ports_gmail import (
    CursorLostError,
    GmailApi,
    GmailAuthError,
    GmailQuotaError,
    GmailStateStore,
    GmailTransientError,
    TaskQueue,
    TokenStore,
    has_banned_term,
)
from cm.contracts.api import GmailNotification, PubSubPush
from cm.contracts.review import DigestItem

WATCH_RENEW_EVERY = timedelta(days=6)
TOKEN_TTL = timedelta(hours=48)
GRAMMAR = "APPROVE 1-5    APPROVE ALL    REJECT 3: reason    EDIT 3: new text"
RECENT_QUERY = "newer_than:2d"


# ---------------------------------------------------------------- push handler
def handle_push(push: PubSubPush, queue: TaskQueue, mailbox: str) -> int:
    """Decode, enqueue ``gmail-fetch-{historyId}`` and return the HTTP status (always 204).

    No Gmail API call here. A duplicate push hits ALREADY_EXISTS (enqueue returns False) and is acked.
    Undecodable or foreign-mailbox payloads are acked and dropped so Pub/Sub does not redeliver them.
    """
    try:
        raw = base64.b64decode(push.message.data, validate=True)
        note = GmailNotification.model_validate(json.loads(raw))
    except (ValueError, ValidationError):
        return 204
    if note.email_address.lower() != mailbox.lower():
        return 204
    queue.enqueue(f"gmail-fetch-{note.history_id}", {"mailbox": mailbox, "history_id": note.history_id})
    return 204


# ---------------------------------------------------------------- retry
def call_with_retry(fn: Callable[[], Any], *, tries: int = 6, sleep: Callable[[float], None] = time.sleep,
                    jitter: Callable[[], float] = lambda: 0.0) -> Any:
    """Retry quota (honouring retry_after) and transient errors, min(2^n + jitter, 64 s).

    Auth errors are never retried. After the last try the error propagates (Cloud Tasks retries).
    """
    for n in range(tries):
        try:
            return fn()
        except GmailAuthError:
            raise
        except (GmailQuotaError, GmailTransientError) as exc:
            if n == tries - 1:
                raise
            wait = getattr(exc, "retry_after", None)
            sleep(min(wait if wait is not None else 2**n + jitter(), 64.0))


# ---------------------------------------------------------------- message normalising
def normalize_message(raw: dict[str, Any]) -> dict[str, Any]:
    """Real Gmail ``format=full`` message -> {id, thread_id, labels, headers, text}.

    Already-normalised dicts (with a ``headers`` mapping) pass through.
    """
    if "headers" in raw and isinstance(raw["headers"], dict):
        return raw
    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    return {"id": raw["id"], "thread_id": raw.get("threadId"), "labels": raw.get("labelIds", []),
            "headers": headers, "text": _plain_text(payload), "attachments": _attachments(payload)}


TINY_IMAGE_BYTES = 10 * 1024      # an image this small is a logo or tracking pixel, never a document
INLINE_IMAGE_BYTES = 100 * 1024   # an inline / Content-ID image up to this size is a signature graphic


def _is_decoration(part: dict[str, Any]) -> bool:
    """Signature logos and other inline images: they must not become uploads."""
    mime = str(part.get("mimeType", "")).lower()
    if not mime.startswith("image/"):
        return False
    hdrs = {str(h.get("name", "")).lower(): str(h.get("value", "")) for h in part.get("headers", []) or []}
    size = (part.get("body") or {}).get("size")
    size = size if isinstance(size, int) else 0
    inline = hdrs.get("content-disposition", "").strip().lower().startswith("inline") or "content-id" in hdrs
    return size <= TINY_IMAGE_BYTES or (inline and size <= INLINE_IMAGE_BYTES)


def _attachments(part: dict[str, Any]) -> list[dict[str, Any]]:
    """Parts that carry a file name and an attachmentId -> [{filename, mime, size, attachment_id}].
    Inline signature images (logos) are skipped."""
    out: list[dict[str, Any]] = []
    body = part.get("body") or {}
    if part.get("filename") and body.get("attachmentId") and not _is_decoration(part):
        out.append({"filename": part["filename"], "mime": part.get("mimeType", "application/octet-stream"),
                    "size": body.get("size"), "attachment_id": body["attachmentId"]})
    for sub in part.get("parts", []) or []:
        out += _attachments(sub)
    return out


def _decode(part: dict[str, Any]) -> str:
    return base64.urlsafe_b64decode(part["body"]["data"] + "==").decode("utf-8", "replace")


def _find(part: dict[str, Any], mime: str) -> str:
    if part.get("mimeType") == mime and part.get("body", {}).get("data"):
        return _decode(part)
    for sub in part.get("parts", []) or []:
        text = _find(sub, mime)
        if text:
            return text
    return ""


def _html_to_text(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style).*?</(script|style)>", "", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</(div|p|li|tr|h\d)>", "\n", markup)
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def _plain_text(part: dict[str, Any]) -> str:
    """text/plain first; an HTML-only message falls back to tag-stripped text/html."""
    return _find(part, "text/plain") or _html_to_text(_find(part, "text/html"))


def is_own_mail(msg: dict[str, Any], mailbox: str) -> bool:
    sender = parseaddr(msg["headers"].get("from", ""))[1].lower()
    return sender == mailbox.lower() or "SENT" in msg.get("labels", [])


# ---------------------------------------------------------------- fetch worker
@dataclass
class FetchResult:
    processed: list[str] = field(default_factory=list)
    skipped_own: list[str] = field(default_factory=list)
    skipped_dup: list[str] = field(default_factory=list)
    cursor_reset: bool = False
    cursor: int | None = None


def fetch_worker(history_id: int, *, api: GmailApi, state: GmailStateStore, mailbox: str,
                 on_message: Callable[[dict[str, Any]], None],
                 sleep: Callable[[float], None] = time.sleep) -> FetchResult:
    """Task body for ``gmail-fetch-{historyId}`` and the 30-minute sweep.

    history.list (2 units) from the saved cursor; 404 -> recent list, then reset the cursor from the
    profile. Idempotent on message id. The cursor advances only after every message is handled, so a
    quota error mid-way leaves it untouched and the task retry re-reads (processed ids are skipped).
    """
    res = FetchResult()
    cursor = state.get_cursor()
    if cursor is None:
        cursor = max(history_id - 1, 0)
        ids, latest = _recent(api, sleep, res)
    else:
        try:
            ids, latest = call_with_retry(lambda: api.history_list(cursor), sleep=sleep)
        except CursorLostError:
            ids, latest = _recent(api, sleep, res)
    for mid in ids:
        if state.is_processed(mid):
            res.skipped_dup.append(mid)
            continue
        msg = normalize_message(call_with_retry(lambda m=mid: api.get_message(m), sleep=sleep))
        if is_own_mail(msg, mailbox):
            res.skipped_own.append(mid)
        else:
            on_message(msg)
            res.processed.append(mid)
        state.mark_processed(mid)
    res.cursor = state.advance_cursor(max(latest, history_id))
    return res


def _recent(api: GmailApi, sleep: Callable[[float], None], res: FetchResult) -> tuple[list[str], int]:
    res.cursor_reset = True
    ids = call_with_retry(lambda: api.list_recent(RECENT_QUERY), sleep=sleep)
    return ids, call_with_retry(api.profile_history_id, sleep=sleep)


# ---------------------------------------------------------------- watch renewal
def should_renew_watch(expiration_ms: int | None, last_renewed: datetime | None, now: datetime) -> bool:
    """Pure: renew every 6 days, or when the watch expires in under 48 h, or when unknown."""
    if expiration_ms is None or last_renewed is None:
        return True
    if now - last_renewed >= WATCH_RENEW_EVERY:
        return True
    return expiration_ms / 1000 - now.timestamp() < 48 * 3600


def renew_watch_job(*, api: GmailApi, state: GmailStateStore, topic: str, now: datetime,
                    last_renewed: datetime | None, sleep: Callable[[float], None] = time.sleep) -> bool:
    """Entry point for /tasks/gmail-watch-renew (users.watch = 100 units). True when renewed."""
    if not should_renew_watch(state.get_watch_expiry(), last_renewed, now):
        return False
    out = call_with_retry(lambda: api.watch(topic), sleep=sleep)
    state.set_watch(int(out["historyId"]), int(out["expiration"]))
    return True


# ---------------------------------------------------------------- digest
def token_hash(token: str, n: int) -> str:
    return hashlib.sha256(f"{token}:{n}".encode()).hexdigest()


@dataclass
class Digest:
    subject: str
    body_text: str
    body_html: str
    reply_to: str
    message_id: str
    token: str
    approval_by_n: dict[int, UUID]


def build_digest(items: list[DigestItem], *, doctor_id: str, mailbox: str, day: str, console_url: str,
                 red_titles: list[str] | None = None, tokens: TokenStore | None = None,
                 now: datetime | None = None, token: str | None = None) -> Digest | None:
    """Plain text first (grammar on top), HTML alternative. Red items are listed unnumbered, no token.

    Returns None when there is nothing to say. Mints one token row per numbered item when ``tokens`` given.
    """
    red = red_titles or []
    if not items and not red:
        return None
    t = token or secrets.token_urlsafe(16)
    numbered = sorted(items, key=lambda i: i.n)
    lines = ["Reply to this email with one command per line:", GRAMMAR, ""]
    rows: list[str] = []
    for it in numbered:
        lines += [f"{it.n}. [{it.tier.upper()}] {it.title}", f"   {it.summary}", f"   Open: {console_url}/review/{it.approval_id}"]
        rows.append(f"<li value=\"{it.n}\"><b>[{it.tier.upper()}]</b> {html.escape(it.title)}<br>{html.escape(it.summary)}</li>")
    if red:
        lines += ["", "Console only (cannot be decided by email):"] + [f"- {r}" for r in red]
    body_text = "\n".join(lines)
    body_html = ("<p>Reply with one command per line:<br><code>" + html.escape(GRAMMAR) + "</code></p><ol>"
                 + "".join(rows) + "</ol>"
                 + ("<p><b>Console only:</b></p><ul>" + "".join(f"<li>{html.escape(r)}</li>" for r in red) + "</ul>" if red else ""))
    local, _, domain = mailbox.partition("@")
    d = Digest(subject=f"CareMemory review - {len(numbered)} items - ref {t[:6]}", body_text=body_text,
               body_html=body_html, reply_to=f"{local}+r_{t}@{domain}", message_id=f"<digest-{doctor_id}-{day}@caremem>",
               token=t, approval_by_n={i.n: i.approval_id for i in numbered})
    if tokens is not None and now is not None and numbered:
        tokens.mint([(token_hash(t, i.n), i.approval_id) for i in numbered], doctor_id, now + TOKEN_TTL)
    return d


# ---------------------------------------------------------------- outbound (approved outbox rows only)
@dataclass
class OutboxRow:
    outbox_id: UUID
    to: str
    subject: str
    body_text: str
    body_html: str | None = None
    reply_to: str | None = None
    thread_id: str | None = None
    in_reply_to: str | None = None
    message_id: str | None = None
    approval_ref: UUID | None = None   # decision approval or approved template id
    template_id: UUID | None = None
    provider_message_id: str | None = None


@dataclass
class SendOutcome:
    status: str  # sent | retry | failed | skipped
    provider_message_id: str | None = None
    skip_reason: str | None = None
    retry_after_s: float | None = None
    error: str | None = None


def send_outbox_row(row: OutboxRow, api: GmailApi, *, sleep: Callable[[float], None] = time.sleep,
                    tries: int = 6, check_banned: bool = False) -> SendOutcome:
    """Only the outbox drainer calls this. A row with neither approval_ref nor template_id is refused."""
    if row.approval_ref is None and row.template_id is None:
        return SendOutcome("skipped", skip_reason="invalid_approval")
    if row.provider_message_id:
        return SendOutcome("skipped", row.provider_message_id, skip_reason="already_sent")
    if check_banned and has_banned_term(row.subject + "\n" + row.body_text):
        return SendOutcome("skipped", skip_reason="banned_term")
    try:
        pid = call_with_retry(lambda: api.send(
            to=row.to, subject=row.subject, body_text=row.body_text, body_html=row.body_html,
            reply_to=row.reply_to, thread_id=row.thread_id, in_reply_to=row.in_reply_to,
            message_id=row.message_id), tries=tries, sleep=sleep)
    except GmailAuthError as exc:
        return SendOutcome("failed", error=f"auth:{type(exc).__name__}")  # never retried; console banner
    except GmailQuotaError as exc:
        return SendOutcome("retry", retry_after_s=exc.retry_after or 64.0, error="quota")
    except GmailTransientError:
        return SendOutcome("retry", retry_after_s=64.0, error="transient")
    return SendOutcome("sent", pid)


class GmailChannel:
    """Thin facade bundling the ports for the integrator."""

    def __init__(self, api: GmailApi, state: GmailStateStore, queue: TaskQueue, mailbox: str) -> None:
        self.api, self.state, self.queue, self.mailbox = api, state, queue, mailbox

    def on_push(self, push: PubSubPush) -> int:
        return handle_push(push, self.queue, self.mailbox)
