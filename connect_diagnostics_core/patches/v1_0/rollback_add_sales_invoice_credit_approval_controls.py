# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _

from connect_diagnostics_core.patches.v1_0.add_sales_invoice_credit_approval_controls import (
    DESIRED_STATES,
    DESIRED_TRANSITIONS,
    SNAPSHOT_FILE,
    WORKFLOW,
    _fingerprint,
    _load_snapshot,
)


def execute() -> None:
    if frappe.db.exists(
        "Workflow Action",
        {"reference_doctype": "Sales Invoice", "status": ["in", ["Open", "Completed"]]},
    ):
        frappe.throw(_("Sales Invoice credit Workflow has used actions; rollback stopped."))
    if frappe.db.exists(
        "Sales Invoice",
        {"is_return": 1, "return_against": ["is", "set"]},
    ):
        frappe.throw(_("Sales Invoice credit note history prevents rollback."))
    if not frappe.db.exists("Workflow", WORKFLOW):
        frappe.throw(_("Sales Invoice credit Workflow is missing; rollback stopped."))
    current = frappe.get_doc("Workflow", WORKFLOW)
    if _fingerprint(current) != (DESIRED_STATES, DESIRED_TRANSITIONS):
        frappe.throw(_("Sales Invoice credit Workflow is not the exact active target; rollback stopped."))
    snapshot = _load_snapshot()
    if not snapshot:
        frappe.throw(_("Legacy Sales Invoice credit Workflow snapshot is missing; rollback stopped."))
        return
    if not isinstance(snapshot, dict):
        frappe.throw(_("Legacy Sales Invoice credit Workflow snapshot is invalid; rollback stopped."))
        return
    if (
        snapshot.get("schema") != 1
        or snapshot.get("site") != frappe.local.site
        or not isinstance(snapshot.get("workflow"), dict)
    ):
        frappe.throw(_("Legacy Sales Invoice credit Workflow snapshot is invalid; rollback stopped."))
        return
    prior = snapshot.get("workflow")
    if not isinstance(prior, dict):
        frappe.throw(_("Legacy Sales Invoice credit Workflow snapshot is invalid; rollback stopped."))
        return
    if prior.get("doctype") != "Workflow" or prior.get("name") != WORKFLOW:
        frappe.throw(_("Legacy Sales Invoice credit Workflow snapshot is invalid; rollback stopped."))
    current.set("states", [_restore_child(row) for row in prior.get("states") or []])
    current.set("transitions", [_restore_child(row) for row in prior.get("transitions") or []])
    current.enable_action_confirmation = prior.get("enable_action_confirmation") or 0
    current.override_status = prior.get("override_status") or 0
    current.send_email_alert = prior.get("send_email_alert") or 0
    current.workflow_state_field = prior.get("workflow_state_field") or "workflow_state"
    current.save(ignore_permissions=True)


def _restore_child(row: dict[str, object]) -> dict[str, object]:
    identity_fields = {
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "idx",
        "parent",
        "parentfield",
        "parenttype",
        "doctype",
    }
    return {key: value for key, value in row.items() if key not in identity_fields}
