from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import migrate_employee_approval_signature as patch_module


class TestMigrateEmployeeApprovalSignaturePatch(UnitTestCase):
    @patch.object(patch_module, "create_custom_fields")
    @patch.object(patch_module, "frappe")
    def test_execute_migrates_value_and_removes_legacy_field(self, frappe, create_custom_fields) -> None:
        frappe.db.has_column.side_effect = [True, True]
        frappe.db.get_value.return_value = "Employee-quotation_signature"

        patch_module.execute()

        create_custom_fields.assert_called_once_with(
            {"Employee": [patch_module.APPROVAL_SIGNATURE_FIELD]},
            update=True,
        )
        self.assertIn("SET approval_signature = quotation_signature", frappe.db.sql.call_args.args[0])
        frappe.delete_doc.assert_called_once_with(
            "Custom Field",
            "Employee-quotation_signature",
            ignore_permissions=True,
            force=True,
        )
        frappe.db.sql_ddl.assert_called_once_with(
            "ALTER TABLE `tabEmployee` DROP COLUMN `quotation_signature`"
        )
        frappe.clear_cache.assert_called_once_with(doctype="Employee")
        frappe.db.commit.assert_called_once()

    @patch.object(patch_module, "create_custom_fields")
    @patch.object(patch_module, "frappe")
    def test_execute_is_safe_when_legacy_field_is_already_gone(self, frappe, create_custom_fields) -> None:
        frappe.db.has_column.side_effect = [False, False]
        frappe.db.get_value.return_value = None

        patch_module.execute()

        create_custom_fields.assert_called_once_with(
            {"Employee": [patch_module.APPROVAL_SIGNATURE_FIELD]},
            update=True,
        )
        frappe.db.sql.assert_not_called()
        frappe.delete_doc.assert_not_called()
        frappe.db.sql_ddl.assert_not_called()
        frappe.clear_cache.assert_called_once_with(doctype="Employee")
        frappe.db.commit.assert_called_once()
