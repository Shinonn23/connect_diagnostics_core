# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from connect_diagnostics_core.setup import accounting_dimension

# Doctypes that already carry a hand-rolled or native `department`/`territory`
# field; registering a dimension must reuse these, never duplicate or repoint them.
PREEXISTING_DEPARTMENT_FIELD_DOCTYPES = (
    "Sales Invoice",
    "Sales Invoice Item",
    "Purchase Invoice",
    "Purchase Invoice Item",
)
PREEXISTING_TERRITORY_FIELD_DOCTYPES = (
    "Sales Invoice",  # native ERPNext field
    "Sales Invoice Item",
    "Purchase Invoice",
    "Journal Entry Account",
)


class TestEnsureConfigurationGuard(UnitTestCase):
    def test_skips_creation_when_every_dimension_already_exists(self) -> None:
        with (
            patch.object(accounting_dimension.frappe.db, "exists", return_value=True),
            patch.object(accounting_dimension.frappe, "get_doc") as get_doc,
        ):
            accounting_dimension.ensure_configuration()
        get_doc.assert_not_called()

    def test_inserts_every_missing_dimension(self) -> None:
        created = MagicMock()
        with (
            patch.object(accounting_dimension.frappe.db, "exists", return_value=False),
            patch.object(accounting_dimension.frappe, "get_doc", return_value=created) as get_doc,
        ):
            accounting_dimension.ensure_configuration()
        self.assertEqual(
            [call.args[0] for call in get_doc.call_args_list],
            [
                {
                    "doctype": "Accounting Dimension",
                    "document_type": "Department",
                    "fieldname": "department",
                    "label": "Department",
                },
                {
                    "doctype": "Accounting Dimension",
                    "document_type": "Territory",
                    "fieldname": "territory",
                    "label": "Territory",
                },
            ],
        )
        self.assertEqual(created.insert.call_count, 2)
        created.insert.assert_called_with(ignore_permissions=True)

    def test_only_missing_dimensions_are_created(self) -> None:
        def exists(_doctype: str, filters: dict[str, str]) -> bool:
            return filters["document_type"] == "Department"

        created = MagicMock()
        with (
            patch.object(accounting_dimension.frappe.db, "exists", side_effect=exists),
            patch.object(accounting_dimension.frappe, "get_doc", return_value=created) as get_doc,
        ):
            accounting_dimension.ensure_configuration()
        self.assertEqual(
            [call.args[0]["document_type"] for call in get_doc.call_args_list],
            ["Territory"],
        )


class TestRegisteredDimensions(IntegrationTestCase):
    """Verifies the registered dimensions against the migrated site state."""

    def setUp(self) -> None:
        super().setUp()
        accounting_dimension.ensure_configuration()

    def _require(self, document_type: str) -> None:
        if not frappe.db.exists("Accounting Dimension", {"document_type": document_type}):
            self.skipTest(f"{document_type} dimension is not registered on this site")

    def test_department_dimension_uses_the_department_fieldname(self) -> None:
        self._require("Department")
        fieldname = cast(
            str,
            frappe.db.get_value("Accounting Dimension", {"document_type": "Department"}, "fieldname"),
        )
        self.assertEqual(fieldname, "department")

    def test_territory_dimension_uses_the_territory_fieldname(self) -> None:
        self._require("Territory")
        fieldname = cast(
            str,
            frappe.db.get_value("Accounting Dimension", {"document_type": "Territory"}, "fieldname"),
        )
        self.assertEqual(fieldname, "territory")

    def test_registration_is_idempotent(self) -> None:
        accounting_dimension.ensure_configuration()
        for document_type in ("Department", "Territory"):
            with self.subTest(document_type=document_type):
                self._require(document_type)
                count = frappe.db.count("Accounting Dimension", {"document_type": document_type})
                self.assertEqual(count, 1)

    def test_preexisting_department_fields_are_not_duplicated(self) -> None:
        self._require("Department")
        for doctype in PREEXISTING_DEPARTMENT_FIELD_DOCTYPES:
            with self.subTest(doctype=doctype):
                options = frappe.get_all(
                    "Custom Field",
                    filters={"dt": doctype, "fieldname": "department"},
                    pluck="options",
                )
                self.assertEqual(options, ["Department"])

    def test_preexisting_territory_fields_are_not_duplicated(self) -> None:
        self._require("Territory")
        for doctype in PREEXISTING_TERRITORY_FIELD_DOCTYPES:
            with self.subTest(doctype=doctype):
                custom = frappe.get_all(
                    "Custom Field",
                    filters={"dt": doctype, "fieldname": "territory"},
                    pluck="name",
                )
                # At most one custom field; Sales Invoice's is native (zero custom rows).
                self.assertLessEqual(len(custom), 1)
