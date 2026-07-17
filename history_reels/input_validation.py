"""Validation helpers for dashboard uploads and externally fetched URLs."""

from __future__ import annotations

import ipaddress
from io import BytesIO
import socket
import zipfile
from urllib.parse import urlparse


MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_XLSX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_XLSX_MEMBERS = 1_000


def validate_external_url(url: str) -> tuple[bool, str]:
    """Allow only public HTTP(S) URLs, blocking local/private network targets."""
    try:
        parsed = urlparse((url or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False, "Use a complete public http:// or https:// URL."
        if parsed.username or parsed.password:
            return False, "URLs containing embedded credentials are not allowed."
        if parsed.port not in {None, 80, 443}:
            return False, "Only standard HTTP/HTTPS ports are allowed."

        addresses = {entry[4][0] for entry in socket.getaddrinfo(parsed.hostname, None)}
        if not addresses:
            return False, "The URL hostname could not be resolved."
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                return False, "Local, private, or reserved network URLs are not allowed."
    except (OSError, ValueError):
        return False, "The URL is invalid or its hostname could not be resolved."
    return True, ""


def validate_uploaded_file(uploaded_file, expected_kind: str, max_bytes: int = MAX_UPLOAD_BYTES) -> tuple[bool, str]:
    """Validate size and a lightweight file signature before processing an upload."""
    if uploaded_file is None:
        return False, "No file was uploaded."
    size = getattr(uploaded_file, "size", 0)
    if not size or size > max_bytes:
        return False, f"File must be between 1 byte and {max_bytes // (1024 * 1024)} MB."

    buffer = uploaded_file.getbuffer()
    content = bytes(buffer[:16])
    signatures = {
        "xlsx": lambda data: data.startswith(b"PK\x03\x04"),
        "mp4": lambda data: len(data) >= 8 and data[4:8] == b"ftyp",
        "png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
        "font": lambda data: data.startswith((b"\x00\x01\x00\x00", b"OTTO", b"true")),
        "csv": lambda data: b"\x00" not in data,
    }
    validator = signatures.get(expected_kind)
    if validator is None or not validator(content):
        return False, f"The uploaded file does not look like a valid {expected_kind.upper()} file."
    if expected_kind == "xlsx":
        try:
            with zipfile.ZipFile(BytesIO(bytes(buffer))) as workbook:
                members = workbook.infolist()
                names = {member.filename for member in members}
                total_size = sum(member.file_size for member in members)
                if len(members) > MAX_XLSX_MEMBERS or total_size > MAX_XLSX_UNCOMPRESSED_BYTES:
                    return False, "The XLSX expands beyond the safe workbook size limit."
                if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                    return False, "The uploaded ZIP is not a valid XLSX workbook."
        except (OSError, zipfile.BadZipFile):
            return False, "The XLSX archive is damaged or invalid."
    return True, ""
