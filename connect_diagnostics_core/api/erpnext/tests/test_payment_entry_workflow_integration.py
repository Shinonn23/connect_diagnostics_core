# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Live configuration checks for the native Payment Entry approval route."""

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase


class TestPaymentEntryWorkflowIntegration(IntegrationTestCase):
    def test_canonical_route_and_transition_tasks_are_live(self) -> None:
        self.assertEqual(frappe.local.site, "local.test")
        workflow = frappe.get_doc("Workflow", "Connect Payment Entry Approval")
        self.assertEqual(workflow.document_type, "Payment Entry")
        self.assertEqual(workflow.is_active, 1)
        self.assertEqual(
            {row.state for row in workflow.states},
            {
                "Payment Entry Draft",
                "Payment Entry Pending Review",
                "Payment Entry Reviewed",
                "Payment Entry Approved",
                "Payment Entry Submitted",
                "Payment Entry Returned",
                "Payment Entry Rejected",
                "Payment Entry Cancelled",
            },
        )
        task_names = {row.transition_tasks for row in workflow.transitions if row.transition_tasks}
        self.assertEqual(
            task_names,
            {
                "Connect Payment Entry Capture Maker",
                "Connect Payment Entry Capture Checker",
                "Connect Payment Entry Capture Approver",
                "Connect Payment Entry Clear Approval",
                "Connect Payment Entry Submit Execution",
                "Connect Payment Entry Cancel Execution",
            },
        )
        for name in task_names:
            task_doc = frappe.get_doc("Workflow Transition Tasks", name)
            self.assertEqual(len(task_doc.tasks), 1)
            self.assertEqual(task_doc.tasks[0].task, name)
            self.assertEqual(task_doc.tasks[0].enabled, 1)
