"""Email the doctor when a patient question needs their expertise (in addition to the console).

Settings by env NAME only (values live in the git-ignored .env, never in the repo):
  DOCTOR_NOTIFY_EMAIL  recipient: the owner's mailbox
  DOCTOR_NOTIFY_MODE   off | dry-run | send   (default dry-run)
  CONSOLE_BASE_URL     link target (default http://localhost:5173)
  'send' also needs GMAIL_OAUTH_CLIENT_JSON, GMAIL_REFRESH_TOKEN, GMAIL_MAILBOX; otherwise the call is
  skipped with reason 'gmail not configured'.

Dry-run writes the rendered message to out/email_outbox/ and never contacts Gmail. The email carries no
AI-written text and is a notification only: replies to it do nothing (no approve-by-email here).
Quiet hours do not apply. Throttle: 1 email/patient/10 min (normal, high); urgent always sends, max 3 per
patient per hour; idempotent per approval_id. Throttle state is an audit_log row (cm.store.gmail_repo).

CLI: ``python -m cm.channels.doctor_notify --send-test --to-env [--i-confirm-owner-approved]``.
A real test email goes out ONLY with DOCTOR_NOTIFY_MODE=send, Gmail env configured AND the confirm flag;
otherwise it prints what it would send and exits 0. The owner confirms before any real email is sent.
"""

from __future__ import annotations

import argparse
import contextlib
import html
import os
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Protocol

from cm.core import tokenize as _tok
from cm.core.clock import IST
from cm.core.clock import now as _clock_now

MODES = ("off", "dry-run", "send")
DEFAULT_CONSOLE_URL = "http://localhost:5173"
EXCERPT_MAX = 200
REMINDER = "Please review in the console. Replies to this email do not send anything to the patient."
OUTBOX_DIR = Path(__file__).resolve().parents[2] / "out" / "email_outbox"
_GMAIL_ENV = ("GMAIL_OAUTH_CLIENT_JSON", "GMAIL_REFRESH_TOKEN", "GMAIL_MAILBOX")
_PREFIX = {"urgent": "Urgent", "high": "High"}
_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,23}$")
_LONG_NUM = re.compile(r"(?<![\w-])\d(?:[\s-]?\d){6,}(?!\w)")  # any 7+ digit run (ids, phones the tokenizer missed)
_CTRL = re.compile(r"[\x00-\x1f\x7f]+")
_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


# ---------------------------------------------------------------- throttle stores
class NotifyStore(Protocol):
    def claim(self, approval_id: str, patient_code: str, urgent: bool, now: datetime) -> str: ...

    def release(self, approval_id: str, now: datetime) -> None: ...


