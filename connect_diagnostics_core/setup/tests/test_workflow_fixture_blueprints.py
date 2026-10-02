# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any
from unittest.mock import patch

from frappe.model.base_document import _get_extended_class
from frappe.tests import UnitTestCase

from connect_diagnostics_core import hooks
from connect_diagnostics_core.api.frappe.approval_routes import get_route
from connect_diagnostics_core.api.hrms import payroll_output_review as payroll_output
from connect_diagnostics_core.patches.v1_0 import normalize_workflow_baseline as v4
from connect_diagnostics_core.patches.v1_0 import upgrade_workflow_baseline_v5 as v5

ROOT = Path(__file__).parents[3]
FIXTURES = ROOT / "connect_diagnostics_core" / "fixtures"
MANIFEST = ROOT / ".github" / "tasks" / "workflow-baseline-implementation" / "workflow-route-manifest.json"
PERMISSIONS = ROOT / ".github" / "tasks" / "workflow-baseline-implementation" / "permission-blueprint.json"


class TestWorkflowFixtureBlueprints(UnitTestCase):
    def test_v5_fixture_adds_only_approved_purchase_order_return(self) -> None:
        current = v5._current_blueprint()
        archived = v4._blueprint()[0]
        self.assertEqual(set(current), set(archived))
        for name in current:
            rows = current[name]["transitions"]
            old_rows = archived[name]["transitions"]
            if name == v5.PURCHASE_ORDER_WORKFLOW:
                self.assertEqual(len(rows), len(old_rows) + 1)
                added = [row for row in rows if row not in old_rows]
                self.assertEqual(added, [v5.RETURN_TRANSITION])
            else:
                self.assertEqual(v4.workflow_shape(current[name]), v4.workflow_shape(archived[name]))

    def test_migrate_guards_validate_current_baseline_before_and_after_sync(self) -> None:
        guard = "connect_diagnostics_core.patches.v1_0.upgrade_workflow_baseline_v5.preflight"
        verify = "connect_diagnostics_core.patches.v1_0.upgrade_workflow_baseline_v5.verify"
        obsolete = (
            "connect_diagnostics_core.patches.v1_0.add_purchase_invoice_approval_controls."
            "validate_installed_configuration"
        )
        self.assertEqual(hooks.before_migrate[0], guard)
        self.assertEqual(hooks.after_migrate[-1], verify)
        self.assertEqual(hooks.after_sync[-1], verify)
        self.assertNotIn(obsolete, hooks.after_migrate)

    def test_install_prepares_baseline_before_fixtures_and_configures_after_sync(self) -> None:
        self.assertEqual(
            hooks.after_install,
            [
                "connect_diagnostics_core.patches.v1_0.normalize_workflow_baseline.execute",
                "connect_diagnostics_core.patches.v1_0.upgrade_workflow_baseline_v5.prepare",
            ],
        )
        configuration = [
            "connect_diagnostics_core.setup.after_install",
            "connect_diagnostics_core.setup.storage_location.ensure_configuration",
            "connect_diagnostics_core.setup.repost_item_valuation.ensure_configuration",
            "connect_diagnostics_core.setup.employee.ensure_configuration",
            "connect_diagnostics_core.setup.print_action_fields.apply_configuration",
            "connect_diagnostics_core.setup.asset_movement_item.apply_configuration",
            "connect_diagnostics_core.setup.asset_installation.apply_configuration",
            "connect_diagnostics_core.setup.asset_disposal.apply_configuration",
            "connect_diagnostics_core.setup.tds.apply_configuration",
        ]
        self.assertEqual(
            hooks.after_sync,
            [
                *configuration,
                "connect_diagnostics_core.setup.after_sync",
                "connect_diagnostics_core.patches.v1_0.upgrade_workflow_baseline_v5.verify",
            ],
        )
        for callback in configuration:
            self.assertNotIn(callback, hooks.after_install)
        self.assertIn("connect_diagnostics_core.setup.asset_disposal.preflight", hooks.before_install)
        self.assertIn("connect_diagnostics_core.setup.asset_disposal.preflight", hooks.before_migrate)
        self.assertIn(
            "connect_diagnostics_core.setup.asset_disposal.apply_configuration", hooks.after_migrate
        )

    def test_production_workflow_hooks_compose_without_shadowing(self) -> None:
        self.assertEqual(
            hooks.extend_doctype_class["Payroll Entry"],
            [
                "connect_diagnostics_core.api.hrms.payroll_entry_workflow.PayrollEntryWorkflowMixin",
                "connect_diagnostics_core.api.hrms.payroll_entry_workflow.PayrollEntryApprovalMixin",
            ],
        )
        self.assertIn("Asset", hooks.extend_doctype_class)
        self.assertEqual(
            hooks.extend_doctype_class["Asset"],
            [
                "connect_diagnostics_core.api.erpnext.asset_movement_workflow.AssetMovementNativeMixin",
                "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.AssetDisposalNativeMixin",
            ],
        )
        self.assertEqual(
            hooks.extend_doctype_class["Asset Finance Book"],
            "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.AssetDisposalFinanceBookMixin",
        )
        self.assertEqual(
            hooks.extend_doctype_class["Sales Invoice"],
            ["connect_diagnostics_core.api.erpnext.asset_disposal_workflow.AssetDisposalSalesInvoiceMixin"],
        )
        self.assertIn("Asset Movement", hooks.extend_doctype_class)
        self.assertIn("Journal Entry", hooks.extend_doctype_class)
        self.assertIn("Asset Value Adjustment", hooks.extend_doctype_class)
        self.assertIn("Process Deferred Accounting", hooks.extend_doctype_class)
        self.assertEqual(
            hooks.doc_events["Stock Entry"]["before_cancel"],
            [
                "connect_diagnostics_core.api.erpnext.stock_entry_workflow.validate_before_cancel",
                "connect_diagnostics_core.api.erpnext.material_request.before_cancel_movement",
                "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.validate_transaction",
            ],
        )
        self.assertEqual(
            hooks.doc_events["Payroll Entry"],
            {
                "validate": "connect_diagnostics_core.api.hrms.payroll_entry_workflow.validate_workflow",
                "before_submit": "connect_diagnostics_core.api.hrms.payroll_entry_workflow.validate_before_submit",
                "on_trash": "connect_diagnostics_core.api.frappe.workflow_action_cleanup.delete_linked_actions",
            },
        )
        self.assertEqual(
            hooks.doc_events["Purchase Order"]["validate"].count(
                "connect_diagnostics_core.api.erpnext.purchase_order_workflow.validate_workflow"
            ),
            1,
        )
        self.assertEqual(
            hooks.permission_query_conditions,
            {
                "Material Request Fulfillment": "connect_diagnostics_core.api.erpnext.material_request_fulfillment.get_permission_query_conditions"
            },
        )

    def test_frappes_reversed_mro_preserves_both_payroll_behaviors(self) -> None:
        class NativePayroll:
            def create_salary_slips(self) -> str:
                return "native-slips"

            def make_journal_entry(self, **kwargs: Any) -> dict[str, Any]:
                return kwargs

        with patch(
            "frappe.get_hooks", return_value={"Payroll Entry": hooks.extend_doctype_class["Payroll Entry"]}
        ):
            extended = _get_extended_class(NativePayroll, "Payroll Entry")
        with patch(
            "connect_diagnostics_core.api.hrms.payroll_output_review.create_salary_slips",
            return_value="native-slips",
        ) as create_slips:
            payroll = extended()
            payroll.name = "_Test Payroll Entry"
            self.assertEqual(payroll.create_salary_slips(), "native-slips")
            with payroll_output.native_operation(payroll.name, "bank_regular"):
                self.assertEqual(
                    payroll.make_journal_entry(submit_journal_entry=True)["submit_journal_entry"], False
                )
        create_slips.assert_called_once_with(payroll)
        self.assertEqual(extended.__mro__[1].__name__, "PayrollEntryApprovalMixin")
        self.assertEqual(extended.__mro__[2].__name__, "PayrollEntryWorkflowMixin")

    def test_normalized_callbacks_resolve_and_production_handlers_are_registered(self) -> None:
        methods = {row["name"]: row["method"] for row in hooks.workflow_methods}
        self.assertEqual(len(methods), len(hooks.workflow_methods))
        self.assertEqual(
            methods["Connect Stock Transfer Reject"],
            "connect_diagnostics_core.api.erpnext.stock_entry_workflow.reject_approval",
        )
        for name, dotted in hooks._normalized_workflow_methods.items():
            self.assertEqual(methods[name], dotted)
            module, callback = dotted.rsplit(".", 1)
            self.assertTrue(callable(getattr(import_module(module), callback)), name)
        self.assertEqual(
            hooks.doc_events["Sales Order"]["before_cancel"],
            "connect_diagnostics_core.api.erpnext.sales_order_workflow.validate_sales_order_before_cancel",
        )
        self.assertEqual(
            hooks.doc_events["Sales Order"]["on_submit"],
            "connect_diagnostics_core.api.erpnext.auto_invoice_generation.enqueue_sales_order_service_group",
        )
        self.assertEqual(
            hooks.doc_events["Delivery Note"]["on_submit"],
            "connect_diagnostics_core.api.erpnext.auto_invoice_generation.enqueue_delivery_note_stock_groups",
        )
        self.assertEqual(
            hooks.doc_events["Sales Invoice"]["before_insert"],
            "connect_diagnostics_core.api.erpnext.auto_invoice_generation.before_insert_sales_invoice_generation",
        )
        self.assertEqual(
            hooks.extend_doctype_class["Sales Invoice"],
            ["connect_diagnostics_core.api.erpnext.asset_disposal_workflow.AssetDisposalSalesInvoiceMixin"],
        )
        self.assertEqual(
            hooks.doc_events["Sales Invoice"]["validate"],
            [
                "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.validate_approval_fields",
                "connect_diagnostics_core.api.erpnext.auto_invoice_generation.validate_sales_invoice_generation",
            ],
        )
        self.assertEqual(
            hooks.doc_events["Sales Invoice"]["before_submit"][:2],
            [
                "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.guard_disposal_sales_invoice_submit",
                "connect_diagnostics_core.api.erpnext.auto_invoice_generation.before_submit_sales_invoice_generation",
            ],
        )
        self.assertEqual(
            hooks.doc_events["Sales Invoice"]["on_submit"],
            [
                "connect_diagnostics_core.api.erpnext.sales_invoice.on_submit_demo_sales_invoice",
                "connect_diagnostics_core.api.erpnext.auto_invoice_generation.on_submit_sales_invoice_generation",
            ],
        )
        self.assertEqual(
            hooks.doc_events["Sales Invoice"]["on_cancel"],
            [
                "connect_diagnostics_core.api.erpnext.sales_invoice.on_cancel_demo_sales_invoice",
                "connect_diagnostics_core.api.erpnext.auto_invoice_generation.on_cancel_sales_invoice_generation",
            ],
        )
        self.assertEqual(
            hooks.doc_events["Sales Invoice"]["before_cancel"][0],
            "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.guard_disposal_sales_invoice_cancel",
        )
        self.assertEqual(
            hooks.doc_events["Asset"]["before_update_after_submit"],
            [
                "connect_diagnostics_core.api.erpnext.asset_installation.validate_customer_update",
                "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.guard_asset_disposal_save",
            ],
        )
        self.assertEqual(
            hooks.doc_events["Asset Depreciation Schedule"]["before_save"],
            "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.guard_asset_depreciation_schedule_change",
        )
        self.assertEqual(
            hooks.doc_events["Journal Entry"]["before_insert"],
            "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.before_insert_generated_disposal_journal_entry",
        )
        self.assertEqual(
            hooks.doc_events["Journal Entry"]["after_insert"],
            "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.after_insert_generated_disposal_journal_entry",
        )
        self.assertEqual(
            hooks.doc_events["Journal Entry"]["before_submit"][0],
            "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.guard_disposal_journal_entry_submit",
        )
        self.assertEqual(
            hooks.doc_events["Journal Entry"]["before_cancel"][0],
            "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.guard_disposal_journal_entry_cancel",
        )
        self.assertEqual(
            hooks.doc_events["Journal Entry"]["on_submit"],
            [
                "connect_diagnostics_core.api.erpnext.journal_entry_generators.complete_approved_generated_source",
                "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.complete_disposal_journal_entry_submit",
            ],
        )
        self.assertEqual(
            hooks.override_whitelisted_methods["erpnext.assets.doctype.asset.depreciation.scrap_asset"],
            "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.scrap_asset",
        )
        self.assertEqual(
            hooks.override_whitelisted_methods["erpnext.assets.doctype.asset.depreciation.restore_asset"],
            "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.restore_asset",
        )
        self.assertEqual(
            hooks.doc_events["Payment Entry"]["before_cancel"],
            "connect_diagnostics_core.api.erpnext.payment_entry_workflow.validate_before_cancel",
        )
        self.assertFalse({name for name in methods if "Sales Order Demo" in name})

    def test_workflow_action_cleanup_hooks_are_exact(self) -> None:
        cleanup = "connect_diagnostics_core.api.frappe.workflow_action_cleanup.delete_linked_actions"
        expected: dict[str, str | list[str]] = {
            name: cleanup
            for name in (
                "Journal Entry",
                "Payment Entry",
                "Payroll Entry",
                "Purchase Invoice",
                "Purchase Order",
                "Sales Invoice",
                "Sales Order",
                "Stock Entry",
            )
        }
        expected["Asset Movement"] = [
            "connect_diagnostics_core.api.erpnext.asset_installation.prevent_history_deletion",
            cleanup,
        ]
        expected["Stock Reconciliation"] = [
            "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.lock_reconciliation_scope_on_trash",
            cleanup,
        ]
        actual = {
            doctype: events["on_trash"]
            for doctype, events in hooks.doc_events.items()
            if cleanup
            in (
                events.get("on_trash", [])
                if isinstance(events.get("on_trash"), list)
                else [events.get("on_trash")]
            )
        }
        self.assertEqual(actual, expected)

    def test_asset_movement_runtime_hooks_are_exact(self) -> None:
        self.assertEqual(
            hooks.extend_doctype_class["Asset"],
            [
                "connect_diagnostics_core.api.erpnext.asset_movement_workflow.AssetMovementNativeMixin",
                "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.AssetDisposalNativeMixin",
            ],
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
                    "connect_diagnostics_core.api.erpnext.asset_movement_acceptance.validate_receipt_evidence",
                    "connect_diagnostics_core.api.erpnext.asset_installation.validate_draft_evidence",
                ],
                "before_update_after_submit": [
                    "connect_diagnostics_core.api.erpnext.asset_movement_workflow.validate_after_submit_update",
                    "connect_diagnostics_core.api.erpnext.asset_movement_acceptance.validate_receipt_evidence",
                    "connect_diagnostics_core.api.erpnext.asset_installation.validate_draft_evidence",
                ],
                "before_submit": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.validate_before_submit",
                "before_cancel": [
                    "connect_diagnostics_core.api.erpnext.asset_movement_workflow.validate_before_cancel",
                    "connect_diagnostics_core.api.erpnext.material_request.before_cancel_movement",
                ],
                "on_cancel": "connect_diagnostics_core.api.erpnext.asset_installation.restore_after_cancel",
                "on_trash": [
                    "connect_diagnostics_core.api.erpnext.asset_installation.prevent_history_deletion",
                    "connect_diagnostics_core.api.frappe.workflow_action_cleanup.delete_linked_actions",
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
        self.assertEqual(
            manifest["activation_status"], "not-imported-pending-guard-and-local-test-acceptance"
        )
        self.assertIn("workflow-state-field-setup", manifest["activation_prerequisites"])
        self.assertIn("executable-permission-contract", manifest["activation_prerequisites"])
        self.assertEqual(set(routes), {f"WF-{number:02d}" for number in range(1, 19)})
        self.assertEqual(routes["WF-08"]["status"], "pending-business-process")
        self.assertIsNone(routes["WF-08"]["document_type"])
        self.assertIsNone(routes["WF-08"]["workflow"])
        self.assertEqual(routes["WF-12"]["status"], "trial-policy-blocked")
        self.assertFalse(routes["WF-12"]["production_accepted"])
        self.assertEqual(routes["WF-07"]["status"], "pending-protected-adapter")
        self.assertIsNone(routes["WF-07"]["workflow"])
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
        names.add(manifest["accounting_dependency"]["workflow"])
        names.add(manifest["stock_reconciliation_dependency"]["workflow"])
        self.assertEqual({workflow["name"] for workflow in workflows}, names)
        self.assertEqual(manifest["stock_reconciliation_dependency"]["status"], "source-checkpoint-only")
        self.assertFalse(manifest["stock_reconciliation_dependency"]["production_accepted"])
        self.assertEqual(routes["WF-11"]["document_type"], "Purchase Order")
        self.assertEqual(routes["WF-11"]["workflow"], "Connect Purchase Order Blueprint")
        for route_id in ("WF-04", "WF-05"):
            route = routes[route_id]
            self.assertEqual(route["document_type"], "Stock Entry")
            self.assertIsNone(route["workflow"])
            self.assertFalse(route["source_checkpoint_importable"])
            self.assertFalse(route["production_accepted"])
            self.assertIn("Material Receipt/Issue", route["remaining_gap"])
            self.assertIn(
                "independently approved" if route_id == "WF-04" else "independent approval",
                route["remaining_gap"],
            )
        self.assertFalse(any(route["production_accepted"] for route in routes.values()))
        self.assertEqual(len(workflows), 10)
        self.assertEqual(len({workflow["document_type"] for workflow in workflows}), 10)
        self.assertTrue(
            all(
                route["document_type"] != "Credit Note" for route in routes.values() if route["document_type"]
            )
        )

    def test_companion_fixtures_are_referentially_integral(self) -> None:
        workflows: list[dict[str, Any]] = json.loads((FIXTURES / "workflow.json").read_text())
        state_rows: list[dict[str, Any]] = json.loads((FIXTURES / "workflow_state.json").read_text())
        action_rows: list[dict[str, Any]] = json.loads((FIXTURES / "workflow_action_master.json").read_text())
        states = {row["workflow_state_name"] for row in state_rows}
        actions = {row["workflow_action_name"] for row in action_rows}
        self.assertEqual(len(states), len(state_rows))
        self.assertEqual(len(actions), len(action_rows))
        self.assertEqual({row["name"] for row in state_rows}, states)
        self.assertEqual({row["name"] for row in action_rows}, actions)
        self.assertEqual(len({row["name"] for row in state_rows}), len(state_rows))
        self.assertEqual(len({row["name"] for row in action_rows}), len(action_rows))
        for row in state_rows:
            self.assertEqual(row["name"], row["workflow_state_name"])
            self.assertEqual(row["doctype"], "Workflow State")
        for row in action_rows:
            self.assertEqual(row["name"], row["workflow_action_name"])
            self.assertEqual(row["doctype"], "Workflow Action Master")
        registered_tasks = {row["name"] for row in hooks.workflow_methods}
        for workflow in workflows:
            self.assertTrue({row["state"] for row in workflow["states"]} <= states)
            self.assertTrue({row["next_state"] for row in workflow["transitions"]} <= states)
            self.assertTrue({row["action"] for row in workflow["transitions"]} <= actions)
            keys = [
                (row["action"], row["state"], row["next_state"], row["allowed"])
                for row in workflow["transitions"]
            ]
            self.assertEqual(len(keys), len(set(keys)), workflow["name"])
            action_role_keys = [
                (row["state"], row["action"], row["allowed"]) for row in workflow["transitions"]
            ]
            self.assertEqual(len(action_role_keys), len(set(action_role_keys)), workflow["name"])
            effects_by_action: dict[tuple[str, str], set[tuple[Any, ...]]] = {}
            for row in workflow["transitions"]:
                action_key = (row["state"], row["action"])
                effects_by_action.setdefault(action_key, set()).add(
                    (
                        row["next_state"],
                        row.get("condition"),
                        row.get("transition_tasks"),
                        row["allow_self_approval"],
                    )
                )
            for effects in effects_by_action.values():
                self.assertEqual(len(effects), 1, workflow["name"])
            statuses = {row["state"]: row["doc_status"] for row in workflow["states"]}
            for row in workflow["transitions"]:
                self.assertIn(row["state"], statuses)
                self.assertIn(row["next_state"], statuses)
                self.assertGreaterEqual(int(statuses[row["next_state"]]), int(statuses[row["state"]]))
                if row.get("transition_tasks"):
                    self.assertIn(row["transition_tasks"], registered_tasks)
                if row["action"].startswith(("Review ", "Approve ", "Reject ", "Return ", "Verify ")):
                    self.assertEqual(row["allow_self_approval"], 0)
        referenced_states = {row["state"] for workflow in workflows for row in workflow["states"]}
        referenced_states.update(
            row["next_state"] for workflow in workflows for row in workflow["transitions"]
        )
        referenced_actions = {row["action"] for workflow in workflows for row in workflow["transitions"]}
        self.assertEqual(states, referenced_states)
        self.assertEqual(actions, referenced_actions)

    def test_credit_maker_roles_have_equivalent_routes_and_locked_reviewed_states(self) -> None:
        workflows: list[dict[str, Any]] = json.loads((FIXTURES / "workflow.json").read_text())
        credit = next(row for row in workflows if row["document_type"] == "Sales Invoice")
        route = get_route("sales_invoice_credit_note")
        self.assertEqual(set(route.maker_roles), {"Sales User", "Accounts User"})
        states = {row["state"]: row["allow_edit"] for row in credit["states"]}
        self.assertEqual(states["Sales Invoice Credit Pending Review"], "All")
        self.assertEqual(states["Sales Invoice Credit Returned"], "All")
        self.assertEqual(states["Sales Invoice Credit Reviewed"], "Accounts Manager")
        self.assertEqual(states["Sales Invoice Credit Approved"], "Accounts Manager")
        for state, action, target, task in (
            (
                "Sales Invoice Draft",
                route.send_action,
                route.pending_review_state,
                "Connect Sales Invoice Credit Send",
            ),
            (
                route.returned_state,
                "Resubmit Sales Invoice Credit for Review",
                route.pending_review_state,
                "Connect Sales Invoice Credit Resubmit",
            ),
        ):
            rows = [row for row in credit["transitions"] if row["state"] == state and row["action"] == action]
            self.assertEqual({row["allowed"] for row in rows}, set(route.maker_roles))
            self.assertEqual(
                {
                    (
                        row["next_state"],
                        row.get("condition"),
                        row.get("transition_tasks"),
                        row["allow_self_approval"],
                    )
                    for row in rows
                },
                {(target, "doc.is_return and doc.return_against", task, 1)},
            )
        for row in credit["transitions"]:
            if row["action"] in {
                "Review Sales Invoice Credit",
                "Return Sales Invoice Credit",
                "Approve Sales Invoice Credit",
                "Reject Sales Invoice Credit",
                "Post Sales Invoice Credit",
            }:
                self.assertNotIn(row["allowed"], route.maker_roles)
                self.assertEqual(row["allow_self_approval"], 0)

    def test_permission_blueprint_is_executable_and_unassigned(self) -> None:
        blueprint = json.loads(PERMISSIONS.read_text())
        self.assertTrue(blueprint["executable"])
        self.assertEqual(blueprint["assignments"], [])
        self.assertTrue(blueprint["rights"])

    def test_blueprints_have_no_threshold_conditions(self) -> None:
        workflows: list[dict[str, Any]] = json.loads((FIXTURES / "workflow.json").read_text())
        for workflow in workflows:
            for transition in workflow["transitions"]:
                condition = transition.get("condition")
                if workflow["document_type"] == "Stock Entry":
                    if transition["action"] in {"Submit Stock Entry", "Cancel Stock Entry"}:
                        self.assertEqual(condition, "doc.purpose != 'Material Transfer'")
                    else:
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
        stock = next(row for row in workflows if row["document_type"] == "Stock Entry")
        self.assertEqual(
            {
                row["state"]: row["allow_edit"]
                for row in stock["states"]
                if row["state"].startswith("Stock Entry ")
            },
            {"Stock Entry Draft": "All", "Stock Entry Submitted": "All", "Stock Entry Cancelled": "All"},
        )

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
            (
                row["action"],
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
                (
                    "Send Payroll Entry for Review",
                    "Payroll Entry Draft",
                    "Payroll Entry Pending Review",
                    "HR User",
                    "Connect Payroll Entry Capture Maker",
                ),
                (
                    "Resubmit Payroll Entry for Review",
                    "Payroll Entry Returned",
                    "Payroll Entry Pending Review",
                    "HR User",
                    "Connect Payroll Entry Capture Maker",
                ),
                (
                    "Review Payroll Entry",
                    "Payroll Entry Pending Review",
                    "Payroll Entry Reviewed",
                    "HR Manager",
                    "Connect Payroll Entry Capture Review",
                ),
                (
                    "Return Payroll Entry",
                    "Payroll Entry Pending Review",
                    "Payroll Entry Returned",
                    "HR Manager",
                    "Reset Payroll Entry Review",
                ),
                (
                    "Return Payroll Entry",
                    "Payroll Entry Reviewed",
                    "Payroll Entry Returned",
                    "Accounts Manager",
                    "Reset Payroll Entry Review",
                ),
                (
                    "Approve Payroll Entry",
                    "Payroll Entry Reviewed",
                    "Payroll Entry Approved",
                    "Accounts Manager",
                    "Connect Payroll Entry Capture Approval",
                ),
                (
                    "Reject Payroll Entry",
                    "Payroll Entry Reviewed",
                    "Payroll Entry Rejected",
                    "Accounts Manager",
                    "Reset Payroll Entry Approval",
                ),
                (
                    "Submit Payroll Entry",
                    "Payroll Entry Approved",
                    "Payroll Entry Submitted",
                    "HR Manager",
                    "Connect Payroll Entry Submit Execution",
                ),
                (
                    "Cancel Payroll Entry",
                    "Payroll Entry Submitted",
                    "Payroll Entry Cancelled",
                    "HR Manager",
                    None,
                ),
            },
        )

    def test_reviewed_routes_match_approved_registry_contract(self) -> None:
        workflows = {
            row["document_type"]: row for row in json.loads((FIXTURES / "workflow.json").read_text())
        }
        protected_tasks = {
            "stock_entry_material_transfer": (
                "Connect Stock Transfer Maker Snapshot",
                "Connect Stock Transfer Review Snapshot",
                "Connect Stock Transfer Approval Snapshot",
                "Connect Stock Transfer Submit Execution",
            ),
            "stock_reconciliation": (
                "Connect Stock Reconciliation Capture Maker",
                "Connect Stock Reconciliation Capture Review",
                "Connect Stock Reconciliation Capture Approval",
                "Connect Stock Reconciliation Submit Execution",
            ),
            "asset_movement": (
                "Connect Asset Movement Maker Snapshot",
                "Connect Asset Movement Review Snapshot",
                "Connect Asset Movement Approval Snapshot",
                "Connect Asset Movement Submit Authorization",
            ),
            "manual_journal_entry": (
                "Connect Journal Entry Capture Maker",
                "Connect Journal Entry Capture Checker",
                "Connect Journal Entry Capture Approver",
                "Connect Journal Entry Submit Execution",
            ),
            "sales_order_credit": (
                "Connect Sales Order Capture Maker",
                "Connect Sales Order Capture Review",
                "Connect Sales Order Capture Approval",
                "Connect Sales Order Submit Execution",
            ),
            "sales_invoice_credit_note": (
                "Connect Sales Invoice Credit Send",
                "Connect Sales Invoice Credit Review",
                "Connect Sales Invoice Credit Approve",
                "Connect Sales Invoice Credit Post",
            ),
            "purchase_order": (
                "Connect Purchase Order Maker",
                "Connect Purchase Order Review",
                "Connect Purchase Order Approval",
                "Connect Purchase Order Submit",
            ),
            "purchase_invoice": (
                "Connect Purchase Invoice Maker",
                "Connect Purchase Invoice Source Verification",
                "Connect Purchase Invoice Accounting Approval",
                "Connect Purchase Invoice Submit",
            ),
            "payment_entry": (
                "Connect Payment Entry Capture Maker",
                "Connect Payment Entry Capture Checker",
                "Connect Payment Entry Capture Approver",
                "Connect Payment Entry Submit Execution",
            ),
            "payroll_entry": (
                "Connect Payroll Entry Capture Maker",
                "Connect Payroll Entry Capture Review",
                "Connect Payroll Entry Capture Approval",
                "Connect Payroll Entry Submit Execution",
            ),
        }
        for key in (
            "stock_entry_material_transfer",
            "stock_reconciliation",
            "asset_movement",
            "manual_journal_entry",
            "sales_order_credit",
            "sales_invoice_credit_note",
            "purchase_order",
            "purchase_invoice",
            "payment_entry",
            "payroll_entry",
        ):
            route = get_route(key)
            workflow = workflows[route.doctype]
            actions = {row["action"] for row in workflow["transitions"]}
            states = {row["state"] for row in workflow["states"]}
            with self.subTest(route=key):
                self.assertIn(route.draft_state, states)
                self.assertIn(route.approved_state, states)
                self.assertIn(route.submitted_state, states)
                self.assertIn(route.send_action, actions)
                self.assertIn(route.review_action, actions)
                self.assertIn(route.approve_action, actions)
                self.assertIn(route.execute_action, actions)
                expected = (
                    (route.send_action, route.draft_state, route.pending_review_state, route.maker_roles[0]),
                    (
                        route.review_action,
                        route.pending_review_state,
                        route.reviewed_state,
                        route.reviewer_roles[0],
                    ),
                    (
                        route.approve_action,
                        route.reviewed_state,
                        route.approved_state,
                        route.final_approver_roles[0],
                    ),
                    (
                        route.execute_action,
                        route.approved_state,
                        route.submitted_state,
                        route.execution_roles[0],
                    ),
                )
                for (action, source, target, role), task in zip(expected, protected_tasks[key], strict=True):
                    self.assertEqual(
                        [
                            row["transition_tasks"]
                            for row in workflow["transitions"]
                            if (row["action"], row["state"], row["next_state"], row["allowed"])
                            == (action, source, target, role)
                        ],
                        [task],
                    )
