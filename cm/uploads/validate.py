"""Upload validation: allowlist by MAGIC BYTES (never the extension or declared mime), size cap, filename cleanup."""

from __future__ import annotations

import io
import os
import re
import struct
import unicodedata
import zlib
from dataclasses import dataclass

MAX_PDF_PAGES = 30
_TYPES = {"jpg": "image/jpeg", "png": "image/png", "pdf": "application/pdf", "txt": "text/plain"}
# Never acceptable as text, whatever follows: executables, archives, scripts, markup, images we do not take.
_DENY_PREFIXES = (
    b"MZ",
    b"\x7fELF",
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"#!",
    b"GIF8",
    b"%!PS",
    b"Rar!",
    b"7z\xbc\xaf",
    b"\x1f\x8b",
    b"\xca\xfe\xba\xbe",
    b"\xcf\xfa\xed\xfe",
    b"\xfe\xed\xfa",
    b"BM",
    b"RIFF",
    b"<",
)
_MARKUP = re.compile(rb"<\s*(script|svg|html|iframe|\?xml|!doctype|object|embed)", re.IGNORECASE)
_CTRL = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")
# Anywhere in an image or PDF body (polyglot tails); `<?xml` is left out because XMP metadata may carry it.
_MARKUP_ANY = re.compile(rb"<\s*(script|svg|html|iframe|!doctype|object|embed)[\s>/]", re.IGNORECASE)
# PDF active content: never needed by a lab slip or prescription, and run by some viewers on open.
# (/JS alone is skipped: three bytes match by chance in binary data; a JS action also carries /S /JavaScript)
_PDF_ACTIVE = re.compile(rb"/(JavaScript|Launch|EmbeddedFiles?|RichMedia)(?![A-Za-z])")
_PDF_NAME_ESC = re.compile(rb"#([0-9A-Fa-f]{2})")
_PDF_STREAM = re.compile(rb"stream\r?\n")
_PDF_STREAM_BODY = re.compile(rb"stream\r?\n.*?endstream", re.S)
# Flate bomb guard: one stream may inflate to 64 MB, the whole file to 512 MB (counted, never all held).
MAX_STREAM_INFLATED = 64 * 1024 * 1024
MAX_PDF_INFLATED = 512 * 1024 * 1024
_KEEP_INFLATED = 4 * 1024 * 1024  # streams up to this size are kept for the active-content scan
MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard (header only, nothing is decoded)


