# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import normalize_workflow_baseline as patch_module
from connect_diagnostics_core.patches.v1_0 import rollback_normalize_workflow_baseline as recovery


class TestNormalizeWorkflowBaseline(UnitTestCase):
    def test_changed_route_predecessors_do_not_point_at_desired_fixture(self) -> None:
        desired = patch_module._desired_workflows()
        for name in (
            "Connect Asset Movement Approval",
            "Connect Sales Invoice Credit Blueprint",
            "Connect Purchase Order Blueprint",
        ):
            self.assertNotEqual(
                patch_module.PREDECESSOR_FINGERPRINTS[name],
                patch_module.workflow_fingerprint(desired[name]),
                msg=f"{name} predecessor hash must represent the captured pre-migration row",
            )

    def test_fixture_is_the_exact_canonical_allowlist(self) -> None:
        desired = patch_module._desired_workflows()
        self.assertEqual(set(desired), set(patch_module.CANONICAL_WORKFLOWS))
        self.assertEqual(
            {str(record["document_type"]) for record in desired.values()},
            set(patch_module.CANONICAL_WORKFLOWS.values()),
        )
        self.assertTrue(all(int(record["is_active"]) == 1 for record in desired.values()))

    def test_fingerprint_is_order_sensitive_and_deterministic(self) -> None:
        first = {
            "name": "Workflow A",
            "document_type": "Journal Entry",
            "is_active": 1,
            "states": [
                {"state": "Draft", "doc_status": "0", "allow_edit": "Accounts User"},
                {"state": "Approved", "doc_status": "0", "allow_edit": "Accounts Manager"},
            ],
            "transitions": [
                {
                    "state": "Draft",
                    "action": "Approve",
                    "next_state": "Approved",
                    "allowed": "Accounts Manager",
                }
            ],
        }
        second = dict(first)
        second["states"] = list(reversed(first["states"]))
        self.assertEqual(patch_module.workflow_fingerprint(first), patch_module.workflow_fingerprint(first))
        self.assertNotEqual(
            patch_module.workflow_fingerprint(first), patch_module.workflow_fingerprint(second)
        )

    def test_retirement_stops_on_open_actions(self) -> None:
        name = "Connect Asset Disposal Blueprint"
        doctype, expected_hash = patch_module.RETIRED_WORKFLOWS[name]
        workflow = frappe._dict(is_active=1)
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe, "get_doc", return_value=workflow),
            patch.object(patch_module, "workflow_fingerprint", return_value=expected_hash),
            self.assertRaises(frappe.ValidationError),
        ):
            patch_module._safe_to_retire(name, doctype, expected_hash)

    def test_retirement_stops_on_nonterminal_documents(self) -> None:
        name = "Connect Asset Disposal Blueprint"
        doctype, expected_hash = patch_module.RETIRED_WORKFLOWS[name]
        workflow = frappe._dict(is_active=1)

        def exists(target: str, filters: object | None = None) -> bool:
            del filters
            return target in {"Workflow", doctype}

        with (
            patch.object(patch_module.frappe.db, "exists", side_effect=exists),
            patch.object(patch_module.frappe.db, "has_column", return_value=True),
            patch.object(patch_module.frappe, "get_doc", return_value=workflow),
            patch.object(patch_module, "workflow_fingerprint", return_value=expected_hash),
            self.assertRaises(frappe.ValidationError),
        ):
            patch_module._safe_to_retire(name, doctype, expected_hash)

    def test_already_inactive_retirement_is_idempotent(self) -> None:
        name = "Connect Material Request Blueprint"
        doctype, expected_hash = patch_module.RETIRED_WORKFLOWS[name]
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe, "get_doc", return_value=frappe._dict(is_active=0)),
            patch.object(patch_module, "workflow_fingerprint") as fingerprint,
        ):
            self.assertFalse(patch_module._safe_to_retire(name, doctype, expected_hash))
        fingerprint.assert_not_called()

    def test_all_retirement_preflight_runs_before_mutation(self) -> None:
        desired = {name: {} for name in patch_module.CANONICAL_WORKFLOWS}
        with (
            patch.object(patch_module, "_desired_workflows", return_value=desired),
            patch.object(patch_module, "_preflight_canonical"),
            patch.object(
                patch_module,
                "_safe_to_retire",
                side_effect=[True, Exception("preflight stopped")],
            ),
            patch.object(patch_module, "_save_recovery_snapshot") as snapshot,
            patch.object(patch_module, "_ensure_custom_fields") as fields,
            patch.object(patch_module, "_ensure_transition_tasks") as tasks,
        ):
            with self.assertRaisesRegex(Exception, "preflight stopped"):
                patch_module.execute()
        snapshot.assert_not_called()
        fields.assert_not_called()
        tasks.assert_not_called()


