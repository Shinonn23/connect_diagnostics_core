# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ..supplier import CustomSupplier, validate


class TestCustomSupplierAutonameUnit(FrappeTestCase):
    def _doc(self, *, dksh: str | None = None, cd: str | None = None) -> CustomSupplier:
        return cast(
            CustomSupplier,
            SimpleNamespace(
                custom_dksh_supplier_code=dksh,
                custom_cd_supplier_code=cd,
                flags=SimpleNamespace(),
            ),
        )

    def test_uses_dksh_code_as_name(self):
        doc = self._doc(dksh="DKSH-SUPP-001")
        CustomSupplier.autoname(doc)
        self.assertEqual(doc.name, "DKSH-SUPP-001")
        self.assertTrue(doc.flags.name_set)

    def test_uses_cd_code_when_dksh_absent(self):
        doc = self._doc(cd="CD-SUPP-001")
        CustomSupplier.autoname(doc)
        self.assertEqual(doc.name, "CD-SUPP-001")
        self.assertTrue(doc.flags.name_set)

    def test_dksh_wins_when_both_codes_present(self):
        doc = self._doc(dksh="DKSH-SUPP-001", cd="CD-SUPP-001")
        CustomSupplier.autoname(doc)
        self.assertEqual(doc.name, "DKSH-SUPP-001")

    def test_strips_whitespace_from_dksh_code(self):
        doc = self._doc(dksh="  DKSH-SUPP-001  ")
        CustomSupplier.autoname(doc)
        self.assertEqual(doc.name, "DKSH-SUPP-001")

    def test_strips_whitespace_from_cd_code(self):
        doc = self._doc(cd="  CD-SUPP-001  ")
        CustomSupplier.autoname(doc)
        self.assertEqual(doc.name, "CD-SUPP-001")

    def test_does_not_set_name_when_both_codes_absent(self):
        doc = self._doc()
        CustomSupplier.autoname(doc)
        self.assertFalse(hasattr(doc, "name"))
        self.assertFalse(hasattr(doc.flags, "name_set"))


class TestCustomSupplierValidateUnit(FrappeTestCase):
    def _doc(
        self, *, name: str = "SUPP-001", dksh: str | None = None, is_new: bool = False
    ) -> CustomSupplier:
        return cast(
            CustomSupplier,
            SimpleNamespace(
                name=name,
                custom_dksh_supplier_code=dksh,
                is_new=lambda: is_new,
            ),
        )

    def test_raises_when_name_is_empty(self):
        doc = self._doc(name="")
        with self.assertRaises(frappe.ValidationError):
            validate(doc, None)

    def test_renames_doc_when_dksh_code_differs_from_name(self):
        doc = self._doc(name="SUPP-001", dksh="DKSH-NEW")
        with patch("frappe.rename_doc") as mock_rename:
            validate(doc, None)
        mock_rename.assert_called_once_with("Supplier", "SUPP-001", "DKSH-NEW", force=True)
        self.assertEqual(doc.name, "DKSH-NEW")

    def test_skips_rename_when_dksh_code_matches_name(self):
        doc = self._doc(name="DKSH-001", dksh="DKSH-001")
        with patch("frappe.rename_doc") as mock_rename:
            validate(doc, None)
        mock_rename.assert_not_called()

    def test_skips_rename_when_dksh_code_absent(self):
        doc = self._doc(name="SUPP-001", dksh=None)
        with patch("frappe.rename_doc") as mock_rename:
            validate(doc, None)
        mock_rename.assert_not_called()

    def test_skips_rename_for_new_documents(self):
        doc = self._doc(name="SUPP-001", dksh="DKSH-NEW", is_new=True)
        with patch("frappe.rename_doc") as mock_rename:
            validate(doc, None)
        mock_rename.assert_not_called()


_DKSH_CODE = "_Test DKSH-SUPP-E2E-001"
_CD_CODE = "_Test CD-SUPP-E2E-001"
_DKSH_PRIO = "_Test DKSH-SUPP-E2E-PRIO"
_RENAME_CD = "_Test CD-SUPP-E2E-RENAME"
_RENAME_DKSH = "_Test DKSH-SUPP-E2E-RENAME"

