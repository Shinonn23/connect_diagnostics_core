# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

from frappe.tests import UnitTestCase

from connect_diagnostics_core import hooks

ROOT = Path(__file__).parents[3]
FIXTURES = ROOT / "connect_diagnostics_core" / "fixtures"
MANIFEST = ROOT / ".github" / "tasks" / "workflow-baseline-implementation" / "workflow-route-manifest.json"
PERMISSIONS = ROOT / ".github" / "tasks" / "workflow-baseline-implementation" / "permission-blueprint.json"


class TestWorkflowFixtureBlueprints(UnitTestCase):
    def test_asset_movement_runtime_hooks_are_exact(self) -> None:
        self.assertEqual(
            hooks.extend_doctype_class["Asset"],
            ["connect_diagnostics_core.api.erpnext.asset_movement_workflow.AssetMovementNativeMixin"],
        )
        self.assertEqual(
            hooks.extend_doctype_class["Asset Movement"],
            ["connect_diagnostics_core.api.erpnext.asset_movement_workflow.AssetMovementWorkflowMixin"],
        )
        self.assertEqual(
            hooks.doc_events["Asset Movement"],
            {
                "before_validate": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.lock_assets_before_submit",
                "validate": [
                    "connect_diagnostics_core.api.erpnext.material_request.validate_asset_movement",
                    "connect_diagnostics_core.api.erpnext.asset_movement_workflow.validate_workflow",
                ],
                "before_submit": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.validate_before_submit",
                "before_cancel": [
                    "connect_diagnostics_core.api.erpnext.asset_movement_workflow.validate_before_cancel",
                    "connect_diagnostics_core.api.erpnext.material_request.before_cancel_movement",
                ],
            },
        )
        methods = {row["name"]: row["method"] for row in hooks.workflow_methods}
        self.assertEqual(
            {
                name: methods[name]
                for name in (
                    "Capture Asset Movement Maker",
                    "Capture Asset Movement Review",
                    "Capture Asset Movement Approval",
                    "Reset Asset Movement Approval",
                    "Authorize Asset Movement Submit Transition",
                    "Authorize Asset Movement Cancel Transition",
                )
            },
            {
                "Capture Asset Movement Maker": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.capture_maker",
                "Capture Asset Movement Review": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.capture_review",
                "Capture Asset Movement Approval": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.capture_approval",
                "Reset Asset Movement Approval": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.reset_approval",
                "Authorize Asset Movement Submit Transition": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.authorize_submit_transition",
                "Authorize Asset Movement Cancel Transition": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.authorize_cancel_transition",
            },
        )

    def test_asset_movement_wf06_route_is_exact(self) -> None:
        workflows = json.loads((FIXTURES / "workflow.json").read_text())
        route = next(row for row in workflows if row["document_type"] == "Asset Movement")
        self.assertEqual(route["workflow_name"], "Connect Asset Movement Approval")
        self.assertEqual(
            [(row["state"], row["allow_edit"], row["doc_status"]) for row in route["states"]],
            [
                ("Asset Movement Draft", "Stock User", "0"),
                ("Asset Movement Pending Review", "Stock Manager", "0"),
                ("Asset Movement Pending Approval", "C-Level Approver", "0"),
                ("Asset Movement Approved", "Stock Manager", "0"),
                ("Asset Movement Rejected", "Stock User", "0"),
                ("Asset Movement Submitted", "Stock Manager", "1"),
                ("Asset Movement Cancelled", "Stock Manager", "2"),
            ],
        )
        self.assertEqual(
            [
                (row["action"], row["state"], row["next_state"], row["allowed"], row["transition_tasks"])
                for row in route["transitions"]
            ],
            [
                (
                    "Send Asset Movement for Review",
                    "Asset Movement Draft",
                    "Asset Movement Pending Review",
                    "Stock User",
                    "Connect Asset Movement Maker Snapshot",
                ),
                (
                    "Review Asset Movement",
                    "Asset Movement Pending Review",
                    "Asset Movement Pending Approval",
                    "Stock Manager",
                    "Connect Asset Movement Review Snapshot",
                ),
                (
                    "Return Asset Movement",
                    "Asset Movement Pending Review",
                    "Asset Movement Draft",
                    "Stock Manager",
                    "Connect Asset Movement Approval Reset",
                ),
                (
                    "Approve Asset Movement",
                    "Asset Movement Pending Approval",
                    "Asset Movement Approved",
                    "C-Level Approver",
                    "Connect Asset Movement Approval Snapshot",
                ),
                (
                    "Return Asset Movement",
                    "Asset Movement Pending Approval",
                    "Asset Movement Draft",
                    "C-Level Approver",
                    "Connect Asset Movement Approval Reset",
                ),
                (
                    "Reject Asset Movement",
                    "Asset Movement Pending Approval",
                    "Asset Movement Rejected",
                    "C-Level Approver",
                    None,
                ),
                (
                    "Resubmit Asset Movement",
                    "Asset Movement Rejected",
                    "Asset Movement Pending Review",
                    "Stock User",
                    "Connect Asset Movement Maker Snapshot",
                ),
                (
                    "Submit Asset Movement",
                    "Asset Movement Approved",
                    "Asset Movement Submitted",
                    "Stock Manager",
                    "Connect Asset Movement Submit Authorization",
                ),
                (
                    "Cancel Asset Movement",
                    "Asset Movement Submitted",
                    "Asset Movement Cancelled",
                    "Stock Manager",
                    "Connect Asset Movement Cancel Authorization",
                ),
            ],
        )
        self.assertEqual(
            [row["action"] for row in route["transitions"] if row["allow_self_approval"]],
            ["Send Asset Movement for Review", "Resubmit Asset Movement"],
        )

    def test_workflows_are_active_and_manifest_complete(self) -> None:
        workflows: list[dict[str, Any]] = json.loads((FIXTURES / "workflow.json").read_text())
        manifest = json.loads(MANIFEST.read_text())
        routes = {route["id"]: route for route in manifest["routes"]}
        self.assertEqual(manifest["target_scope"], "DEV:local.test")
        self.assertFalse(manifest["records_are_inert"])
        self.assertEqual(manifest["activation_status"], "guarded-local-test-only")
        self.assertIn("workflow-state-field-setup", manifest["activation_prerequisites"])
        self.assertIn("executable-permission-contract", manifest["activation_prerequisites"])
        self.assertEqual(set(routes), {f"WF-{number:02d}" for number in range(1, 19)})
        self.assertEqual(routes["WF-08"]["status"], "disabled")
        self.assertIsNone(routes["WF-08"]["document_type"])
        self.assertIsNone(routes["WF-08"]["workflow"])
        self.assertEqual(routes["WF-12"]["status"], "trial-enabled-local-test")
        self.assertFalse(routes["WF-12"]["production_eligible"])
        self.assertTrue(all(workflow["is_active"] == 1 for workflow in workflows))
        self.assertTrue(all(len(workflow["states"]) >= 6 for workflow in workflows))
        self.assertTrue(all(len(workflow["transitions"]) >= 5 for workflow in workflows))
        self.assertNotIn("Salary Slip", {workflow["document_type"] for workflow in workflows})
        self.assertNotIn("Stock Count", {workflow["document_type"] for workflow in workflows})
        self.assertNotIn("Equipment", {workflow["document_type"] for workflow in workflows})
        self.assertNotIn("Asset", {workflow["document_type"] for workflow in workflows})
        self.assertNotIn("Material Request", {workflow["document_type"] for workflow in workflows})
        self.assertFalse(any("Equipment" in workflow["workflow_name"] for workflow in workflows))
        names = {route["workflow"] for route in routes.values() if route["workflow"]}
        names.update(name for route in routes.values() for name in route.get("workflow_names", []))
        self.assertEqual({workflow["name"] for workflow in workflows}, names)
        self.assertEqual(routes["WF-11"]["document_type"], "Purchase Order")
        self.assertEqual(routes["WF-11"]["workflow"], "Connect Purchase Order Blueprint")
        self.assertEqual(routes["WF-11"]["disabled_workflow"], "Connect Material Request Blueprint")
        self.assertTrue(
            all(
                route["document_type"] != "Credit Note" for route in routes.values() if route["document_type"]
            )
        )

    def test_companion_fixtures_are_referentially_integral(self) -> None:
        workflows: list[dict[str, Any]] = json.loads((FIXTURES / "workflow.json").read_text())
        states = {
            row["workflow_state_name"] for row in json.loads((FIXTURES / "workflow_state.json").read_text())
        }
        actions = {
            row["workflow_action_name"]
            for row in json.loads((FIXTURES / "workflow_action_master.json").read_text())
        }
        self_service_actions = {
            "Submit Emergency Stock Movement for Review",
            "Submit Stock Transfer for Approval",
            "Submit Purchase Invoice for Review",
            "Resubmit Purchase Invoice",
        }
        for workflow in workflows:
            self.assertTrue({row["state"] for row in workflow["states"]} <= states)
            self.assertTrue({row["next_state"] for row in workflow["transitions"]} <= states)
            self.assertTrue({row["action"] for row in workflow["transitions"]} <= actions)
            maker_self_actions = {
                ("Purchase Order", "Submit Purchase Order for Review"),
                ("Purchase Order", "Resubmit Purchase Order"),
            }
            self.assertTrue(
                all(
                    row["allow_self_approval"] == 0
                    for row in workflow["transitions"]
                    if row["action"].startswith(
                        ("Review ", "Return ", "Approve ", "Reject ", "Post ", "Cancel ")
                    )
                )
            )
        self.assertEqual(
            {
                row["action"]
                for workflow in workflows
                for row in workflow["transitions"]
                if row["allow_self_approval"] == 1
            },
            self_service_actions,
        )
        referenced_states = {row["state"] for workflow in workflows for row in workflow["states"]}
        referenced_states.update(
            row["next_state"] for workflow in workflows for row in workflow["transitions"]
        )
        referenced_actions = {row["action"] for workflow in workflows for row in workflow["transitions"]}
        self.assertEqual(states, referenced_states)
        self.assertEqual(actions, referenced_actions)

    def test_permission_blueprint_is_non_executable_and_unassigned(self) -> None:
        blueprint = json.loads(PERMISSIONS.read_text())
        self.assertFalse(blueprint["executable"])
        self.assertEqual(blueprint["assignments"], [])
        self.assertTrue(blueprint["rights"])

    def test_blueprints_have_no_threshold_conditions(self) -> None:
        workflows: list[dict[str, Any]] = json.loads((FIXTURES / "workflow.json").read_text())
        for workflow in workflows:
            for transition in workflow["transitions"]:
                condition = transition.get("condition")
                if workflow["document_type"] == "Stock Entry":
                    self.assertIn("doc.purpose == 'Material Transfer'", condition or "")
                    self.assertIn("not doc.add_to_transit", condition or "")
                    self.assertIn("not doc.outgoing_stock_entry", condition or "")
                elif workflow["document_type"] == "Sales Invoice":
                    self.assertIn(
                        condition,
                        {"doc.is_return and doc.return_against", "not doc.is_return"},
                    )
                    if condition == "not doc.is_return":
                        self.assertIn(transition["action"], {"Submit Sales Invoice", "Cancel Sales Invoice"})
                        self.assertIn(transition["allowed"], {"Accounts User", "Accounts Manager"})
                else:
                    self.assertFalse(condition)

    def test_payroll_entry_route_has_three_distinct_approval_stages(self) -> None:
        workflows: list[dict[str, Any]] = json.loads((FIXTURES / "workflow.json").read_text())
        workflow = next(row for row in workflows if row["document_type"] == "Payroll Entry")
        self.assertEqual(
            [(row["state"], row["doc_status"], row["allow_edit"]) for row in workflow["states"]],
            [
                ("Payroll Entry Draft", "0", "HR User"),
                ("Payroll Entry Pending Review", "0", "HR Manager"),
                ("Payroll Entry Reviewed", "0", "Accounts Manager"),
                ("Payroll Entry Returned", "0", "HR User"),
                ("Payroll Entry Approved", "0", "HR Manager"),
                ("Payroll Entry Rejected", "0", "HR User"),
                ("Payroll Entry Submitted", "1", "HR Manager"),
                ("Payroll Entry Cancelled", "2", "HR Manager"),
            ],
        )
        transitions = {
            row["action"]: (
                row["state"],
                row["next_state"],
                row["allowed"],
                row.get("transition_tasks"),
            )
            for row in workflow["transitions"]
        }
        self.assertEqual(
            transitions,
            {
                "Send Payroll Entry for Review": (
                    "Payroll Entry Draft",
                    "Payroll Entry Pending Review",
                    "HR User",
                    "Connect Payroll Entry Maker Snapshot",
                ),
                "Resubmit Payroll Entry for Review": (
                    "Payroll Entry Returned",
                    "Payroll Entry Pending Review",
                    "HR User",
                    "Connect Payroll Entry Maker Snapshot",
                ),
                "Review Payroll Entry": (
                    "Payroll Entry Pending Review",
                    "Payroll Entry Reviewed",
                    "HR Manager",
                    "Connect Payroll Entry Review Snapshot",
                ),
                "Return Payroll Entry": (
                    "Payroll Entry Pending Review",
                    "Payroll Entry Returned",
                    "HR Manager",
                    "Connect Payroll Entry Return Reset",
                ),
                "Approve Payroll Entry": (
                    "Payroll Entry Reviewed",
                    "Payroll Entry Approved",
                    "Accounts Manager",
                    "Connect Payroll Entry Approval Snapshot",
                ),
                "Reject Payroll Entry": (
                    "Payroll Entry Reviewed",
                    "Payroll Entry Rejected",
                    "Accounts Manager",
                    "Connect Payroll Entry Reject Reset",
                ),
                "Submit Payroll Entry": (
                    "Payroll Entry Approved",
                    "Payroll Entry Submitted",
                    "HR Manager",
                    "Connect Payroll Entry Submit Authorization",
                ),
                "Cancel Payroll Entry": (
                    "Payroll Entry Submitted",
                    "Payroll Entry Cancelled",
                    "HR Manager",
                    None,
                ),
            },
        )
