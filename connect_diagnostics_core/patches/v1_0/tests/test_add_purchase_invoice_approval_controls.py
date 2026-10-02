# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import add_purchase_invoice_approval_controls as add_patch
from connect_diagnostics_core.patches.v1_0 import (
    rollback_add_purchase_invoice_approval_controls as rollback_patch,
)


class TestPurchaseInvoiceApprovalPatch(UnitTestCase):
    def test_inventoried_baseline_has_exact_fingerprint(self) -> None:
        baseline = {
            "name": "Connect Purchase Invoice Blueprint",
            "document_type": "Purchase Invoice",
            "is_active": 1,
            "workflow_state_field": "workflow_state",
            "states": [
                {"state": state, "doc_status": status, "allow_edit": role}
                for state, status, role in rollback_patch._BASELINE_STATES
            ],
            "transitions": [
                {
                    "state": state,
                    "action": action,
                    "next_state": next_state,
                    "allowed": role,
                    "allow_self_approval": 0,
                    "condition": None,
                    "transition_tasks": None,
                }
                for state, action, next_state, role in rollback_patch._BASELINE_TRANSITIONS
            ],
        }
        self.assertEqual(
            add_patch._workflow_fingerprint(baseline),
            add_patch.EXPECTED_FINGERPRINT,
        )

    def test_current_fixture_keeps_canonical_maker_and_trial_task_route(self) -> None:
        fixture_path = Path(__file__).parents[3] / "fixtures" / "workflow.json"
        workflow = next(
            row
            for row in json.loads(fixture_path.read_text())
            if row["name"] == "Connect Purchase Invoice Blueprint"
        )
        actual = {
            (row["state"], row["action"], row["next_state"]): row.get("transition_tasks")
            for row in workflow["transitions"]
        }
        self.assertEqual(set(actual), set(add_patch.EXPECTED_TRANSITION_TASKS))
        maker_task = "Connect Purchase Invoice Maker"
        self.assertEqual(
            actual[
                (
                    "Purchase Invoice Draft",
                    "Submit Purchase Invoice for Review",
                    "Purchase Invoice Pending Source Verification",
                )
            ],
            maker_task,
        )
        self.assertEqual(
            actual[
                (
                    "Purchase Invoice Returned",
                    "Resubmit Purchase Invoice",
                    "Purchase Invoice Pending Source Verification",
                )
            ],
            maker_task,
        )
        for route, task in add_patch.EXPECTED_TRANSITION_TASKS.items():
            if route[1] in {"Submit Purchase Invoice for Review", "Resubmit Purchase Invoice"}:
                continue
            self.assertEqual(actual[route], task)

    def test_transition_task_contract_is_synchronous_and_complete(self) -> None:
        referenced_tasks = {task for task in add_patch.EXPECTED_TRANSITION_TASKS.values() if task}
        self.assertEqual(referenced_tasks, set(add_patch.TASKS))

    def test_recovery_stops_on_wrong_site_without_deleting_history(self) -> None:
        with (
            patch.object(rollback_patch.frappe.local, "site", "local"),
            patch.object(rollback_patch.frappe.db, "delete") as delete,
            self.assertRaises(frappe.ValidationError),
        ):
            rollback_patch.execute()
        delete.assert_not_called()

    def test_recovery_restores_only_a_matching_empty_trial(self) -> None:
        workflow = MagicMock()
        workflow.as_dict.return_value = {"name": "Connect Purchase Invoice Blueprint"}
        with (
            patch.object(rollback_patch.frappe.local, "site", "local.test"),
            patch.object(rollback_patch.frappe.db, "count", return_value=0),
            patch.object(rollback_patch.frappe, "get_doc", return_value=workflow),
            patch.object(rollback_patch, "_workflow_fingerprint", return_value=add_patch.TRIAL_FINGERPRINT),
            patch.object(rollback_patch.frappe.db, "delete") as delete,
        ):
            rollback_patch.execute()
        self.assertEqual(workflow.set.call_count, 2)
        workflow.save.assert_called_once_with(ignore_permissions=True)
        delete.assert_not_called()
