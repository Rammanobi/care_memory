"""Property tests for the upload pipeline's pure parts (no database, no network): validation, filename
cleanup, PII masking, idempotency keys, the Gmail patient-code rule and the portal body-size middleware."""

from __future__ import annotations

import asyncio
import re
import unicodedata
import zlib
from typing import Any

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from cm.channels.gmail_attach import find_patient_code
from cm.channels.gmail_reply import sender_ok
from cm.uploads import extract as ex
from cm.uploads import intake
from cm.uploads import review as rv
from cm.uploads.validate import (
    MAX_IMAGE_PIXELS,
    UploadRejected,
    sanitise_filename,
    sniff,
    validate_upload,
)

FAST = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
EXTS = st.sampled_from(["jpg", "png", "pdf", "txt"])
BIDI = set("‎‏‪‫‬‭‮⁦⁧⁨⁩")


@pytest.fixture(autouse=True)
def _cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPLOAD_MAX_MB", "0.25")


CAP = int(0.25 * 1024 * 1024)


# ---------------------------------------------------------------- filenames
@FAST
@given(name=st.text(max_size=400), ext=EXTS)
def test_sanitised_name_is_never_a_path_or_hostile(name: str, ext: str) -> None:
    out = sanitise_filename(name, ext)
    assert out.endswith("." + ext) and len(out) <= 80 + 1 + len(ext)
    assert (
        not out.startswith(".")
        and "/" not in out
        and "\\" not in out
        and ".." not in out[: -len(ext) - 1]
    )
    assert not any(unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") for c in out)
    assert not (set(out) & BIDI)
    assert sanitise_filename(out, ext) == out  # idempotent


@FAST
@given(
    dirs=st.lists(st.sampled_from(["..", ".", "etc", "C:", "~", "%2e%2e"]), max_size=6),
    base=st.from_regex(r"[A-Za-z0-9]{1,20}", fullmatch=True),
    sep=st.sampled_from(["/", "\\"]),
)
def test_traversal_prefix_never_survives(dirs: list[str], base: str, sep: str) -> None:
    out = sanitise_filename(sep.join([*dirs, base + ".pdf"]), "pdf")
    assert out == base + ".pdf"


# ---------------------------------------------------------------- validation
@FAST
@given(data=st.binary(max_size=4096), name=st.text(max_size=50), mime=st.text(max_size=30))
def test_validate_only_ever_rejects_with_a_known_code(data: bytes, name: str, mime: str) -> None:
    try:
        v = validate_upload(name, data, mime)
    except UploadRejected as exc:
        assert exc.code in ("bad_type", "too_large")
        return
    assert v.ext == sniff(data) and v.size == len(data) and v.filename.endswith("." + v.ext)


@FAST
@given(
    prefix=st.sampled_from(
        [
            b"MZ",
            b"\x7fELF",
            b"PK\x03\x04",
            b"#!",
            b"GIF8",
            b"%!PS",
            b"Rar!",
            b"\x1f\x8b",
            b"BM",
            b"RIFF",
            b"<",
        ]
    ),
    rest=st.binary(max_size=512),
)
def test_denied_magic_is_always_refused(prefix: bytes, rest: bytes) -> None:
    with pytest.raises(UploadRejected):
        validate_upload("x.pdf", prefix + rest, "application/pdf")


@FAST
@given(
    head=st.sampled_from([b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"%PDF-1.4\n"]),
    filler=st.binary(max_size=8000),
    tag=st.sampled_from(["script", "html", "iframe", "svg", "SCRIPT", "!DOCTYPE"]),
    ws=st.sampled_from(["", " ", "\n"]),
    end=st.sampled_from([">", " ", "/"]),
)
def test_markup_anywhere_in_a_binary_is_refused(
    head: bytes, filler: bytes, tag: str, ws: str, end: str
) -> None:
    data = head + filler + f"<{ws}{tag}{end}".encode()
    assert len(data) <= CAP
    with pytest.raises(UploadRejected):
        validate_upload("x", data)


@FAST
@given(
    text=st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=0x2FFF, blacklist_characters="<"),
        max_size=6000,
    ),
    tag=st.sampled_from(["script", "svg", "html", "iframe", "?xml", "object"]),
)
def test_markup_anywhere_in_text_is_refused(text: str, tag: str) -> None:
    data = (text + f"\n<{tag} x>").encode()
    assume(len(data) <= CAP)
    with pytest.raises(UploadRejected):
        validate_upload("n.txt", data)


