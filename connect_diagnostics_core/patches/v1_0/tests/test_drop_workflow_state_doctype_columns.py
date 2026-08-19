# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import drop_workflow_state_doctype_columns as patch_module


class TestDropWorkflowStateDoctypeColumns(UnitTestCase):
    def test_targets_the_four_app_owned_state_columns(self) -> None:
        self.assertEqual(
            set(patch_module.WORKFLOW_STATE_COLUMNS),
            {
                ("Stock Count", "count_state"),
                ("Customer Credit Request", "credit_request_state"),
                ("Medical Device Product Registration", "regulatory_workflow_state"),
                ("Supplier Bank Change Request", "bank_change_request_state"),
            },
        )

    def test_drops_each_column_idempotently(self) -> None:
        dropped: list[str] = []

        with (
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(
                patch_module.frappe.db,
                "sql_ddl",
                side_effect=lambda statement: dropped.append(statement),
            ),
        ):
            patch_module.execute()

        self.assertEqual(len(dropped), 4)
        for (doctype, column), statement in zip(patch_module.WORKFLOW_STATE_COLUMNS, dropped, strict=True):
            self.assertIn(f"`tab{doctype}`", statement)
            # IF EXISTS keeps the drop idempotent regardless of DocType-sync order.
            self.assertIn(f"DROP COLUMN IF EXISTS `{column}`", statement)
