# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ..customer import CustomCustomer, validate


class TestCustomCustomerAutonameUnit(FrappeTestCase):
    def _doc(self, *, dksh: str | None = None, cd: str | None = None) -> CustomCustomer:
        return cast(
            CustomCustomer,
            SimpleNamespace(
                custom_dksh_customer_code=dksh,
                custom_cd_customer_code=cd,
                flags=SimpleNamespace(),
            ),
        )

    def test_uses_dksh_code_as_name(self):
        doc = self._doc(dksh="DKSH-001")
        CustomCustomer.autoname(doc)
        self.assertEqual(doc.name, "DKSH-001")
        self.assertTrue(doc.flags.name_set)

    def test_uses_cd_code_when_dksh_absent(self):
        doc = self._doc(cd="CD-001")
        CustomCustomer.autoname(doc)
        self.assertEqual(doc.name, "CD-001")
        self.assertTrue(doc.flags.name_set)

    def test_dksh_wins_when_both_codes_present(self):
        doc = self._doc(dksh="DKSH-001", cd="CD-001")
        CustomCustomer.autoname(doc)
        self.assertEqual(doc.name, "DKSH-001")

    def test_strips_whitespace_from_dksh_code(self):
        doc = self._doc(dksh="  DKSH-001  ")
        CustomCustomer.autoname(doc)
        self.assertEqual(doc.name, "DKSH-001")

    def test_strips_whitespace_from_cd_code(self):
        doc = self._doc(cd="  CD-001  ")
        CustomCustomer.autoname(doc)
        self.assertEqual(doc.name, "CD-001")

    def test_does_not_set_name_when_both_codes_absent(self):
        doc = self._doc()
        CustomCustomer.autoname(doc)
        self.assertFalse(hasattr(doc, "name"))
        self.assertFalse(hasattr(doc.flags, "name_set"))


class TestCustomCustomerValidateUnit(FrappeTestCase):
    def _doc(
        self, *, name: str = "CUST-001", dksh: str | None = None, is_new: bool = False
    ) -> CustomCustomer:
        return cast(
            CustomCustomer,
            SimpleNamespace(
                name=name,
                custom_dksh_customer_code=dksh,
                is_new=lambda: is_new,
            ),
        )

    def test_raises_when_name_is_empty(self):
        doc = self._doc(name="")
        with self.assertRaises(frappe.ValidationError):
            validate(doc, None)

    def test_renames_doc_when_dksh_code_differs_from_name(self):
        doc = self._doc(name="CUST-001", dksh="DKSH-NEW")
        with patch("frappe.rename_doc") as mock_rename:
            validate(doc, None)
        mock_rename.assert_called_once_with("Customer", "CUST-001", "DKSH-NEW", force=True)
        self.assertEqual(doc.name, "DKSH-NEW")

    def test_skips_rename_when_dksh_code_matches_name(self):
        doc = self._doc(name="DKSH-001", dksh="DKSH-001")
        with patch("frappe.rename_doc") as mock_rename:
            validate(doc, None)
        mock_rename.assert_not_called()

    def test_skips_rename_when_dksh_code_absent(self):
        doc = self._doc(name="CUST-001", dksh=None)
        with patch("frappe.rename_doc") as mock_rename:
            validate(doc, None)
        mock_rename.assert_not_called()

    def test_skips_rename_for_new_documents(self):
        doc = self._doc(name="CUST-001", dksh="DKSH-NEW", is_new=True)
        with patch("frappe.rename_doc") as mock_rename:
            validate(doc, None)
        mock_rename.assert_not_called()


_DKSH_CODE = "_Test DKSH-CUST-E2E-001"
_CD_CODE = "_Test CD-CUST-E2E-001"
_DKSH_PRIO = "_Test DKSH-CUST-E2E-PRIO"
_RENAME_CD = "_Test CD-CUST-E2E-RENAME"
_RENAME_DKSH = "_Test DKSH-CUST-E2E-RENAME"

_KNOWN_TEST_NAMES: list[tuple[str, str]] = [
    ("Customer", _DKSH_CODE),
    ("Customer", _CD_CODE),
    ("Customer", _DKSH_PRIO),
    ("Customer", _RENAME_CD),
    ("Customer", _RENAME_DKSH),
]


