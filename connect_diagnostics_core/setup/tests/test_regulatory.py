# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Tests for code-managed Regulatory setup metadata."""

from __future__ import annotations

import json
from pathlib import Path

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import regulatory

REGULATORY_DOCTYPE_DIR = Path(__file__).parents[2] / "connect_diagnostics_regulatory" / "doctype"
EXPECTED_LAYOUT_FIELDS = {
    "medical_device_establishment_registration": {
        "establishment_section": "Section Break",
        "establishment_column": "Column Break",
        "validity_section": "Section Break",
        "ownership_section": "Section Break",
    },
    "medical_device_product_registration": {
        "registration_tab": "Tab Break",
        "identity_section": "Section Break",
        "identity_column": "Column Break",
        "classification_section": "Section Break",
        "parties_section": "Section Break",
        "validity_section": "Section Break",
        "lifecycle_section": "Section Break",
        "products_tab": "Tab Break",
    },
    "medical_device_registered_product": {
        "identity_section": "Section Break",
        "identity_column": "Column Break",
        "manufacturer_section": "Section Break",
        "pack_section": "Section Break",
        "effective_section": "Section Break",
    },
    "medical_device_registration_action": {
        "action_section": "Section Break",
        "action_column": "Column Break",
        "tracking_section": "Section Break",
        "result_section": "Section Break",
        "evidence_section": "Section Break",
    },
    "medical_device_regulatory_document": {
        "document_tab": "Tab Break",
        "identity_section": "Section Break",
        "validity_section": "Section Break",
        "verification_section": "Section Break",
        "remarks_section": "Section Break",
    },
    "medical_device_regulatory_override": {
        "transaction_section": "Section Break",
        "transaction_column": "Column Break",
        "decision_section": "Section Break",
        "approval_section": "Section Break",
        "remarks_section": "Section Break",
    },
    "medical_device_regulatory_alert_log": {
        "alert_section": "Section Break",
        "alert_column": "Column Break",
        "result_section": "Section Break",
    },
    "medical_device_regulatory_settings": {
        "general_tab": "Tab Break",
        "owner_section": "Section Break",
        "validation_tab": "Tab Break",
        "existing_stock_tab": "Tab Break",
        "alerts_tab": "Tab Break",
    },
    "regulatory_expiry_alert_rule": {
        "alert_rule_section": "Section Break",
        "recipient_section": "Section Break",
    },
}


class TestRegulatorySetup(UnitTestCase):
    def test_superseded_workflow_state_uses_a_supported_style(self) -> None:
        self.assertEqual(regulatory.WORKFLOW_STATES["Registration Superseded"], "Inverse")

    def test_regulatory_forms_have_complete_grouped_layouts(self) -> None:
        for doctype_dir, expected_fields in EXPECTED_LAYOUT_FIELDS.items():
            with self.subTest(doctype=doctype_dir):
                definition = json.loads(
                    (REGULATORY_DOCTYPE_DIR / doctype_dir / f"{doctype_dir}.json").read_text()
                )
                fields = {field["fieldname"]: field["fieldtype"] for field in definition["fields"]}
                field_order = definition["field_order"]

                self.assertEqual(len(field_order), len(set(field_order)))
                self.assertEqual(set(field_order), set(fields))
                for fieldname, fieldtype in expected_fields.items():
                    self.assertEqual(fields.get(fieldname), fieldtype)

    def test_regulatory_form_layout_preserves_business_fieldnames(self) -> None:
        for doctype_dir in EXPECTED_LAYOUT_FIELDS:
            with self.subTest(doctype=doctype_dir):
                definition = json.loads(
                    (REGULATORY_DOCTYPE_DIR / doctype_dir / f"{doctype_dir}.json").read_text()
                )
                layout_fields = {
                    field["fieldname"]
                    for field in definition["fields"]
                    if field["fieldtype"] in {"Tab Break", "Section Break", "Column Break"}
                }
                self.assertTrue(layout_fields)
                self.assertTrue(layout_fields.issubset(set(definition["field_order"])))