class TestIncompleteApplyRecovery(UnitTestCase):
    def test_completed_patch_refuses_incomplete_apply_recovery(self) -> None:
        def exists(doctype: str, filters: object) -> str | None:
            del filters
            return "record" if doctype in {"File", "Patch Log"} else None

        with (
            patch.object(recovery.frappe.db, "exists", side_effect=exists),
            patch.object(recovery, "_snapshot") as snapshot,
            self.assertRaises(frappe.ValidationError),
        ):
            recovery.recover_incomplete_apply()
        snapshot.assert_not_called()

    def test_changed_workflow_refuses_incomplete_apply_recovery(self) -> None:
        snapshot = {"workflows": [{"name": "Workflow A"}]}

        def exists(doctype: str, filters: object) -> str | None:
            del filters
            return "record" if doctype in {"File", "Workflow"} else None

        with (
            patch.object(recovery.frappe.db, "exists", side_effect=exists),
            patch.object(recovery.frappe, "get_doc", return_value=frappe._dict(creation="2026-09-26")),
            patch.object(recovery, "_snapshot", return_value=snapshot),
            patch.object(recovery, "workflow_fingerprint", side_effect=["changed", "captured"]),
            patch.object(recovery, "_restore_transition_tasks") as restore_tasks,
            self.assertRaises(frappe.ValidationError),
        ):
            recovery.recover_incomplete_apply()
        restore_tasks.assert_not_called()

    def test_nonempty_custom_field_is_never_removed(self) -> None:
        def exists(doctype: str, filters: object) -> str | None:
            del filters
            return "record" if doctype in {"Custom Field", "Payment Entry"} else None

        with (
            patch.object(recovery.frappe.db, "exists", side_effect=exists),
            patch.object(recovery.frappe.db, "has_column", return_value=True),
            patch.object(recovery.frappe, "delete_doc") as delete_doc,
            self.assertRaises(frappe.ValidationError),
        ):
            recovery._remove_custom_fields([{"dt": "Payment Entry", "fieldname": "approval_digest"}])
        delete_doc.assert_not_called()

    def test_snapshot_is_deleted_only_after_recovery_postconditions(self) -> None:
        snapshot = {"workflows": [], "transition_tasks": [], "missing_transition_tasks": []}

        def exists(doctype: str, filters: object) -> str | None:
            del filters
            return "snapshot-file" if doctype == "File" else None

        with (
            patch.object(recovery.frappe.db, "exists", side_effect=exists),
            patch.object(recovery.frappe, "get_doc", return_value=frappe._dict(creation="2026-09-26")),
            patch.object(recovery, "_snapshot", return_value=snapshot),
            patch.object(recovery, "_restore_transition_tasks"),
            patch.object(recovery.frappe, "get_all", return_value=[]),
            patch.object(recovery, "_assert_recovered") as assert_recovered,
            patch.object(recovery.frappe, "delete_doc") as delete_doc,
        ):
            recovery.recover_incomplete_apply()
        assert_recovered.assert_called_once_with(snapshot)
        delete_doc.assert_called_once_with("File", "snapshot-file", ignore_permissions=True)
