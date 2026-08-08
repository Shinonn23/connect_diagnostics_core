# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.connect_diagnostics_dksh import reference


class FakeDoc:
    """Minimal stand-in for a reference-master Document."""

    def __init__(self, doctype: str, name: str, values: dict[str, Any]) -> None:
        self.doctype = doctype
        self.name = name
        self._values = dict(values)

    def get(self, fieldname: str) -> Any:
        return self._values.get(fieldname)

    def set(self, fieldname: str, value: Any) -> None:
        self._values[fieldname] = value


class TestValidateReference(UnitTestCase):
    def test_trims_every_code_field(self) -> None:
        doc = FakeDoc(
            "DKSH Item",
            "  A  ",
            {"dksh_item_code": "  A  ", "supplier_product_code": " B ", "item": None},
        )

        reference.validate_reference(
            doc,  # ty: ignore[invalid-argument-type] - test double
            code_fields=("dksh_item_code", "supplier_product_code"),
            link_field="item",
            master_doctype="Item",
        )

        self.assertEqual(doc.get("dksh_item_code"), "A")
        self.assertEqual(doc.get("supplier_product_code"), "B")

    def test_no_duplicate_lookup_when_link_is_blank(self) -> None:
        doc = FakeDoc("DKSH Item", "A", {"dksh_item_code": "A", "item": None})

        with patch.object(reference.frappe.db, "get_value") as get_value:
            reference.validate_reference(
                doc,  # ty: ignore[invalid-argument-type] - test double
                code_fields=("dksh_item_code",),
                link_field="item",
                master_doctype="Item",
            )

        get_value.assert_not_called()

    def test_rejects_a_second_reference_to_the_same_master(self) -> None:
        doc = FakeDoc("DKSH Item", "B", {"dksh_item_code": "B", "item": "_Test Item"})

        with patch.object(reference.frappe.db, "get_value", return_value="A"):
            with self.assertRaises(frappe.ValidationError):
                reference.validate_reference(
                    doc,  # ty: ignore[invalid-argument-type] - test double
                    code_fields=("dksh_item_code",),
                    link_field="item",
                    master_doctype="Item",
                )

    def test_allows_when_no_other_reference_holds_the_master(self) -> None:
        doc = FakeDoc("DKSH Item", "B", {"dksh_item_code": "B", "item": "_Test Item"})

        with patch.object(reference.frappe.db, "get_value", return_value=None) as get_value:
            reference.validate_reference(
                doc,  # ty: ignore[invalid-argument-type] - test double
                code_fields=("dksh_item_code",),
                link_field="item",
                master_doctype="Item",
            )

        get_value.assert_called_once_with(
            "DKSH Item",
            {"item": "_Test Item", "name": ["!=", "B"]},
            "name",
        )


class TestInjectConnection(UnitTestCase):
    def test_registers_the_link_field_and_creates_the_group(self) -> None:
        data: dict[str, Any] = {}

        result = reference.inject_connection(
            data,
            reference_doctype="DKSH Item",
            link_field="item",
            group_label="Reference",
        )

        self.assertEqual(result["non_standard_fieldnames"], {"DKSH Item": "item"})
        self.assertEqual(result["transactions"], [{"label": "Reference", "items": ["DKSH Item"]}])

    def test_appends_to_an_existing_group_without_duplicating(self) -> None:
        data: dict[str, Any] = {"transactions": [{"label": "Reference", "items": ["Other"]}]}

        reference.inject_connection(
            data,
            reference_doctype="DKSH Item",
            link_field="item",
            group_label="Reference",
        )
        reference.inject_connection(
            data,
            reference_doctype="DKSH Item",
            link_field="item",
            group_label="Reference",
        )

        self.assertEqual(data["transactions"], [{"label": "Reference", "items": ["Other", "DKSH Item"]}])