def _ensure_non_group_customer_group() -> str:
    existing: str | None = cast(str | None, frappe.db.get_value("Customer Group", {"is_group": 0}, "name"))
    if existing:
        return existing
    group = frappe.get_doc(
        {
            "doctype": "Customer Group",
            "customer_group_name": "_Test Non-Group Customer Group",
            "is_group": 0,
            "parent_customer_group": "All Customer Groups",
        }
    )
    group.insert(ignore_permissions=True)
    return cast(str, group.name)


class TestCustomCustomerNamingE2E(FrappeTestCase):
    """
    Verifies the complete naming flow:
      INSERT → CustomCustomer.autoname() fires via override_doctype_class
      SAVE   → validate() hook fires via doc_events, may call frappe.rename_doc
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.customer_group = _ensure_non_group_customer_group()

    def setUp(self):
        self._to_delete: list[tuple[str, str]] = list(_KNOWN_TEST_NAMES)
        for doctype, name in self._to_delete:
            frappe.delete_doc(doctype, name, ignore_missing=True, force=True)
        frappe.db.commit()

    def tearDown(self):
        for doctype, name in self._to_delete:
            frappe.delete_doc(doctype, name, ignore_missing=True, force=True)
        frappe.db.commit()

    def _insert_customer(self, **kwargs) -> frappe.Document:
        doc = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": "_Test Naming Customer",
                "customer_type": "Company",
                "customer_group": self.customer_group,
                **kwargs,
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        return doc

    def test_new_customer_named_by_dksh_code(self):
        doc = self._insert_customer(custom_dksh_customer_code=_DKSH_CODE)
        self.assertEqual(doc.name, _DKSH_CODE)
        self.assertTrue(frappe.db.exists("Customer", _DKSH_CODE))

    def test_new_customer_falls_back_to_cd_code_when_dksh_absent(self):
        doc = self._insert_customer(custom_cd_customer_code=_CD_CODE)
        self.assertEqual(doc.name, _CD_CODE)
        self.assertTrue(frappe.db.exists("Customer", _CD_CODE))

    def test_dksh_code_wins_over_cd_code_on_insert(self):
        doc = self._insert_customer(
            custom_dksh_customer_code=_DKSH_PRIO,
            custom_cd_customer_code="_Test CD-CUST-E2E-PRIO-IGNORED",
        )
        self.assertEqual(doc.name, _DKSH_PRIO)
        self.assertFalse(frappe.db.exists("Customer", "_Test CD-CUST-E2E-PRIO-IGNORED"))

    def test_new_customer_uses_naming_series_when_no_codes(self):
        doc = self._insert_customer(
            customer_name="_Test No Code Customer",
            naming_series="PTN.YY.MM.####",
        )
        self._to_delete.append(("Customer", doc.name))  # ty:ignore[invalid-argument-type]
        # Name must come from the series, not from any constant code value
        self.assertFalse(doc.name.startswith("_Test"))  # ty:ignore[unresolved-attribute]
        # Frappe collapses the `.` separators in naming_series → "PTN" prefix
        self.assertTrue(doc.name.startswith("PTN"))  # ty:ignore[unresolved-attribute]

    # --- validate hook (via doc_events) ---

    def test_validate_hook_renames_customer_when_dksh_code_set_after_creation(self):
        # Step 1: create with CD code — autoname uses it as the name
        doc = self._insert_customer(custom_cd_customer_code=_RENAME_CD)
        self.assertEqual(doc.name, _RENAME_CD)

        # Step 2: add DKSH code and save — validate hook fires and calls rename_doc
        doc.custom_dksh_customer_code = _RENAME_DKSH  # ty:ignore[unresolved-attribute]
        doc.save(ignore_permissions=True)

        self.assertEqual(doc.name, _RENAME_DKSH)
        self.assertFalse(frappe.db.exists("Customer", _RENAME_CD))
        self.assertTrue(frappe.db.exists("Customer", _RENAME_DKSH))

    def test_validate_hook_does_not_rename_when_dksh_already_matches_name(self):
        # Customer already named by DKSH code — save again should be a no-op on name
        doc = self._insert_customer(custom_dksh_customer_code=_DKSH_CODE)
        self.assertEqual(doc.name, _DKSH_CODE)

        doc.customer_name = "_Test Updated Display Name"  # ty:ignore[unresolved-attribute]
        doc.save(ignore_permissions=True)

        self.assertEqual(doc.name, _DKSH_CODE)
        self.assertTrue(frappe.db.exists("Customer", _DKSH_CODE))
