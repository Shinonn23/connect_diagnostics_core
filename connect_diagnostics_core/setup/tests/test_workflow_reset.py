# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Guardrails for the standard ERPNext workflow exports.

The app may export the explicitly approved workflows for ERPNext-owned
DocTypes, but it must not recreate workflows for any app-owned DocType or
resurrect the retired workflow definitions.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, ClassVar

from frappe.tests import UnitTestCase

from connect_diagnostics_core import hooks
from connect_diagnostics_core.setup import customer_onboarding, payroll, procure_to_pay, regulatory

MANIFEST = (
    Path(__file__).parents[3]
    / ".github"
    / "tasks"
    / "workflow-baseline-implementation"
    / "workflow-route-manifest.json"
)


class TestWorkflowReset(UnitTestCase):
    C_LEVEL_APPROVER_ROLE: ClassVar[str] = "C-Level Approver"
    APPROVER_ROLES: ClassVar[set[str]] = {
        "Stock Manager",
        "Accounts Manager",
        "Sales Manager",
        "Purchase Manager",
        "HR Manager",
        "C-Level Approver",
    }
    FLOW_ROLES: ClassVar[set[str]] = {
        "Stock User",
        "Stock Manager",
        "Accounts User",
        "Accounts Manager",
        "Sales User",
        "Sales Manager",
        "Purchase User",
        "Purchase Manager",
        "HR User",
        "HR Manager",
        "C-Level Approver",
    }

    def test_hooks_declare_only_approved_standard_workflows(self) -> None:
        fixture_doctypes = {
            entry["doctype"] if isinstance(entry, dict) else entry for entry in hooks.fixtures
        }
        self.assertTrue({"Workflow", "Workflow State", "Workflow Action Master"} <= fixture_doctypes)

        workflow_fixture = json.loads(
            Path(hooks.__file__).with_name("fixtures").joinpath("workflow.json").read_text()
        )
        manifest = json.loads(MANIFEST.read_text())
        expected_names = {route["workflow"] for route in manifest["routes"] if route.get("workflow")}
        expected_names.update(
            workflow for route in manifest["routes"] for workflow in route.get("workflow_names", [])
        )
        self.assertEqual(
            {workflow["workflow_name"] for workflow in workflow_fixture},
            expected_names,
        )
        self.assertNotIn("Connect Equipment Assignment Blueprint", expected_names)
        self.assertFalse(
            any("Equipment Assignment" in workflow["workflow_name"] for workflow in workflow_fixture)
        )
        self.assertTrue(all(workflow["is_active"] == 1 for workflow in workflow_fixture))

    def test_standard_workflow_fixture_does_not_target_app_doctypes(self) -> None:
        workflow_fixture = json.loads(
            Path(hooks.__file__).with_name("fixtures").joinpath("workflow.json").read_text()
        )
        app_doctypes = {
            "Stock Count",
            "Stock Count Adjustment",
            "Stock Count Item",
            "Stock Count Warehouse",
            "Borrowed Asset Return Inspection",
            "Borrowed Item Resolution",
            "Dispatch",
            "Dispatch Transfer",
            "Supplier Bank Change Request",
        }
        self.assertFalse(app_doctypes & {workflow["document_type"] for workflow in workflow_fixture})

    def test_standard_workflow_fixture_has_complete_docstatus_lifecycle(self) -> None:
        workflow_fixture = json.loads(
            Path(hooks.__file__).with_name("fixtures").joinpath("workflow.json").read_text()
        )
        for workflow in workflow_fixture:
            with self.subTest(workflow=workflow["workflow_name"]):
                states: list[dict[str, Any]] = workflow["states"]
                self.assertEqual({state["doc_status"] for state in states}, {"0", "1", "2"})
                self.assertEqual(workflow["workflow_state_field"], "workflow_state")
                self.assertTrue(
                    all(
                        transition["allow_self_approval"] == 0
                        for transition in workflow["transitions"]
                        if transition["action"].startswith(("Approve ", "Reject ", "Review ", "Post "))
                    )
                )

    def test_approval_transitions_are_c_level_controlled(self) -> None:
        workflow_fixture = json.loads(
            Path(hooks.__file__).with_name("fixtures").joinpath("workflow.json").read_text()
        )

        for workflow in workflow_fixture:
            doctype = workflow["document_type"]
            with self.subTest(doctype=doctype):
                for prefix in ("Approve ", "Reject "):
                    roles = {
                        transition["allowed"]
                        for transition in workflow["transitions"]
                        if transition["action"].startswith(prefix)
                    }
                    self.assertTrue(roles)
                    self.assertTrue(roles <= self.APPROVER_ROLES)
                self.assertTrue(
                    all(
                        transition["allow_self_approval"] == 0
                        for transition in workflow["transitions"]
                        if transition["action"].startswith(("Approve ", "Reject ", "Review ", "Post "))
                    )
                )

    def test_payment_approval_excludes_manager_roles(self) -> None:
        workflow = next(
            workflow
            for workflow in json.loads(
                Path(hooks.__file__).with_name("fixtures").joinpath("workflow.json").read_text()
            )
            if workflow["document_type"] == "Payment Entry"
        )
        approval_roles = {
            transition["allowed"]
            for transition in workflow["transitions"]
            if transition["action"].startswith(("Approve ", "Reject "))
        }
        self.assertEqual(approval_roles, {"C-Level Approver"})

    def test_workflow_email_and_desk_notifications_are_enabled(self) -> None:
        workflow_fixture = json.loads(
            Path(hooks.__file__).with_name("fixtures").joinpath("workflow.json").read_text()
        )

        for workflow in workflow_fixture:
            with self.subTest(workflow=workflow["workflow_name"]):
                self.assertIn(workflow["send_email_alert"], (0, 1))
                states = {state["state"]: state for state in workflow["states"]}
                pending = next(
                    state
                    for name, state in states.items()
                    if " Pending " in name or " Pending Review" in name
                )
                approved = next(state for name, state in states.items() if name.endswith(" Approved"))
                self.assertEqual(pending.get("send_email", 0), workflow["send_email_alert"])
                self.assertEqual(approved.get("send_email", 0), workflow["send_email_alert"])

    def test_rejection_is_terminal_and_not_editable_by_flow_roles(self) -> None:
        workflow_fixture = json.loads(
            Path(hooks.__file__).with_name("fixtures").joinpath("workflow.json").read_text()
        )
        for workflow in workflow_fixture:
            rejected_states = [
                state for state in workflow["states"] if state["state"].endswith((" Rejected", " Returned"))
            ]
            self.assertGreaterEqual(len(rejected_states), 1)
            for rejected in rejected_states:
                with self.subTest(state=rejected["state"]):
                    self.assertFalse(
                        [
                            transition
                            for transition in workflow["transitions"]
                            if transition["state"] == rejected["state"]
                            and not transition["action"].startswith("Resubmit ")
                        ]
                    )
                    self.assertIn(
                        rejected["allow_edit"],
                        self.FLOW_ROLES | {"System Manager", "All"},
                    )

    def test_revise_actions_and_transitions_are_removed(self) -> None:
        workflow_fixture = json.loads(
            Path(hooks.__file__).with_name("fixtures").joinpath("workflow.json").read_text()
        )
        action_fixture = json.loads(
            Path(hooks.__file__).with_name("fixtures").joinpath("workflow_action_master.json").read_text()
        )
        self.assertFalse(
            any(
                transition["action"].startswith("Revise ")
                for workflow in workflow_fixture
                for transition in workflow["transitions"]
            )
        )
        self.assertFalse(any(action["name"].startswith("Revise ") for action in action_fixture))

    def test_workflow_helper_module_is_removed(self) -> None:
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("connect_diagnostics_core.api.erpnext.workflow")

    def test_payment_approval_setup_module_is_removed(self) -> None:
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("connect_diagnostics_core.setup.payment_approval")

    def test_setup_modules_expose_no_workflow_provisioning(self) -> None:
        for module in (customer_onboarding, payroll, procure_to_pay, regulatory):
            for attr in ("ensure_workflow", "ensure_workflow_masters", "ensure_salary_slip_review_workflow"):
                self.assertFalse(
                    hasattr(module, attr),
                    msg=f"{module.__name__} still exposes {attr}",
                )
