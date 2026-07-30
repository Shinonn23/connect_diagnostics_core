# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import (
    expand_customer_document_preferences as patch_module,
)
from connect_diagnostics_core.setup import customer as customer_setup


class TestExpandCustomerDocumentPreferences(UnitTestCase):
    def test_build_preference_values_splits_tax_invoice_and_preserves_print_date(
        self,
    ) -> None:
        values = patch_module.build_preference_values(
            {
                "use_tax_invoice": 0,
                "print_date": 0,
            }
        )

        self.assertEqual(values["use_delivery_note"], 0)
        self.assertEqual(values["use_invoice"], 0)
        self.assertEqual(values["purchase_order_copy_count"], 1)
        self.assertEqual(values["quotation_form_preset"], "Form 02")
        self.assertEqual(values["quotation_signatory_type"], "Sales Representative")
        self.assertEqual(values["quotation_validity_mode"], "Valid Till")
        for prefix, _label, _use_fieldname in customer_setup.DOCUMENT_PREFERENCES:
            with self.subTest(prefix=prefix):
                self.assertEqual(values[f"show_{prefix}_date"], 0)
                self.assertEqual(values[f"{prefix}_original_count"], 1)
                self.assertEqual(values[f"{prefix}_copy_count"], 0)
                self.assertEqual(values[f"{prefix}_language"], "Thai")

    @patch.object(patch_module.frappe, "logger")
    @patch.object(patch_module.frappe.db, "set_value")
    @patch.object(patch_module.frappe, "get_all")
    @patch.object(patch_module, "create_custom_fields")
    def test_execute_creates_fields_and_backfills_customers_idempotently(
        self,
        mocked_create_custom_fields: MagicMock,
        mocked_get_all: MagicMock,
        mocked_set_value: MagicMock,
        mocked_logger: MagicMock,
    ) -> None:
        customers: list[dict[str, Any]] = [
            {"name": "CUST-0001", "use_tax_invoice": 1, "print_date": 1},
            {"name": "CUST-0002", "use_tax_invoice": 0, "print_date": 0},
        ]
        mocked_get_all.return_value = customers

        patch_module.execute()
        first_run_calls = cast(list[Any], mocked_set_value.call_args_list.copy())
        mocked_set_value.reset_mock()
        patch_module.execute()

        mocked_create_custom_fields.assert_has_calls(
            [
                call(customer_setup.CUSTOM_FIELDS, ignore_validate=True),
                call(customer_setup.CUSTOM_FIELDS, ignore_validate=True),
            ]
        )
        mocked_get_all.assert_has_calls(
            [
                call("Customer", fields=list(patch_module.LEGACY_FIELDS)),
                call("Customer", fields=list(patch_module.LEGACY_FIELDS)),
            ]
        )
        self.assertEqual(mocked_set_value.call_args_list, first_run_calls)
        self.assertEqual(first_run_calls[0].args[2]["use_delivery_note"], 1)
        self.assertEqual(first_run_calls[0].args[2]["use_invoice"], 1)
        self.assertEqual(first_run_calls[1].args[2]["use_delivery_note"], 0)
        self.assertEqual(first_run_calls[1].args[2]["use_invoice"], 0)
        self.assertNotIn("use_customer_po", first_run_calls[0].args[2])
        self.assertNotIn("use_tax_invoice", first_run_calls[0].args[2])
        mocked_logger.assert_called()
