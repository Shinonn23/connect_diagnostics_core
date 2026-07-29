# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core import hooks
from connect_diagnostics_core.patches.v1_0 import retire_dksh_sales_domain as patch_module
from connect_diagnostics_core.setup import customer_onboarding, item, sales_order_item


class TestRetireDKSHSalesDomain(UnitTestCase):
    def test_execute_is_safe_to_repeat_when_each_retirement_step_is_idempotent(self) -> None:
        step_names = (
            "_ensure_item_dksh_code_field",
            "_backfill_item_dksh_codes",
            "_migrate_pending_customers",
            "_remove_dksh_workflow_actions",
            "_remove_dksh_workflow_configuration",
            "_remove_dksh_price_list",
            "_remove_dksh_permissions_and_roles",
            "_reset_sales_order_item_grid_settings",
            "_remove_retired_custom_fields_and_columns",
            "_remove_retired_doctypes",
        )
        mocks = {name: MagicMock() for name in step_names}
        with ExitStack() as stack:
            for name, mocked_step in mocks.items():
                stack.enter_context(patch.object(patch_module, name, mocked_step))
            mocked_configuration = stack.enter_context(
                patch.object(customer_onboarding, "ensure_configuration")
            )
            mocked_clear_cache = stack.enter_context(patch.object(patch_module.frappe, "clear_cache"))
            patch_module.execute()
            patch_module.execute()

        for mocked_step in mocks.values():
            self.assertEqual(mocked_step.call_count, 2)
        self.assertEqual(mocked_configuration.call_count, 2)
        self.assertEqual(mocked_clear_cache.call_count, 2)

    def test_item_code_backfill_preserves_one_unambiguous_legacy_code(self) -> None:
        def collect_master(
            candidates: defaultdict[str, list[tuple[str, str]]],
            eligible_item_names: set[str] | None,
        ) -> None:
            self.assertEqual(eligible_item_names, {"CD-ITEM-001"})
            candidates["CD-ITEM-001"].append(("retired mapping", "EXT-001"))

        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=True),
            patch.object(
                patch_module.frappe,
                "get_all",
                return_value=[
                    {
                        "name": "CD-ITEM-001",
                        "dksh_item_code": "",
                        "item_channel": patch_module.CHANNEL_BOTH,
                    }
                ],
            ),
            patch.object(patch_module, "_collect_master_mapping_candidates", side_effect=collect_master),
            patch.object(patch_module, "_collect_partner_mapping_candidates"),
            patch.object(patch_module.frappe.db, "set_value") as mocked_set_value,
        ):
            patch_module._backfill_item_dksh_codes()

        mocked_set_value.assert_called_once_with(
            "Item",
            "CD-ITEM-001",
            "dksh_item_code",
            "EXT-001",
            update_modified=False,
        )

    def test_item_code_conflict_blocks_retirement_before_any_backfill_write(self) -> None:
        def collect_master(
            candidates: defaultdict[str, list[tuple[str, str]]],
            eligible_item_names: set[str] | None,
        ) -> None:
            self.assertEqual(eligible_item_names, {"CD-ITEM-001"})
            candidates["CD-ITEM-001"].extend(
                [
                    ("retired mapping", "EXT-001"),
                    ("retired mapping", "EXT-002"),
                ]
            )

        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=True),
            patch.object(
                patch_module.frappe,
                "get_all",
                return_value=[
                    {
                        "name": "CD-ITEM-001",
                        "dksh_item_code": "",
                        "item_channel": patch_module.CHANNEL_BOTH,
                    }
                ],
            ),
            patch.object(patch_module, "_collect_master_mapping_candidates", side_effect=collect_master),
            patch.object(patch_module, "_collect_partner_mapping_candidates"),
            patch.object(patch_module.frappe.db, "set_value") as mocked_set_value,
            patch.object(
                patch_module.frappe,
                "throw",
                side_effect=frappe.ValidationError("Preservation conflict"),
            ) as mocked_throw,
        ):
            with self.assertRaises(frappe.ValidationError):
                patch_module._backfill_item_dksh_codes()

        mocked_set_value.assert_not_called()
        self.assertIn("EXT-001, EXT-002", mocked_throw.call_args.args[0])

    def test_item_code_backfill_skips_dksh_only_items(self) -> None:
        def collect_master(
            candidates: defaultdict[str, list[tuple[str, str]]],
            eligible_item_names: set[str] | None,
        ) -> None:
            self.assertEqual(eligible_item_names, set())
            self.assertEqual(candidates, {})

        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=True),
            patch.object(
                patch_module.frappe,
                "get_all",
                return_value=[
                    {
                        "name": "DKSH-ITEM-001",
                        "dksh_item_code": "",
                        "item_channel": "DKSH",
                    }
                ],
            ),
            patch.object(patch_module, "_collect_master_mapping_candidates", side_effect=collect_master),
            patch.object(patch_module, "_collect_partner_mapping_candidates"),
            patch.object(patch_module.frappe.db, "set_value") as mocked_set_value,
        ):
            patch_module._backfill_item_dksh_codes()

        mocked_set_value.assert_not_called()

    def test_conflict_aborts_execute_before_destructive_retirement(self) -> None:
        conflict = frappe.ValidationError("Preservation conflict")
        with (
            patch.object(patch_module, "_ensure_item_dksh_code_field"),
            patch.object(patch_module, "_backfill_item_dksh_codes", side_effect=conflict),
            patch.object(customer_onboarding, "ensure_configuration") as mocked_configuration,
            patch.object(patch_module, "_remove_retired_custom_fields_and_columns") as mocked_fields,
            patch.object(patch_module, "_remove_retired_doctypes") as mocked_doctypes,
        ):
            with self.assertRaises(frappe.ValidationError):
                patch_module.execute()

        mocked_configuration.assert_not_called()
        mocked_fields.assert_not_called()
        mocked_doctypes.assert_not_called()

    def test_pending_customer_moves_to_accounting_and_receives_new_actions(self) -> None:
        customer_doc = MagicMock()
        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=True),
            patch.object(patch_module.frappe, "get_all", return_value=["CD-0001"]),
            patch.object(patch_module, "clear_workflow_actions") as mocked_clear_actions,
            patch.object(patch_module.frappe.db, "set_value") as mocked_set_value,
            patch.object(patch_module.frappe, "get_doc", return_value=customer_doc),
            patch.object(patch_module, "process_workflow_actions") as mocked_process_actions,
        ):
            patch_module._migrate_pending_customers()

        mocked_clear_actions.assert_called_once_with("Customer", "CD-0001")
        mocked_set_value.assert_called_once_with(
            "Customer",
            "CD-0001",
            "customer_onboarding_state",
            customer_onboarding.PENDING_ACCOUNTING_STATE,
            update_modified=False,
        )
        mocked_process_actions.assert_called_once_with(customer_doc, "on_update")

    def test_retired_field_allowlist_keeps_item_code_and_standard_sales_order_fields(self) -> None:
        self.assertNotIn("dksh_item_code", patch_module.RETIRED_CUSTOM_FIELDS["Item"])
        self.assertTrue(
            {
                "item_channel",
                "partner_item_mappings",
                "has_dksh_code",
                "item_code_is_dksh_code",
            }.issubset(patch_module.RETIRED_CUSTOM_FIELDS["Item"])
        )
        self.assertTrue(
            {
                "dksh_item_code",
                "supplier_product_code",
                "mat_group_code",
                "mat_group4_code",
                "material_type_code",
            }.isdisjoint(patch_module.RETIRED_CUSTOM_FIELDS["Item"])
        )
        self.assertEqual(
            set(patch_module.RETIRED_CUSTOM_FIELDS["Sales Order Item"]),
            {"dksh_item_mapping", "custom_dksh_item_mapping"},
        )
        item_fields = {field["fieldname"]: field for field in item.CUSTOM_FIELDS["Item"]}
        sales_order_item_fields = {
            field["fieldname"] for field in sales_order_item.CUSTOM_FIELDS["Sales Order Item"]
        }

        self.assertIn("dksh_item_code", item_fields)
        self.assertEqual(item_fields["dksh_tab"]["fieldtype"], "Tab Break")
        self.assertEqual(item_fields["dksh_tab"]["label"], "DKSH")
        self.assertEqual(item_fields["dksh_item_code"]["insert_after"], "dksh_tab")
        self.assertEqual(
            item_fields["supplier_product_code"]["insert_after"],
            "dksh_item_code",
        )
        self.assertEqual(item_fields["mat_group_code"]["insert_after"], "supplier_product_code")
        self.assertEqual(item_fields["mat_group4_code"]["insert_after"], "mat_group_code")
        self.assertEqual(item_fields["material_type_code"]["insert_after"], "mat_group4_code")
        self.assertNotIn("item_channel", item_fields)
        self.assertNotIn("dksh_item_mapping", sales_order_item_fields)
        self.assertNotIn("Sales Order", hooks.doc_events)
        self.assertNotIn("Sales Order", hooks.doctype_js)
        self.assertFalse(hasattr(hooks, "override_whitelisted_methods"))

    def test_doctype_retirement_is_limited_to_mapping_and_legacy_settings(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "delete") as mocked_delete,
            patch.object(patch_module.frappe.db, "table_exists", return_value=False),
            patch.object(patch_module, "_delete_doc_if_exists") as mocked_delete_doc,
            patch.object(patch_module, "_drop_table_if_exists") as mocked_drop_table,
        ):
            patch_module._remove_retired_doctypes()

        mocked_delete.assert_called_once_with("Singles", {"doctype": patch_module.DKSH_SETTINGS_DOCTYPE})
        expected_doctypes = (
            patch_module.DKSH_MAPPING_DOCTYPE,
            patch_module.PARTNER_MAPPING_DOCTYPE,
            patch_module.DKSH_SETTINGS_DOCTYPE,
        )
        self.assertEqual(
            mocked_delete_doc.call_args_list,
            [call("DocType", doctype) for doctype in expected_doctypes],
        )
        self.assertEqual(
            mocked_drop_table.call_args_list,
            [call(doctype) for doctype in expected_doctypes],
        )

    def test_missing_schema_objects_make_destructive_helpers_no_ops(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "has_column", return_value=False),
            patch.object(patch_module.frappe.db, "table_exists", return_value=False),
            patch.object(patch_module.frappe.db, "exists", return_value=False),
            patch.object(patch_module.frappe.db, "sql_ddl") as mocked_ddl,
            patch.object(patch_module.frappe, "delete_doc") as mocked_delete_doc,
        ):
            patch_module._drop_column_if_exists("Customer", "customer_channel")
            patch_module._drop_table_if_exists(patch_module.DKSH_MAPPING_DOCTYPE)
            patch_module._delete_doc_if_exists("Role", "Retired Role")

        mocked_ddl.assert_not_called()
        mocked_delete_doc.assert_not_called()

    def test_retirement_preview_is_read_only_and_reports_conflicts(self) -> None:
        with (
            patch.object(
                patch_module,
                "_plan_item_dksh_code_updates",
                return_value=({"CD-ITEM-001": "EXT-001"}, ["duplicate legacy code"]),
            ),
            patch.object(patch_module.frappe.db, "count", return_value=0),
            patch.object(patch_module.frappe.db, "has_column", return_value=False),
            patch.object(patch_module.frappe.db, "table_exists", return_value=False),
            patch.object(patch_module.frappe.db, "exists", return_value=False),
            patch.object(patch_module.frappe.db, "sql", return_value=[]),
            patch.object(patch_module.frappe.db, "set_value") as mocked_set_value,
            patch.object(patch_module.frappe.db, "delete") as mocked_delete,
            patch.object(patch_module.frappe.db, "sql_ddl") as mocked_ddl,
            patch.object(patch_module.frappe, "delete_doc") as mocked_delete_doc,
        ):
            preview = patch_module.get_retirement_preview()

        self.assertEqual(preview["item_codes_to_backfill"], 1)
        self.assertEqual(preview["item_code_conflicts"], ["duplicate legacy code"])
        mocked_set_value.assert_not_called()
        mocked_delete.assert_not_called()
        mocked_ddl.assert_not_called()
        mocked_delete_doc.assert_not_called()
