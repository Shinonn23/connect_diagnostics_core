# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from frappe.tests import UnitTestCase

ROOT = Path(__file__).parents[3]
FIXTURES = ROOT / "connect_diagnostics_core" / "fixtures"
MANIFEST = ROOT / ".github" / "tasks" / "workflow-baseline-implementation" / "workflow-route-manifest.json"
PERMISSIONS = ROOT / ".github" / "tasks" / "workflow-baseline-implementation" / "permission-blueprint.json"


class TestWorkflowFixtureBlueprints(UnitTestCase):
    def test_workflows_are_active_and_manifest_complete(self) -> None:
        workflows: list[dict[str, Any]] = json.loads((FIXTURES / "workflow.json").read_text())
        manifest = json.loads(MANIFEST.read_text())
        routes = {route["id"]: route for route in manifest["routes"]}
        self.assertEqual(manifest["target_scope"], "DEV:local.test")
        self.assertFalse(manifest["records_are_inert"])
        self.assertEqual(manifest["activation_status"], "enabled-on-dev")
        self.assertIn("workflow-state-field-setup", manifest["activation_prerequisites"])
        self.assertIn("executable-permission-contract", manifest["activation_prerequisites"])
        self.assertEqual(set(routes), {f"WF-{number:02d}" for number in range(1, 19)})
        self.assertEqual(routes["WF-08"]["status"], "disabled")
        self.assertIsNone(routes["WF-08"]["document_type"])
        self.assertIsNone(routes["WF-08"]["workflow"])
        self.assertTrue(all(workflow["is_active"] == 1 for workflow in workflows))
        self.assertTrue(all(len(workflow["states"]) >= 6 for workflow in workflows))
        self.assertTrue(all(len(workflow["transitions"]) >= 5 for workflow in workflows))
        self.assertNotIn("Salary Slip", {workflow["document_type"] for workflow in workflows})
        self.assertNotIn("Stock Count", {workflow["document_type"] for workflow in workflows})
        self.assertNotIn("Equipment", {workflow["document_type"] for workflow in workflows})
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
                    if (workflow["document_type"], row["action"]) not in maker_self_actions
                    and not row["action"].startswith("Submit ")
                )
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
                else:
                    self.assertFalse(condition)

    def test_purchase_order_has_three_distinct_role_stages_and_rework_paths(self) -> None:
        workflows: list[dict[str, Any]] = json.loads((FIXTURES / "workflow.json").read_text())
        workflow = next(row for row in workflows if row["document_type"] == "Purchase Order")
        transitions = {
            (row["state"], row["action"]): (row["next_state"], row["allowed"])
            for row in workflow["transitions"]
        }

        self.assertEqual(
            transitions[("Purchase Order Draft", "Submit Purchase Order for Review")],
            ("Purchase Order Pending Review", "Purchase User"),
        )
        self.assertEqual(
            transitions[("Purchase Order Pending Review", "Review Purchase Order")],
            ("Purchase Order Pending Approval", "Purchase Manager"),
        )
        self.assertEqual(
            transitions[("Purchase Order Pending Approval", "Approve Purchase Order")],
            ("Purchase Order Approved", "C-Level Approver"),
        )
        self.assertEqual(
            transitions[("Purchase Order Rejected", "Resubmit Purchase Order")],
            ("Purchase Order Pending Review", "Purchase User"),
        )
        maker_actions = {
            row["action"]: row["allow_self_approval"]
            for row in workflow["transitions"]
            if row["allowed"] == "Purchase User"
        }
        self.assertEqual(
            maker_actions,
            {
                "Submit Purchase Order for Review": 1,
                "Resubmit Purchase Order": 1,
            },
        )
        self.assertTrue(
            all(
                row["allow_self_approval"] == 0
                for row in workflow["transitions"]
                if row["allowed"] != "Purchase User"
            )
        )
