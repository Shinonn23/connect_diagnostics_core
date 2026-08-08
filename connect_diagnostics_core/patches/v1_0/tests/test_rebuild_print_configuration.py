# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import (
    rebuild_print_configuration,
    rollback_rebuild_print_configuration,
)
from connect_diagnostics_core.setup import print_documents
from connect_diagnostics_core.setup.print_configuration_template import seed_registry_rows


class FakeParent:
    """Minimal stand-in for a Document with two child tables."""

    def __init__(self, rows: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "print_documents": [],
            "print_copies": [],
        }
        for fieldname, values in (rows or {}).items():
            self.tables[fieldname] = list(values)

    def get(self, fieldname: str) -> list[Any]:
        return [_Row(row) for row in self.tables.get(fieldname, [])]

    def append(self, fieldname: str, values: dict[str, Any]) -> None:
        self.tables.setdefault(fieldname, []).append(values)


class _Row:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)


class TestSeedRegistryRows(UnitTestCase):
    def test_seeding_an_empty_parent_adds_every_document_and_copy(self) -> None:
        parent = FakeParent()

        added = seed_registry_rows(parent)  # ty: ignore[invalid-argument-type] - test double

        self.assertTrue(added)
        self.assertEqual(
            [row["document_key"] for row in parent.tables["print_documents"]],
            [document.key for document in print_documents.PRINT_DOCUMENTS],
        )
        expected_copies = sum(len(document.copies) for document in print_documents.PRINT_DOCUMENTS)
        self.assertEqual(len(parent.tables["print_copies"]), expected_copies)

    def test_seeding_is_idempotent(self) -> None:
        parent = FakeParent()
        seed_registry_rows(parent)  # ty: ignore[invalid-argument-type] - test double
        documents = len(parent.tables["print_documents"])
        copies = len(parent.tables["print_copies"])

        added = seed_registry_rows(parent)  # ty: ignore[invalid-argument-type] - test double

        self.assertFalse(added)
        self.assertEqual(len(parent.tables["print_documents"]), documents)
        self.assertEqual(len(parent.tables["print_copies"]), copies)

    def test_seeding_preserves_values_a_user_already_edited(self) -> None:
        parent = FakeParent(
            {
                "print_documents": [{"document_key": "tax_invoice", "enabled": 0, "show_date": 0}],
                "print_copies": [
                    {"document_key": "tax_invoice", "copy_key": "original", "count": 5},
                ],
            }
        )

        seed_registry_rows(parent)  # ty: ignore[invalid-argument-type] - test double

        tax_invoice = [
            row for row in parent.tables["print_documents"] if row["document_key"] == "tax_invoice"
        ]
        self.assertEqual(len(tax_invoice), 1)
        self.assertEqual(tax_invoice[0]["enabled"], 0)
        original = [
            row
            for row in parent.tables["print_copies"]
            if row["document_key"] == "tax_invoice" and row["copy_key"] == "original"
        ]
        self.assertEqual(len(original), 1)
        self.assertEqual(original[0]["count"], 5)

    def test_tax_invoice_rows_default_to_all_four_named_copies(self) -> None:
        parent = FakeParent()

        seed_registry_rows(parent)  # ty: ignore[invalid-argument-type] - test double

        tax_invoice_copies = [
            row for row in parent.tables["print_copies"] if row["document_key"] == "tax_invoice"
        ]
        self.assertEqual(
            [row["copy_key"] for row in tax_invoice_copies],
            ["original", "customer", "accounting", "sales"],
        )
        self.assertTrue(all(row["count"] == 1 for row in tax_invoice_copies))


class TestRetiredFields(UnitTestCase):
    def test_every_retired_document_prefix_is_covered(self) -> None:
        retired = rebuild_print_configuration.retired_customer_fields()

        for prefix in rebuild_print_configuration.RETIRED_DOCUMENT_PREFIXES:
            for fieldname in (
                f"use_{prefix}",
                f"show_{prefix}_date",
                f"{prefix}_language",
                f"{prefix}_original_count",
                f"{prefix}_copy_count",
            ):
                with self.subTest(fieldname=fieldname):
                    self.assertIn(fieldname, retired)

    def test_retired_list_does_not_drop_fields_still_in_use(self) -> None:
        retired = set(rebuild_print_configuration.retired_customer_fields())

        for kept in (
            "print_configuration_template",
            "customer_print_name",
            "print_documents",
            "print_copies",
            "print_date",
            *print_documents.SCALAR_FIELDS,
        ):
            with self.subTest(fieldname=kept):
                self.assertNotIn(kept, retired)


class TestModuleRepointing(UnitTestCase):
    def test_execute_repoints_formats_and_doctypes(self) -> None:
        set_value = MagicMock()
        with (
            patch.object(rebuild_print_configuration.frappe.db, "exists", return_value=True),
            patch.object(rebuild_print_configuration.frappe.db, "set_value", set_value),
        ):
            rebuild_print_configuration._repoint_module()

        targets = {call.args[1] for call in set_value.call_args_list}
        self.assertEqual(
            targets,
            set(rebuild_print_configuration.PRINT_FORMATS) | set(rebuild_print_configuration.MOVED_DOCTYPES),
        )
        self.assertTrue(all(call.args[3] == "Connect Diagnostics Print" for call in set_value.call_args_list))

    def test_repointing_skips_records_that_do_not_exist(self) -> None:
        set_value = MagicMock()
        with (
            patch.object(rebuild_print_configuration.frappe.db, "exists", return_value=False),
            patch.object(rebuild_print_configuration.frappe.db, "set_value", set_value),
        ):
            rebuild_print_configuration._repoint_module()

        set_value.assert_not_called()

    def test_the_patch_covers_every_shipped_print_format(self) -> None:
        from connect_diagnostics_core.utils.tests.test_print_formats import load_print_formats

        shipped = {print_format["name"] for print_format in load_print_formats()}

        self.assertEqual(set(rebuild_print_configuration.PRINT_FORMATS), shipped)


class TestRollback(UnitTestCase):
    def test_rollback_returns_moved_records_but_not_the_new_ones(self) -> None:
        moved_back = [
            doctype
            for doctype in rollback_rebuild_print_configuration.MOVED_DOCTYPES
            if doctype not in rollback_rebuild_print_configuration.INTRODUCED_DOCTYPES
        ]

        self.assertEqual(moved_back, ["Print Configuration Template"])

    def test_rollback_drops_the_customer_tables_it_introduced(self) -> None:
        self.assertEqual(
            set(rollback_rebuild_print_configuration.INTRODUCED_CUSTOMER_FIELDS),
            {"print_documents_section", "print_documents", "print_copies_section", "print_copies"},
        )
