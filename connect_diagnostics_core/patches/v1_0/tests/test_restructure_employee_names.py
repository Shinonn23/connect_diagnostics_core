from __future__ import annotations

from unittest.mock import call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import restructure_employee_names as patch_module


class TestRestructureEmployeeNamesPatch(UnitTestCase):
    @patch.object(patch_module, "delete_custom_fields")
    @patch.object(patch_module, "create_custom_fields")
    @patch.object(patch_module, "frappe")
    def test_execute_creates_en_fields_migrates_data_and_cleans_up(
        self, frappe, create_custom_fields, delete_custom_fields
    ) -> None:
        frappe.db.has_column.return_value = True
        frappe.db.sql.return_value = []

        patch_module.execute()

        create_custom_fields.assert_called_once_with(patch_module.EMPLOYEE_EN_FIELDS, update=True)
        delete_custom_fields.assert_called_once_with(
            {"Employee": list(patch_module.OLD_TH_FIELDS)},
            bypass_hooks=True,
        )
        self.assertEqual(frappe.db.sql.call_count, 2)
        self.assertIn("SELECT name", frappe.db.sql.call_args_list[0].args[0])
        self.assertIn("custom_first_name_en = first_name", frappe.db.sql.call_args_list[1].args[0])
        frappe.db.delete.assert_called_once_with(
            "Property Setter",
            {
                "doc_type": "Employee",
                "field_name": "middle_name",
                "property": "label",
            },
        )
        self.assertEqual(
            frappe.db.sql_ddl.call_args_list,
            [
                call("ALTER TABLE `tabEmployee` DROP COLUMN `custom_first_name_th`"),
                call("ALTER TABLE `tabEmployee` DROP COLUMN `custom_last_name_th`"),
                call("ALTER TABLE `tabEmployee` DROP COLUMN `custom_full_name_th`"),
                call("ALTER TABLE `tabEmployee` DROP COLUMN `custom_middle_name_th`"),
            ],
        )
        frappe.clear_cache.assert_called_once_with(doctype="Employee")

    @patch.object(patch_module, "frappe")
    def test_validate_all_employees_have_th_names_throws_when_missing(self, frappe) -> None:
        frappe.db.sql.return_value = [{"name": "EMP-001"}, {"name": "EMP-002"}]

        patch_module._validate_all_employees_have_th_names()

        frappe.throw.assert_called_once()
        self.assertIn("EMP-001, EMP-002", frappe.throw.call_args.args[0])

    @patch.object(patch_module, "delete_custom_fields")
    @patch.object(patch_module, "create_custom_fields")
    @patch.object(patch_module, "frappe")
    def test_execute_throws_when_legacy_th_columns_are_incomplete(
        self, frappe, create_custom_fields, delete_custom_fields
    ) -> None:
        frappe.db.has_column.side_effect = [True, False]
        frappe.throw.side_effect = RuntimeError("legacy columns incomplete")

        with self.assertRaises(RuntimeError):
            patch_module.execute()

        frappe.throw.assert_called_once()
        create_custom_fields.assert_called_once_with(patch_module.EMPLOYEE_EN_FIELDS, update=True)
        delete_custom_fields.assert_not_called()

    @patch.object(patch_module, "frappe")
    def test_drop_old_th_columns_only_drops_existing_columns(self, frappe) -> None:
        frappe.db.has_column.side_effect = [True, False, True, False]

        patch_module._drop_old_th_columns()

        self.assertEqual(
            frappe.db.sql_ddl.call_args_list,
            [
                call("ALTER TABLE `tabEmployee` DROP COLUMN `custom_first_name_th`"),
                call("ALTER TABLE `tabEmployee` DROP COLUMN `custom_full_name_th`"),
            ],
        )
