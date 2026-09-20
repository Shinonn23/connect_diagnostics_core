# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import regulatory
from connect_diagnostics_core.connect_diagnostics_regulatory.doctype.medical_device_product_registration.medical_device_product_registration import (
    _ranges_overlap,
)


class TestRegulatoryResolver(UnitTestCase):
    def test_normalize_registration_number_keeps_legacy_letters_and_digits(self) -> None:
        self.assertEqual(regulatory.normalize_registration_number(" 68-2-2-1-0006254 "), "682210006254")
        self.assertEqual(regulatory.normalize_registration_number("ab / 01-c"), "AB01C")

    def test_resolves_single_effective_mapping(self) -> None:
        mapping = {
            "registration": "68-2-2-1-0006254",
            "newcode": "U1MN00010268-2-2-1-0006254000001C",
            "identifier": "CL1000",
            "physical_manufacturer": "EasyDiagnosis",
            "expiry_date": "2029-12-31",
            "official_status": "Active",
        }
        with patch.object(regulatory.frappe.db, "sql", return_value=[frappe._dict(mapping)]):
            self.assertEqual(regulatory.get_effective_mapping("CL1000", date(2026, 8, 9)), mapping)

    def test_rejects_ambiguous_effective_mapping(self) -> None:
        mappings = [frappe._dict({"registration": "REG-1"}), frappe._dict({"registration": "REG-2"})]
        with patch.object(regulatory.frappe.db, "sql", return_value=mappings):
            with self.assertRaises(frappe.ValidationError):
                regulatory.get_effective_mapping("CL1000", date(2026, 8, 9))

    def test_mapping_lookup_keeps_expired_rows_for_policy_evaluation(self) -> None:
        mapping = frappe._dict(
            {
                "registration": "REG-1",
                "newcode": "NEW-1",
                "expiry_date": "2026-08-01",
                "official_status": "Active",
            }
        )
        with patch.object(regulatory.frappe.db, "sql", return_value=[mapping]) as sql:
            self.assertEqual(regulatory.get_mapping_at_date("CL1000", date(2026, 8, 9)), mapping)

        self.assertNotIn("registration.expiry_date >=", sql.call_args.args[0])

    def test_item_dashboard_registration_connection_is_idempotent(self) -> None:
        dashboard: dict[str, object] = {}

        regulatory.inject_item_dashboard_connections(dashboard)
        regulatory.inject_item_dashboard_connections(dashboard)

        self.assertEqual(
            dashboard["non_standard_fieldnames"],
            {"Medical Device Product Registration": "current_medical_device_registration"},
        )
        self.assertEqual(
            dashboard["transactions"],
            [{"label": "Regulatory", "items": ["Medical Device Product Registration"]}],
        )

    def test_effective_date_ranges_are_inclusive_and_detect_overlap(self) -> None:
        self.assertTrue(
            _ranges_overlap(
                frappe._dict(effective_from="2026-01-01", effective_to="2026-06-30"),
                frappe._dict(effective_from="2026-06-30", effective_to="2026-12-31"),
            )
        )
        self.assertFalse(
            _ranges_overlap(
                frappe._dict(effective_from="2026-01-01", effective_to="2026-06-29"),
                frappe._dict(effective_from="2026-06-30", effective_to="2026-12-31"),
            )
        )
