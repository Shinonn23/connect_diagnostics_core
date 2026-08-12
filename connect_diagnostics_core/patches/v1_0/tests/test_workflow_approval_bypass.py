# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import workflow_approval_bypass as patch_module


class TestWorkflowApprovalBypass(UnitTestCase):
    def test_execute_normalizes_only_inactive_workflows_and_retains_actions(self) -> None:
        def get_workflow(_doctype: str, filters: dict[str, object], _field: str) -> str | None:
            if filters["is_active"] == 1:
                return None
            return "Inactive Workflow"

        with (
            patch.object(patch_module.frappe.db, "get_value", side_effect=get_workflow),
            patch.object(patch_module.frappe.db, "set_value") as set_value,
            patch.object(patch_module.frappe, "get_all", return_value=["ACTION-1", "ACTION-2"]),
            patch.object(patch_module.frappe, "clear_cache"),
        ):
            patch_module.execute()

        self.assertEqual(set_value.call_count, len(patch_module.MANAGED_DOCUMENT_TYPES))

    def test_execute_does_not_bypass_missing_or_active_workflow(self) -> None:
        def get_workflow(_doctype: str, filters: dict[str, object], _field: str) -> str | None:
            if filters["is_active"] == 1:
                return "Active Workflow" if _doctype == "Payment Request" else None
            return None

        with (
            patch.object(patch_module.frappe.db, "get_value", side_effect=get_workflow),
            patch.object(patch_module.frappe.db, "set_value") as set_value,
            patch.object(patch_module.frappe, "get_all") as get_all,
            patch.object(patch_module.frappe, "clear_cache"),
        ):
            patch_module.execute()

        get_all.assert_not_called()
        set_value.assert_not_called()