_KNOWN_TEST_NAMES: list[tuple[str, str]] = [
    ("Supplier", _DKSH_CODE),
    ("Supplier", _CD_CODE),
    ("Supplier", _DKSH_PRIO),
    ("Supplier", _RENAME_CD),
    ("Supplier", _RENAME_DKSH),
]


class TestCustomSupplierNamingE2E(FrappeTestCase):
    """
    Verifies the complete naming flow:
      INSERT → CustomSupplier.autoname() fires via override_doctype_class
      SAVE   → validate() hook fires via doc_events, may call frappe.rename_doc
    """

    def setUp(self):
        self._to_delete: list[tuple[str, str]] = list(_KNOWN_TEST_NAMES)
        for doctype, name in self._to_delete:
            frappe.delete_doc(doctype, name, ignore_missing=True, force=True)
        frappe.db.commit()

    def tearDown(self):
        for doctype, name in self._to_delete:
            frappe.delete_doc(doctype, name, ignore_missing=True, force=True)
        frappe.db.commit()

    def _insert_supplier(self, **kwargs) -> frappe.Document:
        doc = frappe.get_doc(
            {
                "doctype": "Supplier",
                "supplier_name": "_Test Naming Supplier",
                "supplier_type": "Company",
                **kwargs,
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        return doc

    def test_new_supplier_named_by_dksh_code(self):
        doc = self._insert_supplier(custom_dksh_supplier_code=_DKSH_CODE)
        self.assertEqual(doc.name, _DKSH_CODE)
        self.assertTrue(frappe.db.exists("Supplier", _DKSH_CODE))

    def test_new_supplier_falls_back_to_cd_code_when_dksh_absent(self):
        doc = self._insert_supplier(custom_cd_supplier_code=_CD_CODE)
        self.assertEqual(doc.name, _CD_CODE)
        self.assertTrue(frappe.db.exists("Supplier", _CD_CODE))

    def test_dksh_code_wins_over_cd_code_on_insert(self):
        doc = self._insert_supplier(
            custom_dksh_supplier_code=_DKSH_PRIO,
            custom_cd_supplier_code="_Test CD-SUPP-E2E-PRIO-IGNORED",
        )
        self.assertEqual(doc.name, _DKSH_PRIO)
        self.assertFalse(frappe.db.exists("Supplier", "_Test CD-SUPP-E2E-PRIO-IGNORED"))

    def test_new_supplier_uses_naming_series_when_no_codes(self):
        doc = self._insert_supplier(
            supplier_name="_Test No Code Supplier",
            naming_series="PTN.YY.MM.####",
        )
        # pyrefly: ignore [bad-argument-type]
        self._to_delete.append(("Supplier", doc.name))
        # pyrefly: ignore [missing-attribute]
        self.assertFalse(doc.name.startswith("_Test"))
        # pyrefly: ignore [missing-attribute]
        self.assertTrue(doc.name.startswith("PTN."))

    def test_validate_hook_renames_supplier_when_dksh_code_set_after_creation(self):
        # Step 1: create with CD code — autoname uses it as the name
        doc = self._insert_supplier(custom_cd_supplier_code=_RENAME_CD)
        self.assertEqual(doc.name, _RENAME_CD)

        # Step 2: add DKSH code and save — validate hook fires and calls rename_doc
        # pyrefly: ignore [missing-attribute]
        doc.custom_dksh_supplier_code = _RENAME_DKSH
        doc.save(ignore_permissions=True)

        self.assertEqual(doc.name, _RENAME_DKSH)
        self.assertFalse(frappe.db.exists("Supplier", _RENAME_CD))
        self.assertTrue(frappe.db.exists("Supplier", _RENAME_DKSH))

    def test_validate_hook_does_not_rename_when_dksh_already_matches_name(self):
        doc = self._insert_supplier(custom_dksh_supplier_code=_DKSH_CODE)
        self.assertEqual(doc.name, _DKSH_CODE)

        # pyrefly: ignore [missing-attribute]
        doc.supplier_name = "_Test Updated Display Name"
        doc.save(ignore_permissions=True)

        self.assertEqual(doc.name, _DKSH_CODE)
        self.assertTrue(frappe.db.exists("Supplier", _DKSH_CODE))