class MemoryNotifyStore:
    """In-memory fallback (tests, or no database). Same rules as cm.store.gmail_repo."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def claim(self, approval_id: str, patient_code: str, urgent: bool, now: datetime) -> str:
        from datetime import timedelta

        if any(r["approval"] == approval_id for r in self.rows):
            return "duplicate"
        mine = [r for r in self.rows if r["code"] == patient_code]
        if urgent:
            if sum(1 for r in mine if r["urgent"] and r["at"] > now - timedelta(hours=1)) >= 3:
                return "throttled"
        elif any(r["at"] > now - timedelta(minutes=10) for r in mine):
            return "throttled"
        self.rows.append({"approval": approval_id, "code": patient_code, "urgent": urgent, "at": now})
        return "ok"

    def release(self, approval_id: str, now: datetime) -> None:
        self.rows = [r for r in self.rows if r["approval"] != approval_id]


class PgNotifyStore:
    def claim(self, approval_id: str, patient_code: str, urgent: bool, now: datetime) -> str:
        from cm.store import gmail_repo

        return gmail_repo.doctor_notify_claim(approval_id, patient_code, urgent, now)

    def release(self, approval_id: str, now: datetime) -> None:
        from cm.store import gmail_repo

        gmail_repo.doctor_notify_release(approval_id, now)


_fallback = MemoryNotifyStore()


class _DefaultStore:
    """Postgres when reachable, else the in-memory fallback (never raises)."""

    def claim(self, approval_id: str, patient_code: str, urgent: bool, now: datetime) -> str:
        try:
            return PgNotifyStore().claim(approval_id, patient_code, urgent, now)
        except Exception:  # noqa: BLE001 (db down: keep notifying, process-local throttle)
            return _fallback.claim(approval_id, patient_code, urgent, now)

    def release(self, approval_id: str, now: datetime) -> None:
        try:
            PgNotifyStore().release(approval_id, now)
        except Exception:  # noqa: BLE001
            _fallback.release(approval_id, now)


# ---------------------------------------------------------------- rendering
def _clean(text: str) -> str:
    return _CTRL.sub(" ", str(text)).strip()


def _mask_excerpt(text: object) -> str:
    s = _clean("" if text is None else str(text))
    s = _tok.tokenize(s)
    s = _LONG_NUM.sub("[NUMBER]", s)
    s = re.sub(r"\s+", " ", s)
    return s if len(s) <= EXCERPT_MAX else s[: EXCERPT_MAX - 3].rstrip() + "..."


def _code(patient_code: object) -> str:
    c = _clean("" if patient_code is None else str(patient_code))
    return c if _CODE_RE.match(c) else "unknown"


def _word(value: object, default: str) -> str:
    v = _SAFE.sub("", _clean("" if value is None else str(value)))[:32]
    return v or default


def priority_label(priority: object) -> str:
    return _PREFIX.get(str(priority or "").strip().lower(), "New")


def console_link(base_url: str | None, approval_id: str) -> str:
    base = (base_url or DEFAULT_CONSOLE_URL).strip().rstrip("/")
    if not re.match(r"^https?://[^\s]+$", base):
        base = DEFAULT_CONSOLE_URL
    return f"{base}/requests?approval={_SAFE.sub('', str(approval_id))[:64]}"


def render_question_email(
    approval_id: str,
    *,
    patient_code: str,
    category: str,
    priority: str,
    question_excerpt: str,
    now: datetime | None = None,
    channel: str = "telegram",
    console_base_url: str | None = None,
) -> tuple[str, str, str]:
    """(subject, text_body, html_body). Patient code only, masked excerpt, no AI text. Pure, never network."""
    code, cat = _code(patient_code), _word(category, "question")
    label, chan = priority_label(priority), _word(channel, "telegram")
    excerpt = _mask_excerpt(question_excerpt)
    at = (now or _clock_now()).astimezone(IST).strftime("%d %b %Y, %H:%M IST")
    link = console_link(console_base_url, approval_id)
    subject = f"[CareMemory] {label} patient question {code} ({cat})"
    rows = [("Patient", code), ("Channel", chan), ("Category", cat), ("Urgency", label), ("Received", at)]
    text = "\n".join(f"{k}: {v}" for k, v in rows)
    text += f"\n\nQuestion (masked excerpt):\n{excerpt}\n\nOpen in the console:\n{link}\n\n{REMINDER}\n"
    trs = "".join(
        f"<tr><td style=\"padding:2px 12px 2px 0;color:#555\">{k}</td><td><b>{html.escape(v)}</b></td></tr>"
        for k, v in rows
    )
    body = (
        "<div style=\"font-family:Arial,sans-serif;font-size:14px;color:#111\">"
        f"<table>{trs}</table>"
        f"<p style=\"margin:14px 0 4px\">Question (masked excerpt):</p>"
        f"<blockquote style=\"margin:0;padding:8px 12px;background:#f4f4f4;border-left:3px solid #999\">"
        f"{html.escape(excerpt)}</blockquote>"
        f"<p><a href=\"{html.escape(link, quote=True)}\">Open in the console</a></p>"
        f"<p style=\"color:#555\">{html.escape(REMINDER)}</p></div>"
    )
    return subject, text, body


# ---------------------------------------------------------------- config
def _mode(env: Mapping[str, str]) -> str:
    m = (env.get("DOCTOR_NOTIFY_MODE") or "dry-run").strip().lower().replace("_", "-")
    return m if m in MODES else "dry-run"


def _recipient(env: Mapping[str, str]) -> str | None:
    addr = parseaddr((env.get("DOCTOR_NOTIFY_EMAIL") or "").strip())[1]
    return addr if addr and "@" in addr and not re.search(r"[\s,;<>]", addr) else None


def _gmail_ready(env: Mapping[str, str]) -> bool:
    return all((env.get(k) or "").strip() for k in _GMAIL_ENV)


def _write_outbox(directory: Path, name: str, to: str, subject: str, text: str, body_html: str, now: datetime) -> Path:
    msg = EmailMessage()
    msg["To"], msg["Subject"], msg["Date"] = to, subject, now.astimezone(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")
    msg["X-CareMemory-Dry-Run"] = "1"
    msg.set_content(text)
    msg.add_alternative(body_html, subtype="html")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{now.astimezone(UTC):%Y%m%dT%H%M%S}_{_SAFE.sub('', name)[:64] or 'msg'}.eml"
    path.write_bytes(msg.as_bytes())
    return path


def _send(api: Any, env: Mapping[str, str], to: str, subject: str, text: str, body_html: str) -> None:
    from cm.channels.gmail import call_with_retry

    if api is None:
        from cm.channels.gmail_google import GmailConfig, GoogleGmailApi

        api = GoogleGmailApi(cfg=GmailConfig.from_env(dict(env)))
    call_with_retry(lambda: api.send(to=to, subject=subject, body_text=text, body_html=body_html))


# ---------------------------------------------------------------- main entry
def notify_doctor_new_question(
    approval_id: str,
    *,
    patient_code: str,
    category: str,
    priority: str,
    question_excerpt: str,
    now: datetime | None = None,
    channel: str = "telegram",
    env: Mapping[str, str] | None = None,
    api: Any = None,
    store: NotifyStore | None = None,
    outbox_dir: Path | None = None,
) -> dict[str, Any]:
    """Notify the doctor by email. Never raises. Returns {status, reason, path?}.

    status: skipped (off, not configured, duplicate, throttled) | dry_run | sent | failed.
    ``env``, ``api``, ``store`` and ``outbox_dir`` are injection points for tests.
    """
    claimed = False
    st: Any = None
    at = None
    try:
        e: Mapping[str, str] = os.environ if env is None else env
        mode = _mode(e)
        if mode == "off":
            return {"status": "skipped", "reason": "off"}
        to = _recipient(e)
        if mode == "send":
            if not _gmail_ready(e):
                return {"status": "skipped", "reason": "gmail not configured"}
            if to is None:
                return {"status": "skipped", "reason": "recipient not configured"}
        aid = _clean("" if approval_id is None else str(approval_id))
        if not aid:
            return {"status": "failed", "reason": "invalid approval_id"}
        at = now or _clock_now()
        code = _code(patient_code)
        urgent = priority_label(priority) == "Urgent"
        st = store if store is not None else _DefaultStore()
        verdict = st.claim(aid, code, urgent, at)
        if verdict != "ok":
            return {"status": "skipped", "reason": verdict}
        claimed = True
        subject, text, body = render_question_email(
            aid, patient_code=patient_code, category=category, priority=priority,
            question_excerpt=question_excerpt, now=at, channel=channel, console_base_url=e.get("CONSOLE_BASE_URL"),
        )
        if mode == "dry-run":
            path = _write_outbox(outbox_dir or OUTBOX_DIR, aid, to or "(DOCTOR_NOTIFY_EMAIL unset)", subject, text, body, at)
            return {"status": "dry_run", "reason": "dry-run", "path": str(path)}
        _send(api, e, to or "", subject, text, body)
        return {"status": "sent", "reason": "sent"}
    except Exception as exc:  # noqa: BLE001 (contract: never raises; reason is the class name only, no values)
        if claimed and st is not None and at is not None:
            with contextlib.suppress(Exception):
                st.release(str(approval_id), at)
        return {"status": "failed", "reason": type(exc).__name__}


# ---------------------------------------------------------------- CLI
def _cli(argv: list[str] | None = None, env: Mapping[str, str] | None = None, api: Any = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m cm.channels.doctor_notify", description=__doc__.split("\n")[0])
    ap.add_argument("--send-test", action="store_true", help="send ONE clearly labelled test email")
    ap.add_argument("--to-env", action="store_true", help="recipient comes from DOCTOR_NOTIFY_EMAIL")
    ap.add_argument("--i-confirm-owner-approved", action="store_true", help="the owner approved a real send")
    a = ap.parse_args(argv)
    if not (a.send_test and a.to_env):
        ap.print_help()
        return 0
    if env is None:
        from cm.core.config import load_dotenv

        load_dotenv()
    e: Mapping[str, str] = os.environ if env is None else env
    to = _recipient(e)
    subject = "[CareMemory] TEST email (ignore): doctor notification check"
    text = (
        "This is a TEST message from CareMemory to check doctor email notification.\n"
        "It contains no patient data. No action is needed.\n\n" + REMINDER + "\n"
    )
    body = f"<p><b>TEST</b> message from CareMemory (no patient data, no action needed).</p><p>{html.escape(REMINDER)}</p>"
    mode, ready = _mode(e), _gmail_ready(e)
    go = mode == "send" and ready and to is not None and a.i_confirm_owner_approved
    if not go:
        why = []
        if mode != "send":
            why.append(f"DOCTOR_NOTIFY_MODE is '{mode}', not 'send'")
        if not ready:
            why.append("Gmail env not configured")
        if to is None:
            why.append("DOCTOR_NOTIFY_EMAIL not set")
        if not a.i_confirm_owner_approved:
            why.append("--i-confirm-owner-approved not passed")
        print("NOT SENT (the owner confirms before any real email). Would send:")
        print(f"  to: {'<DOCTOR_NOTIFY_EMAIL (set)>' if to else '<DOCTOR_NOTIFY_EMAIL (unset)>'}")
        print(f"  subject: {subject}\n  body:\n    " + text.replace("\n", "\n    "))
        print("  reasons: " + "; ".join(why))
        return 0
    try:
        _send(api, e, to or "", subject, text, body)
    except Exception as exc:  # noqa: BLE001
        print(f"send failed: {type(exc).__name__}")
        return 1
    print("test email sent")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
