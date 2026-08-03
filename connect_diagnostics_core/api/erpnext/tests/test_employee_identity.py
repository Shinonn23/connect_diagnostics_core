# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from connect_diagnostics_core.api.erpnext import employee
from connect_diagnostics_core.setup import employee as employee_setup


def _valid_identity(prefix: str = "110170020345") -> str:
    checksum_total = sum(int(digit) * (13 - index) for index, digit in enumerate(prefix))
    return f"{prefix}{(11 - (checksum_total % 11)) % 10}"


def _employee_doc(
    values: dict[str, str],
    *,
    changed_fields: tuple[str, ...] = (),
    previous_values: dict[str, str] | None = None,
) -> MagicMock:
    doc = MagicMock()
    doc.name = "EMP-001"
    doc.flags = frappe._dict()
    doc.get.side_effect = values.get
    doc.set.side_effect = values.__setitem__
    doc.has_value_changed.side_effect = lambda fieldname: fieldname in changed_fields
    doc.get_doc_before_save.return_value = (
        frappe._dict(previous_values) if previous_values is not None else None
    )
    return doc


class TestEmployeeIdentity(UnitTestCase):
    def test_normalize_removes_hyphens_and_whitespace(self) -> None:
        identity = _valid_identity()
        formatted = f"{identity[0]}-{identity[1:5]} {identity[5:10]}-{identity[10:12]}-{identity[12]}"

        self.assertEqual(employee.normalize_thai_identity_number(formatted), identity)

    def test_normalize_canonicalizes_unicode_decimal_digits(self) -> None:
        identity = _valid_identity()
        thai_digits = "".join(chr(0x0E50 + int(digit)) for digit in identity)
        full_width_digits = "".join(chr(0xFF10 + int(digit)) for digit in identity)

        self.assertEqual(employee.normalize_thai_identity_number(thai_digits), identity)
        self.assertEqual(employee.normalize_thai_identity_number(full_width_digits), identity)
        self.assertTrue(employee.is_valid_thai_identity_number(thai_digits))

    def test_checksum_validation(self) -> None:
        identity = _valid_identity()

        self.assertTrue(employee.is_valid_thai_identity_number(identity))
        self.assertFalse(
            employee.is_valid_thai_identity_number(f"{identity[:12]}{(int(identity[-1]) + 1) % 10}")
        )
        self.assertFalse(employee.is_valid_thai_identity_number("123"))

    @patch.object(employee.frappe, "has_permission", return_value=True)
    @patch.object(employee.frappe.db, "exists", return_value=False)
    def test_hook_normalizes_both_fields(
        self,
        _mocked_exists: MagicMock,
        mocked_permission: MagicMock,
    ) -> None:
        national_id = _valid_identity("110170020345")
        tax_id = _valid_identity("310060012345")
        values = {
            "national_id": f"{national_id[:4]}-{national_id[4:]}",
            "tax_id": f" {tax_id[:6]} {tax_id[6:]} ",
        }
        doc = _employee_doc(values, changed_fields=("national_id",))

        employee.validate_employee_identity(doc, "validate")

        self.assertEqual(values, {"national_id": national_id, "tax_id": tax_id})
        self.assertTrue(doc.flags.ignore_version)
        mocked_permission.assert_called_once_with("Employee", "mask", doc=doc)

    @patch.object(employee.frappe, "has_permission", return_value=False)
    @patch.object(employee.frappe.db, "exists", return_value=False)
    def test_unchanged_identity_keeps_normal_version_tracking(
        self,
        _mocked_exists: MagicMock,
        mocked_permission: MagicMock,
    ) -> None:
        values = {"national_id": _valid_identity(), "tax_id": ""}
        doc = _employee_doc(values)

        employee.validate_employee_identity(doc, "validate")

        self.assertNotIn("ignore_version", doc.flags)
        mocked_permission.assert_not_called()

    @patch.object(employee.frappe.db, "exists", return_value=False)
    def test_empty_identity_fields_remain_independent(self, mocked_exists: MagicMock) -> None:
        values = {"national_id": "", "tax_id": ""}
        doc = _employee_doc(values)

        employee.validate_employee_identity(doc, "validate")

        self.assertIsNone(values["national_id"])
        self.assertIsNone(values["tax_id"])
        mocked_exists.assert_not_called()

    @patch.object(employee.frappe, "has_permission", return_value=False)
    @patch.object(employee.frappe.db, "exists")
    def test_setting_identity_requires_mask_permission(
        self,
        mocked_exists: MagicMock,
        _mocked_permission: MagicMock,
    ) -> None:
        values = {"national_id": _valid_identity(), "tax_id": ""}
        doc = _employee_doc(values, changed_fields=("national_id",))

        with self.assertRaises(frappe.PermissionError):
            employee.validate_employee_identity(doc, "validate")

        mocked_exists.assert_not_called()

    @patch.object(employee.frappe, "has_permission", return_value=False)
    def test_clearing_identity_requires_mask_permission(self, _mocked_permission: MagicMock) -> None:
        values = {"national_id": "", "tax_id": ""}
        doc = _employee_doc(
            values,
            changed_fields=("national_id",),
            previous_values={"national_id": _valid_identity(), "tax_id": ""},
        )

        with self.assertRaises(frappe.PermissionError):
            employee.validate_employee_identity(doc, "validate")

    @patch.object(employee.frappe, "has_permission", return_value=True)
    @patch.object(employee.frappe.db, "exists", return_value=False)
    def test_invalid_format_is_rejected_without_echoing_value(
        self,
        _mocked_exists: MagicMock,
        _mocked_permission: MagicMock,
    ) -> None:
        values = {"national_id": "123", "tax_id": ""}
        doc = _employee_doc(values, changed_fields=("national_id",))

        with self.assertRaises(frappe.ValidationError) as error:
            employee.validate_employee_identity(doc, "validate")

        self.assertNotIn("123", str(error.exception))

    @patch.object(employee.frappe, "has_permission", return_value=True)
    @patch.object(employee.frappe.db, "exists", return_value="EMP-002")
    def test_duplicate_identity_is_rejected(
        self,
        _mocked_exists: MagicMock,
        _mocked_permission: MagicMock,
    ) -> None:
        values = {"national_id": _valid_identity(), "tax_id": ""}
        doc = _employee_doc(values, changed_fields=("national_id",))

        with self.assertRaises(frappe.ValidationError):
            employee.validate_employee_identity(doc, "validate")

    def test_identity_fields_are_masked_unique_and_no_copy(self) -> None:
        fields = {field["fieldname"]: field for field in employee_setup.CUSTOM_FIELDS["Employee"]}

        for fieldname in ("national_id", "tax_id"):
            with self.subTest(fieldname=fieldname):
                self.assertEqual(fields[fieldname]["fieldtype"], "Data")
                self.assertEqual(fields[fieldname]["mask"], 1)
                self.assertEqual(fields[fieldname]["no_copy"], 1)
                self.assertEqual(fields[fieldname]["unique"], 1)

    @patch.object(employee_setup.frappe, "get_doc")
    @patch.object(employee_setup.frappe, "get_all", return_value=["HR-MANAGER-PERM"])
    @patch.object(employee_setup, "setup_custom_perms")
    def test_hr_manager_receives_mask_permission(
        self,
        mocked_setup_custom_perms: MagicMock,
        mocked_get_all: MagicMock,
        mocked_get_doc: MagicMock,
    ) -> None:
        permission = MagicMock()
        permission.get.return_value = 0
        mocked_get_doc.return_value = permission

        employee_setup.ensure_employee_mask_permission()

        mocked_setup_custom_perms.assert_called_once_with("Employee")
        mocked_get_all.assert_called_once_with(
            "Custom DocPerm",
            filters={
                "parent": "Employee",
                "role": "HR Manager",
                "permlevel": 0,
                "if_owner": 0,
            },
            pluck="name",
        )
        permission.set.assert_called_once_with("mask", 1)
        permission.save.assert_called_once_with(ignore_permissions=True)


