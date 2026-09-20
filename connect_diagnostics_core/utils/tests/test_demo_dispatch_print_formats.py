# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from frappe.tests import UnitTestCase

PRINT_FORMAT_ROOT = Path(__file__).parents[2] / "connect_diagnostics_print" / "print_format"
FEATURE_FORMATS = {
    "Material Request": "material_request/material_request.json",
    "Dispatch": "dispatch/dispatch.json",
    "Borrowed Asset Return Inspection": "borrowed_asset_return_inspection/borrowed_asset_return_inspection.json",
    "Demo Asset Label": "demo_asset_label/demo_asset_label.json",
}


def load_feature_formats() -> dict[str, dict[str, Any]]:
    return {
        name: json.loads((PRINT_FORMAT_ROOT / relative_path).read_text())
        for name, relative_path in FEATURE_FORMATS.items()
    }


class TestDemoDispatchPrintFormats(UnitTestCase):
    def test_formats_use_native_chrome_and_existing_print_audit(self) -> None:
        for expected_name, print_format in load_feature_formats().items():
            with self.subTest(name=expected_name):
                self.assertEqual(print_format["name"], expected_name)
                self.assertEqual(print_format["module"], "Connect Diagnostics Print")
                self.assertEqual(print_format["pdf_generator"], "chrome")
                self.assertIn("{{ register_print(doc) }}", print_format["html"])

    def test_material_request_print_uses_only_authorized_snapshot(self) -> None:
        html = load_feature_formats()["Material Request"]["html"]

        self.assertIn('print_actions.get("authorized", {})', html)
        self.assertNotIn('print_actions.get("submit", {})', html)
        self.assertNotIn('print_actions.get("checked", {})', html)
        self.assertIn("unit_cost_ex_vat", html)
        self.assertIn("allocated_asset", html)

    def test_dispatch_and_return_inspection_include_operational_evidence(self) -> None:
        formats = load_feature_formats()

        dispatch_html = formats["Dispatch"]["html"]
        self.assertIn("reference_doctype", dispatch_html)
        self.assertIn("receiver_signature", dispatch_html)
        inspection_html = formats["Borrowed Asset Return Inspection"]["html"]
        self.assertIn("doc.checks", inspection_html)
        self.assertIn("asset_id_photo", inspection_html)

    def test_demo_label_uses_server_generated_qr_rows(self) -> None:
        print_format = load_feature_formats()["Demo Asset Label"]
        html = print_format["html"]
        css = print_format["css"]

        self.assertIn("get_dispatch_label_rows(doc)", html)
        self.assertIn("get_qr_svg_code(row.identifier)", html)
        self.assertIn("page-width:100mm", css)
        self.assertIn("page-height:60mm", css)
        for side in ("top", "bottom", "left", "right"):
            self.assertIn(f"margin-{side}:0mm!important", css)
