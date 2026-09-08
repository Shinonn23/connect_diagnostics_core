# Copyright (c) 2026, Siwat Sroisuwan and contributors

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import add_transit_return_controls, rename_demo_return_inspection


class TestTransitReturnControls(UnitTestCase):
    def test_new_fields_cover_employee_company_native_movements(self) -> None:
        self.assertIn(
            "borrow_warehouse",
            {field["fieldname"] for field in add_transit_return_controls.NEW_FIELDS["Employee"]},
        )
        self.assertIn(
            "borrow_in_transit_warehouse",
            {field["fieldname"] for field in add_transit_return_controls.NEW_FIELDS["Company"]},
        )
        self.assertIn(
            "return_dispatch_transfer",
            {field["fieldname"] for field in add_transit_return_controls.NEW_FIELDS["Quality Inspection"]},
        )

    def test_rename_is_deterministic(self) -> None:
        self.assertEqual(
            rename_demo_return_inspection.RENAMES[0][1:],
            ("Demo Return Inspection", "Borrowed Asset Return Inspection"),
        )