class UploadRejected(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code, self.detail = code, detail


@dataclass(frozen=True)
class Validated:
    ext: str  # jpg | png | pdf | txt (from the bytes)
    mime: str
    filename: str  # sanitised, extension rewritten to the real type
    size: int
    pages: int | None = None


def max_bytes() -> int:
    try:
        return int(float(os.environ.get("UPLOAD_MAX_MB", "10")) * 1024 * 1024)
    except ValueError:
        return 10 * 1024 * 1024


def sniff(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(_DENY_PREFIXES):
        return None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    return None if _CTRL.search(text) else "txt"


def _name_char(c: str) -> bool:
    # letters, digits and combining marks (Telugu vowel signs are category M), plus a few separators
    return c.isalnum() or c in "_ .-" or unicodedata.category(c) in ("Mn", "Mc")


def sanitise_filename(name: str | None, ext: str = "txt") -> str:
    """Base name only, no control or path characters, at most 80 chars, extension forced to the real type."""
    base = (name or "").replace("\\", "/").split("/")[-1]
    base = unicodedata.normalize("NFKC", base)
    stem = os.path.splitext(base)[0]
    stem = "".join(c for c in stem if _name_char(c))
    stem = re.sub(r"[\s_.-]{2,}", " ", stem).strip(" .-_")[:80]
    return f"{stem or 'document'}.{ext}"


def _pdf_pages(data: bytes) -> int | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise UploadRejected("bad_type", "encrypted pdf")
        return len(reader.pages)
    except UploadRejected:
        raise
    except Exception:  # noqa: BLE001  (damaged but openable files fall back to a rough count)
        return len(re.findall(rb"/Type\s*/Page(?![a-z])", data)) or None


def _pdf_streams(data: bytes) -> list[bytes]:
    """Inflate every Flate stream (bounded in total); raise on a decompression bomb."""
    out: list[bytes] = []
    total = 0
    for m in _PDF_STREAM.finditer(data):
        end = data.find(b"endstream", m.end())
        raw, d, size, kept = data[m.end() : end if end != -1 else len(data)], zlib.decompressobj(), 0, []
        try:
            while raw:
                chunk = d.decompress(raw, 1 << 20)
                raw = d.unconsumed_tail
                size += len(chunk)
                total += len(chunk)
                if size > MAX_STREAM_INFLATED or total > MAX_PDF_INFLATED:
                    raise UploadRejected("bad_type", "pdf expands too much")
                if size <= _KEEP_INFLATED:
                    kept.append(chunk)
                if not chunk:
                    break
        except zlib.error:
            continue  # not Flate (or damaged): nothing to inflate
        if size <= _KEEP_INFLATED:
            out.append(b"".join(kept))
    return out


def _pdf_active(data: bytes, streams: list[bytes]) -> bool:
    """JavaScript, launch actions or embedded files, also inside object streams and #-escaped names."""
    plain = _PDF_STREAM_BODY.sub(b"", data)  # raw (binary) stream bodies are checked inflated instead
    return any(
        _PDF_ACTIVE.search(_PDF_NAME_ESC.sub(lambda m: bytes([int(m.group(1), 16)]), blob))
        for blob in (plain, *streams)
    )


def _image_too_big(ext: str, data: bytes) -> bool:
    if ext == "png" and data[12:16] == b"IHDR" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return w * h > MAX_IMAGE_PIXELS
    if ext == "jpg":
        try:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as im:  # header only: no pixels are decoded
                w, h = im.size
        except ImportError:
            return False
        except Exception as exc:  # noqa: BLE001  (Pillow's own bomb error, or an unreadable header)
            return type(exc).__name__ == "DecompressionBombError"
        return w * h > MAX_IMAGE_PIXELS
    return False


def validate_upload(
    filename: str | None, data: bytes, declared_mime: str | None = None
) -> Validated:
    """Raise UploadRejected(code in too_large|bad_type) or return the facts about an acceptable file.

    ``declared_mime`` is ignored on purpose: only the bytes decide.
    """
    if not data:
        raise UploadRejected("bad_type", "empty file")
    if len(data) > max_bytes():
        raise UploadRejected("too_large", "file too large")
    ext = sniff(data)
    if ext is None:
        raise UploadRejected("bad_type", "file type not allowed")
    if ext != "txt" and _MARKUP.search(data[:1024]):
        raise UploadRejected("bad_type", "markup inside a binary file")
    if ext != "txt" and b"PK\x05\x06" in data[-70000:] and b"PK\x03\x04" in data:
        raise UploadRejected("bad_type", "archive hidden in file")
    if ext != "txt" and _MARKUP_ANY.search(data):
        raise UploadRejected("bad_type", "markup inside a binary file")
    if ext == "txt" and _MARKUP.search(data):
        raise UploadRejected("bad_type", "markup in text")
    if _image_too_big(ext, data):
        raise UploadRejected("bad_type", "image too large")
    if ext == "pdf" and _pdf_active(data, _pdf_streams(data)):
        raise UploadRejected("bad_type", "pdf with active content")
    pages = _pdf_pages(data) if ext == "pdf" else None
    if pages is not None and pages > MAX_PDF_PAGES:
        raise UploadRejected("bad_type", f"pdf has more than {MAX_PDF_PAGES} pages")
    return Validated(ext, _TYPES[ext], sanitise_filename(filename, ext), len(data), pages)
