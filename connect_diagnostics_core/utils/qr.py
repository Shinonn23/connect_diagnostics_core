# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Small, print-safe QR helper for app-owned labels."""

from __future__ import annotations

from base64 import b64encode
from io import BytesIO


def get_qr_svg_code(value: str | None) -> str:
    """Return a self-contained SVG data URI, or an empty string for no value."""
    if not value:
        return ""

    from pyqrcode import create as create_qr

    stream = BytesIO()
    try:
        create_qr(str(value)).svg(stream, scale=4, background="#fff", module_color="#111")
        payload = b64encode(stream.getvalue()).decode("ascii")
    finally:
        stream.close()
    return f"data:image/svg+xml;base64,{payload}"
