# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from connect_diagnostics_core import setup
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
NATIVE_DIMENSION_FIELDS = {
    "Journal Entry Account": ("territory",),
    "Sales Invoice": ("department",),
    "Purchase Invoice": ("department", "territory"),
    "Sales Invoice Item": ("department", "territory"),
    "Purchase Invoice Item": ("department", "territory"),
    "Sales Order Item": ("department", "territory"),
    "Sales Taxes and Charges": ("department", "territory"),
    "Purchase Taxes and Charges": ("department", "territory"),
}


class TestEnsureConfigurationGuard(UnitTestCase):
    def test_setup_modules_do_not_declare_native_dimension_custom_fields(self) -> None:
        self.assertEqual(sum(map(len, NATIVE_DIMENSION_FIELDS.values())), 14)
        for module in setup._MODULES:
            for doctype, fields in getattr(module, "CUSTOM_FIELDS", {}).items():
                with self.subTest(module=module.__name__, doctype=doctype):
                    self.assertFalse({field["fieldname"] for field in fields} & {"department", "territory"})

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

    def test_repeated_setup_preserves_each_existing_native_dimension_field(self) -> None:
        fieldnames = ("name", "fieldtype", "options", "allow_on_submit", "insert_after")

        def snapshot() -> dict[tuple[str, str], dict[str, object]]:
            result = {}
            for doctype, dimensions in NATIVE_DIMENSION_FIELDS.items():
                for dimension in dimensions:
                    rows = frappe.get_all(
                        "Custom Field",
                        filters={"dt": doctype, "fieldname": dimension},
                        fields=list(fieldnames),
                    )
                    self.assertEqual(len(rows), 1, f"{doctype}.{dimension} must have one native field")
                    self.assertEqual((rows[0].fieldtype, rows[0].options), ("Link", dimension.title()))
                    result[(doctype, dimension)] = dict(rows[0])
            return result

        before = snapshot()
        setup.apply_all()
        self.assertEqual(snapshot(), before)
        setup.apply_all()
        self.assertEqual(snapshot(), before)

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