@FAST
@given(extra=st.integers(min_value=0, max_value=4096))
def test_size_boundary(extra: int) -> None:
    ok = b"a" * CAP
    assert validate_upload("n.txt", ok).size == CAP
    with pytest.raises(UploadRejected) as e:
        validate_upload("n.txt", ok + b"a" * (extra + 1))
    assert e.value.code == "too_large"


@FAST
@given(
    w=st.integers(min_value=1, max_value=2**31 - 1), h=st.integers(min_value=1, max_value=2**31 - 1)
)
def test_png_pixel_bomb_guard(w: int, h: int) -> None:
    import struct

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + ihdr
        + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    )
    if w * h > MAX_IMAGE_PIXELS:
        with pytest.raises(UploadRejected):
            validate_upload("a.png", data)
    else:
        assert validate_upload("a.png", data).ext == "png"


@settings(max_examples=15, deadline=None)
@given(mb=st.integers(min_value=65, max_value=120))
def test_pdf_flate_bomb_refused_without_inflating_it_all(mb: int) -> None:
    raw = zlib.compress(b"\x00" * (mb * 1024 * 1024), 9)
    head = b"1 0 obj\n<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(raw)
    data = b"%PDF-1.4\n" + head + raw + b"\nendstream\nendobj\n"
    assume(len(data) <= CAP)
    with pytest.raises(UploadRejected):
        validate_upload("b.pdf", data)


@FAST
@given(
    name=st.sampled_from(
        [b"JavaScript", b"Launch", b"EmbeddedFile", b"EmbeddedFiles", b"RichMedia"]
    ),
    esc=st.lists(st.booleans(), min_size=12, max_size=12),
    compressed=st.booleans(),
)
def test_pdf_active_content_refused_even_when_obfuscated(
    name: bytes, esc: list[bool], compressed: bool
) -> None:
    hidden = b"".join(b"#%02X" % c if e else bytes([c]) for c, e in zip(name, esc, strict=False))
    obj = b"<< /S /" + hidden + b" /F (x) >>"
    if compressed:
        z = zlib.compress(obj)
        body = (
            b"1 0 obj\n<< /Type /ObjStm /Length %d /Filter /FlateDecode >>\nstream\n" % len(z)
            + z
            + b"\nendstream\nendobj\n"
        )
    else:
        body = b"1 0 obj\n" + obj + b"\nendobj\n"
    with pytest.raises(UploadRejected):
        validate_upload("a.pdf", b"%PDF-1.4\n" + body + b"%%EOF\n")