class TestEmployeeIdentityPersistence(IntegrationTestCase):
    def test_identity_save_omits_version_while_unrelated_save_is_audited(self) -> None:
        company = "_Test Company"
        if not frappe.db.exists("Company", company):
            company = frappe.get_all("Company", pluck="name", limit=1)[0]
        gender = frappe.get_all("Gender", pluck="name", limit=1)[0]
        employment_type = frappe.get_all("Employment Type", pluck="name", limit=1)[0]
        identity = _valid_identity("999999999999")
        self.assertFalse(frappe.db.exists("Employee", {"national_id": identity}))

        employee_doc = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": "Identity Version Test",
                "company": company,
                "status": "Active",
                "gender": gender,
                "employment_type": employment_type,
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2026-01-01",
            }
        ).insert(ignore_permissions=True)

        employee_doc.national_id = identity
        employee_doc.save(ignore_permissions=True, ignore_version=False)
        identity_versions = frappe.get_all(
            "Version",
            filters={"ref_doctype": "Employee", "docname": employee_doc.name},
            pluck="data",
        )
        self.assertEqual(identity_versions, [])

        employee_doc.middle_name = "Normal audit change"
        employee_doc.save(ignore_permissions=True, ignore_version=False)
        normal_versions = frappe.get_all(
            "Version",
            filters={"ref_doctype": "Employee", "docname": employee_doc.name},
            pluck="data",
        )
        self.assertEqual(len(normal_versions), 1)
        self.assertIn("Normal audit change", normal_versions[0])
        self.assertNotIn(identity, normal_versions[0])
