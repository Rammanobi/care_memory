"""Upload validation: magic bytes decide, never the name or the declared mime."""

from __future__ import annotations

import io

import pytest

from cm.uploads.storage import LocalStorage, StorageError
from cm.uploads.validate import (
    MAX_PDF_PAGES,
    UploadRejected,
    sanitise_filename,
    validate_upload,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def _pdf(pages: int) -> bytes:
    from pypdf import PdfWriter

    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _code(name: str, data: bytes, mime: str | None = None) -> str:
    with pytest.raises(UploadRejected) as e:
        validate_upload(name, data, mime)
    return e.value.code


@pytest.mark.parametrize(
    ("data", "ext"),
    [(PNG, "png"), (JPG, "jpg"), (_pdf(1), "pdf"), (b"reports ok\n", "txt")],
)
def test_allowed_types_by_magic(data: bytes, ext: str) -> None:
    v = validate_upload("scan", data)
    assert v.ext == ext and v.filename.endswith("." + ext)


def test_spoofed_extension_and_mime_do_not_help() -> None:
    assert _code("photo.png", b"MZ\x90\x00" + b"\x00" * 64, "image/png") == "bad_type"
    assert _code("a.pdf", b"PK\x03\x04" + b"\x00" * 64) == "bad_type"
    v = validate_upload("report.pdf", PNG, "application/pdf")  # real type wins, name is corrected
    assert v.ext == "png" and v.filename == "report.png"


@pytest.mark.parametrize(
    "data",
    [
        b"\x7fELF\x02\x01\x01",
        b"<html><script>alert(1)</script></html>",
        b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"/>',
        b"#!/bin/sh\nrm -rf /",
        b"GIF89a\x01\x00",
        b"\xff\xfe\x00\x00\x80\x81",  # not utf-8
        b"text with a nul\x00 byte",
    ],
)
def test_rejected_content(data: bytes) -> None:
    assert _code("x.txt", data) == "bad_type"


def test_empty_and_oversize(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _code("a.txt", b"") == "bad_type"
    monkeypatch.setenv("UPLOAD_MAX_MB", "1")
    assert _code("a.png", PNG + b"\x00" * (1024 * 1024)) == "too_large"
    validate_upload("a.png", PNG)  # under the cap still fine


def test_polyglots_rejected() -> None:
    assert _code("a.png", PNG + b"<script>alert(1)</script>") == "bad_type"  # markup near the head
    zipish = JPG + b"x" * 100 + b"PK\x03\x04" + b"y" * 50 + b"PK\x05\x06" + b"\x00" * 18
    assert _code("a.jpg", zipish) == "bad_type"
    assert _code("a.txt", b"<svg onload=alert(1)>") == "bad_type"


def test_pdf_page_cap() -> None:
    validate_upload("a.pdf", _pdf(MAX_PDF_PAGES))
    assert _code("a.pdf", _pdf(MAX_PDF_PAGES + 1)) == "bad_type"


@pytest.mark.parametrize(
    "name",
    [
        "../../etc/passwd",
        "..\\..\\windows\\system32\\evil.png",
        "/abs/path/a.txt",
        "a\x00b\nc.txt",
        "",
        None,
    ],
)
def test_traversal_and_junk_filenames(name: str | None) -> None:
    out = sanitise_filename(name, "txt")
    assert out.endswith(".txt") and "/" not in out and "\\" not in out and ".." not in out
    assert "\x00" not in out and "\n" not in out


def test_filename_keeps_readable_name_and_caps_length() -> None:
    assert sanitise_filename("Lab report 12-May.jpeg", "jpg") == "Lab report 12-May.jpg"
    assert len(sanitise_filename("a" * 500, "pdf")) <= 84


def test_local_storage_roundtrip_and_traversal(tmp_path) -> None:
    st = LocalStorage(tmp_path)
    uri = st.put("P-0142/" + "a" * 64, b"hello")
    assert st.exists(uri) and st.get(uri) == b"hello"
    assert st.put("P-0142/" + "a" * 64, b"hello") == uri  # idempotent
    assert not list((tmp_path / "P-0142").glob(".tmp-*"))
    for bad in ["../x", "P-0142/../../x", "/etc/passwd", "P-0142//x", "", "a/b/c/d", "..\\x"]:
        with pytest.raises(StorageError):
            st.put(bad, b"x")
    assert not st.exists("local://../../etc/passwd")
    with pytest.raises(StorageError):
        st.get("local://../../etc/passwd")
