# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from base64 import b64decode

from frappe.tests import UnitTestCase

from connect_diagnostics_core.utils.qr import get_qr_svg_code


class TestQr(UnitTestCase):
    def test_returns_self_contained_svg_data_uri(self) -> None:
        result = get_qr_svg_code("AST-0001")

        prefix, payload = result.split(",", 1)
        self.assertEqual(prefix, "data:image/svg+xml;base64")
        self.assertIn(b"<svg", b64decode(payload))

    def test_empty_value_returns_empty_string(self) -> None:
        self.assertEqual(get_qr_svg_code(None), "")
