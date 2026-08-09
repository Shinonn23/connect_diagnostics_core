# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date
from typing import cast
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import regulatory_transactions


class TestRegulatoryTransactionPolicy(UnitTestCase):
    def test_missing_mapping_uses_missing_registration_policy(self) -> None:
        messages = regulatory_transactions._evaluate_row(
            cast(Document, frappe._dict(doctype="Purchase Receipt")),
            cast(Document, frappe._dict(idx=1, item_code="CL1000")),
            None,
            date(2026, 8, 9),
            _settings(),
        )

        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0].startswith("Block:"), messages[0])

    def test_expired_outbound_stock_defaults_to_warning(self) -> None:
        messages = regulatory_transactions._evaluate_row(
            cast(Document, frappe._dict(doctype="Delivery Note")),
            cast(Document, frappe._dict(idx=1, item_code="CL1000")),
            {
                "registration": "REG-1",
                "newcode": "NEW-1",
                "official_status": "Active",
                "expiry_date": "2026-08-01",
            },
            date(2026, 8, 9),
            _settings(),
        )

        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0].startswith("Warning:"), messages[0])

    def test_snapshot_preserves_resolved_values_and_row_facts(self) -> None:
        doc = cast(
            Document,
            frappe._dict(
                doctype="Purchase Receipt",
                posting_date="2026-08-09",
                medical_device_regulatory_override="",
                items=[frappe._dict(item_code="CL1000", batch_no="B-1", serial_no="S-1", uom="Kit", qty=2)],
            ),
        )
        mapping = {
            "registration": "REG-1",
            "newcode": "NEW-1",
            "identifier": "CL1000",
            "physical_manufacturer": "Manufacturer A",
        }
        with (
            patch.object(regulatory_transactions, "_item_requires_registration", return_value=True),
            patch.object(regulatory_transactions.regulatory, "get_mapping_at_date", return_value=mapping),
            patch.object(regulatory_transactions, "_manufacturer_country", return_value="China"),
            patch.object(regulatory_transactions, "_batch_expiry", return_value="2027-01-01"),
        ):
            regulatory_transactions.capture_transaction_snapshot(doc)

        row = doc.get("items")[0]
        self.assertEqual(row.regulatory_registration, "REG-1")
        self.assertEqual(row.regulatory_newcode, "NEW-1")
        self.assertEqual(row.regulatory_batch_no, "B-1")
        self.assertEqual(row.regulatory_serial_no, "S-1")
        self.assertEqual(row.regulatory_product_expiry_date, "2027-01-01")
        self.assertEqual(row.regulatory_reporting_uom, "Kit")
        self.assertEqual(row.regulatory_reporting_qty, 2)


def _settings() -> dict[str, str]:
    return {
        "missing_registration_action": "Block",
        "expired_registration_action": "Block",
        "suspended_registration_action": "Block",
        "revoked_registration_action": "Block",
        "missing_newcode_action": "Block",
        "manufacturer_mismatch_action": "Warning",
        "expired_registration_existing_stock_policy": "Warning",
    }
