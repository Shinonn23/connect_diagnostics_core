from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import rollback_backfill_national_id_display as patch_module


class TestRollbackBackfillNationalIdDisplayPatch(UnitTestCase):
    @patch.object(patch_module, "frappe")
    def test_execute_clears_national_id_display_column(self, frappe) -> None:
        frappe.db.has_column.return_value = True

        patch_module.execute()

        frappe.db.sql.assert_called_once()
        self.assertIn("SET national_id_display = ''", frappe.db.sql.call_args.args[0])

    @patch.object(patch_module, "frappe")
    def test_execute_noop_when_column_missing(self, frappe) -> None:
        frappe.db.has_column.return_value = False

        patch_module.execute()

        frappe.db.sql.assert_not_called()