# ---------------------------------------------------------------- PII masking and extraction helpers
PHONE = st.from_regex(r"[6-9][0-9]{9}", fullmatch=True)
AADHAAR = st.from_regex(r"[2-9][0-9]{3} [0-9]{4} [0-9]{4}", fullmatch=True)
WORDS = st.text(alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Zs")), max_size=60)


@FAST
@given(pre=WORDS, post=WORDS, phone=PHONE, aadhaar=AADHAAR)
def test_mask_never_leaks_phone_or_aadhaar(pre: str, post: str, phone: str, aadhaar: str) -> None:
    out = ex.mask(f"{pre} phone {phone} id {aadhaar} {post}")
    assert (
        phone not in out
        and aadhaar not in out
        and aadhaar.replace(" ", "") not in out.replace(" ", "")
    )
    assert not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", out)


@FAST
@given(text=st.text(max_size=3000), limit=st.integers(min_value=0, max_value=500))
def test_mask_respects_the_limit_and_strips_controls(text: str, limit: int) -> None:
    out = ex.mask(text, limit)
    assert len(out) <= limit and not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", out)


@FAST
@given(text=st.text(max_size=4000))
def test_rule_fields_are_capped_low_confidence_and_never_raise(text: str) -> None:
    fields = ex._text_fields(text)
    assert len(fields) <= 45 and all(f["confidence"] == 0.5 for f in fields)


@FAST
@given(text=st.text(max_size=500), hint=st.sampled_from([*ex.DOC_TYPES, None, "evil", "system"]))
def test_doc_type_is_always_known_and_a_valid_hint_wins(text: str, hint: str | None) -> None:
    dt = ex.guess_doc_type(text, "", hint)
    assert dt in ex.DOC_TYPES and (hint not in ex.DOC_TYPES or dt == hint)


# ---------------------------------------------------------------- idempotency keys
@FAST
@given(
    tok=st.from_regex(r"P-[0-9]{4}", fullmatch=True),
    data=st.binary(max_size=200),
    other=st.from_regex(r"P-[0-9]{4}", fullmatch=True),
)
def test_content_hash_is_per_patient(tok: str, data: bytes, other: str) -> None:
    assert intake.content_hash(tok, data) == intake.content_hash(tok, data)
    if other != tok:
        assert intake.content_hash(tok, data) != intake.content_hash(other, data)


@FAST
@given(uid=st.uuids())
def test_task_ids_are_colon_free_and_stable(uid: Any) -> None:
    assert rv.task_id(str(uid)) == f"docx-{uid}" and ":" not in rv.task_id(str(uid))


@FAST
@given(
    tg=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
    mid=st.one_of(st.none(), st.text(max_size=10)),
    aid=st.one_of(st.none(), st.text(max_size=10)),
)
def test_origin_key_needs_complete_ids(tg: str | None, mid: str | None, aid: str | None) -> None:
    o = {"telegram_file_unique_id": tg, "gmail_message_id": mid, "gmail_attachment_id": aid}
    k = intake.origin_key(o)
    if tg:
        assert k == f"telegram:{tg}"
    elif mid and aid:
        assert k == f"gmail:{mid}:{aid}"
    else:
        assert k is None


# ---------------------------------------------------------------- Gmail
CODE = st.integers(min_value=0, max_value=9999)  # persons.token is ^P-[0-9]{4}$


@FAST
@given(codes=st.lists(CODE, min_size=2, max_size=4, unique=True), noise=WORDS)
def test_two_distinct_codes_in_the_subject_are_ambiguous(codes: list[int], noise: str) -> None:
    subj = noise + " " + " ".join(f"PT-{c:04d}" for c in codes)
    assume(len({f"{c:04d}" for c in codes}) > 1)
    assert find_patient_code({"headers": {"subject": subj}, "text": ""}) is None


@FAST
@given(c=CODE, noise=WORDS)
def test_one_code_resolves(c: int, noise: str) -> None:
    assert (
        find_patient_code({"headers": {"subject": f"{noise} pt-{c:04d}"}, "text": ""})
        == f"P-{c:04d}"
    )


@FAST
@given(
    evil=st.from_regex(r"[a-z]{1,8}@[a-z]{1,8}\.(test|com|in)", fullmatch=True),
    shape=st.sampled_from(
        [
            "{doc} <{evil}>",
            '"{doc}" <{evil}>',
            "{evil} ({doc})",
            "{doc}, {evil}",
            "<{doc}> <{evil}>",
        ]
    ),
)
def test_sender_with_two_addresses_is_never_trusted(evil: str, shape: str) -> None:
    doc = "doc@clinic.org"
    assume(evil != doc)
    hdr = {"from": shape.format(doc=doc, evil=evil), "authentication-results": "dmarc=pass"}
    assert sender_ok(hdr, doc) is False


# ---------------------------------------------------------------- portal body-size middleware
@settings(max_examples=60, deadline=None)
@given(
    chunks=st.lists(st.integers(min_value=1, max_value=48 * 1024), min_size=1, max_size=60),
    declare=st.booleans(),
)
def test_body_limit_never_reads_far_past_the_cap(chunks: list[int], declare: bool) -> None:
    from cm.api.body_limit import FRAMING_SLACK, BodyLimitMiddleware

    cap = 256 * 1024
    total = sum(chunks)
    state = {"i": 0, "pulled": 0}
    sent: list[dict[str, Any]] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:  # reads the whole body, then 200
        while True:
            m = await receive()
            if m["type"] == "http.disconnect" or not m.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive() -> dict[str, Any]:
        if state["i"] < len(chunks):
            n = chunks[state["i"]]
            state["i"] += 1
            state["pulled"] += n
            return {"type": "http.request", "body": b"x" * n, "more_body": state["i"] < len(chunks)}
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(m: dict[str, Any]) -> None:
        sent.append(m)

    headers = [(b"content-length", str(total).encode())] if declare else []
    scope = {"type": "http", "method": "POST", "path": "/portal/documents", "headers": headers}
    asyncio.run(
        BodyLimitMiddleware(inner, ("/portal/documents",), lambda: cap)(scope, receive, send)
    )
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    limit = cap + FRAMING_SLACK
    assert status == (413 if total > limit else 200)
    assert len([m for m in sent if m["type"] == "http.response.start"]) == 1
    if total > limit:
        assert state["pulled"] <= limit + max(chunks)
        if declare:
            assert state["pulled"] == 0
