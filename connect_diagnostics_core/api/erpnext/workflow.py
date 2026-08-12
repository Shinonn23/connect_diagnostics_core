# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


def has_active_workflow(document_type: str) -> bool:
    """Return whether Frappe has an active workflow for a document type."""
    active_workflow = frappe.db.get_value(
        "Workflow",
        {"document_type": document_type, "is_active": 1},
        "name",
    )
    if active_workflow:
        return True
    inactive_workflow = frappe.db.get_value(
        "Workflow",
        {"document_type": document_type, "is_active": 0},
        "name",
    )
    if not inactive_workflow:
        frappe.throw(_("Workflow configuration is missing for {0}.").format(document_type))
    return False


def finalize_if_workflow_inactive(
    doc: Document,
    state_field: str,
    final_state: str,
) -> bool:
    """Apply the configured final state when approval is intentionally bypassed."""
    if has_active_workflow(doc.doctype):
        return False
    doc.set(state_field, final_state)
    return True


def initialize_workflow_state(doc: Document) -> None:
    """Initialize a new document from the active Workflow's first draft state."""
    if not doc.is_new():
        return
    workflow_name = frappe.db.get_value(
        "Workflow",
        {"document_type": doc.doctype, "is_active": 1},
        "name",
    )
    if not workflow_name:
        return
    workflow = frappe.get_doc("Workflow", workflow_name)
    state_field = workflow.get("workflow_state_field")
    if not state_field or doc.get(state_field):
        return
    initial_states = [state for state in workflow.get("states", []) if str(state.get("doc_status")) == "0"]
    if initial_states:
        doc.set(state_field, initial_states[0].get("state"))
