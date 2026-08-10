from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import backfill_national_id_display as patch_module


class TestBackfillNationalIdDisplayPatch(UnitTestCase):
    @patch.object(patch_module, "create_custom_fields")
    @patch.object(patch_module, "frappe")
    def test_execute_creates_field_and_backfills_clean_records(self, frappe, create_custom_fields) -> None:
        frappe.db.has_column.return_value = True
        frappe.get_all.return_value = [
            SimpleNamespace(name="EMP-001", national_id="3-1004-00828-61-1"),
            SimpleNamespace(name="EMP-002", national_id="1002003004007"),
        ]

        patch_module.execute()

        create_custom_fields.assert_called_once_with(
            {"Employee": [patch_module.NATIONAL_ID_DISPLAY_FIELD]}, update=True
        )
        self.assertEqual(
            frappe.db.set_value.call_args_list,
            [
                call("Employee", "EMP-001", "national_id_display", "3-1004-00828-61-1", update_modified=False),
                call("Employee", "EMP-002", "national_id_display", "1-0020-03004-00-7", update_modified=False),
            ],
        )

    @patch.object(patch_module, "create_custom_fields")
    @patch.object(patch_module, "frappe")
    def test_execute_skips_and_logs_dirty_national_id(self, frappe, create_custom_fields) -> None:
        frappe.db.has_column.return_value = True
        frappe.get_all.return_value = [SimpleNamespace(name="EMP-001", national_id="not-13-digits")]

        patch_module.execute()

        frappe.db.set_value.assert_not_called()
        frappe.logger.return_value.warning.assert_called_once()

    @patch.object(patch_module, "create_custom_fields")
    @patch.object(patch_module, "frappe")
    def test_execute_skips_13_digits_with_invalid_checksum(self, frappe, create_custom_fields) -> None:
        frappe.db.has_column.return_value = True
        frappe.get_all.return_value = [SimpleNamespace(name="EMP-001", national_id="1234567890123")]

        patch_module.execute()

        frappe.db.set_value.assert_not_called()
        frappe.logger.return_value.warning.assert_called_once()

    @patch.object(patch_module, "create_custom_fields")
    @patch.object(patch_module, "frappe")
    def test_execute_noop_when_national_id_column_missing(self, frappe, create_custom_fields) -> None:
        frappe.db.has_column.return_value = False

        patch_module.execute()

        create_custom_fields.assert_not_called()
        frappe.get_all.assert_not_called()
