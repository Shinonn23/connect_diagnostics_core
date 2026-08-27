# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import employee

THAI_PAYROLL_FIELDS = {
    "thai_payroll_section": "Section Break",
    "social_security_eligible": "Check",
    "provident_fund_rate": "Percent",
}

NATIONAL_ID_FIELDS = {
    "national_id_section": "Section Break",
    "national_id": "Data",
    "national_id_display": "Data",
    "social_security_id": "Data",
}


class TestEmployeeCustomFields(UnitTestCase):
    def _employee_fields(self) -> list[dict]:
        return employee.CUSTOM_FIELDS["Employee"]

    def _field(self, fieldname: str) -> dict:
        for field in self._employee_fields():
            if field["fieldname"] == fieldname:
                return field
        self.fail(f"Employee custom field '{fieldname}' is not defined")

    def test_fieldnames_are_unique(self) -> None:
        fieldnames = [field["fieldname"] for field in self._employee_fields()]

        self.assertEqual(len(fieldnames), len(set(fieldnames)))

    def test_thai_payroll_fields_exist_with_expected_types(self) -> None:
        for fieldname, fieldtype in THAI_PAYROLL_FIELDS.items():
            with self.subTest(fieldname=fieldname):
                self.assertEqual(self._field(fieldname)["fieldtype"], fieldtype)

    def test_national_id_fields_exist_with_expected_types(self) -> None:
        for fieldname, fieldtype in NATIONAL_ID_FIELDS.items():
            with self.subTest(fieldname=fieldname):
                self.assertEqual(self._field(fieldname)["fieldtype"], fieldtype)

    def test_thai_payroll_insert_after_chain_is_contiguous(self) -> None:
        self.assertEqual(self._field("thai_payroll_section")["insert_after"], "payroll_cost_center")
        self.assertEqual(self._field("social_security_eligible")["insert_after"], "thai_payroll_section")
        self.assertEqual(self._field("provident_fund_rate")["insert_after"], "social_security_eligible")

    def test_national_id_insert_after_chain_is_contiguous(self) -> None:
        self.assertEqual(self._field("national_id_section")["insert_after"], "place_of_issue")
        self.assertEqual(self._field("national_id")["insert_after"], "national_id_section")
        self.assertEqual(self._field("national_id_display")["insert_after"], "national_id")
        self.assertEqual(self._field("social_security_id")["insert_after"], "national_id_display")

    def test_national_id_display_is_read_only(self) -> None:
        self.assertEqual(self._field("national_id_display").get("read_only"), 1)

    def test_provident_fund_rate_has_no_default(self) -> None:
        field = self._field("provident_fund_rate")

        self.assertNotIn("default", field)
        self.assertTrue(field.get("description"))

    def test_quotation_signature_is_a_signature_without_a_default(self) -> None:
        field = self._field("quotation_signature")

        self.assertEqual(field["fieldtype"], "Signature")
        self.assertNotIn("default", field)
        self.assertTrue(field.get("description"))

    def test_no_property_setter_makes_thai_payroll_fields_required(self) -> None:
        required = {
            fieldname
            for fieldname, prop, value, _ in employee.PROPERTY_SETTERS["Employee"]
            if prop == "reqd" and value == "1"
        }

        self.assertTrue(THAI_PAYROLL_FIELDS.keys().isdisjoint(required))
        self.assertTrue(NATIONAL_ID_FIELDS.keys().isdisjoint(required))

    def test_signature_field_is_configured_without_duplicating_the_standard_field(self) -> None:
        fieldnames = [field["fieldname"] for field in self._employee_fields()]
        signature_setters = [
            setter
            for setter in employee.PROPERTY_SETTERS["Employee"]
            if setter[0] == employee.SIGNATURE_FIELD
        ]

        self.assertNotIn(employee.SIGNATURE_FIELD, fieldnames)
        self.assertEqual(
            signature_setters,
            [(employee.SIGNATURE_FIELD, "label", "Employee Signature", "Data")],
        )


class TestEmployeeSignatureLayout(UnitTestCase):
    def _meta_with(self, fieldnames: list[str]) -> MagicMock:
        meta = MagicMock()
        meta.fields = [MagicMock(fieldname=fieldname) for fieldname in fieldnames]
        return meta

    def test_relocates_signature_after_approver_fields(self) -> None:
        current_order = [
            "default_shift",
            employee.SIGNATURE_FIELD,
            employee.SIGNATURE_ANCHOR,
            "company_details_section",
        ]

        reordered = employee._relocated_after_anchor(
            current_order,
            (employee.SIGNATURE_FIELD,),
            employee.SIGNATURE_ANCHOR,
        )

        self.assertEqual(
            reordered,
            [
                "default_shift",
                employee.SIGNATURE_ANCHOR,
                employee.SIGNATURE_FIELD,
                "company_details_section",
            ],
        )

    def test_relocation_is_idempotent(self) -> None:
        current_order = [
            "default_shift",
            employee.SIGNATURE_ANCHOR,
            employee.SIGNATURE_FIELD,
            "company_details_section",
        ]

        self.assertEqual(
            employee._relocated_after_anchor(
                current_order,
                (employee.SIGNATURE_FIELD,),
                employee.SIGNATURE_ANCHOR,
            ),
            current_order,
        )

    def test_skips_configuration_when_signature_or_anchor_is_missing(self) -> None:
        meta = self._meta_with(["default_shift", "company_details_section"])

        with (
            patch.object(employee.frappe, "get_meta", return_value=meta),
            patch.object(employee, "_set_field_order") as set_field_order,
        ):
            employee.ensure_configuration()

        set_field_order.assert_not_called()

    def test_persists_reordered_signature_field_order(self) -> None:
        meta = self._meta_with(
            [
                "default_shift",
                employee.SIGNATURE_FIELD,
                employee.SIGNATURE_ANCHOR,
                "company_details_section",
            ]
        )

        with (
            patch.object(employee.frappe, "get_meta", return_value=meta),
            patch.object(employee, "_set_field_order") as set_field_order,
        ):
            employee.ensure_configuration()

        set_field_order.assert_called_once_with(
            "Employee",
            [
                "default_shift",
                employee.SIGNATURE_ANCHOR,
                employee.SIGNATURE_FIELD,
                "company_details_section",
            ],
        )
