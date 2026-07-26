# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe.model.document import Document
from frappe.permissions import setup_custom_perms

from connect_diagnostics_core.api.erpnext import dksh_item_mapping
from connect_diagnostics_core.setup import customer_onboarding

ITEM_DOCTYPE = "Item"
MAPPING_DOCTYPE = dksh_item_mapping.DKSH_ITEM_MAPPING_DOCTYPE
COORDINATOR_ROLE = dksh_item_mapping.DKSH_ITEM_COORDINATOR_ROLE

WORKFLOW_NAME = "DKSH Item Mapping Workflow"
WORKFLOW_STATE_FIELD = "mapping_state"

WORKFLOW_STATE_STYLES = {
    dksh_item_mapping.DRAFT_STATE: "",
    dksh_item_mapping.PENDING_COORDINATOR_REVIEW_STATE: "Warning",
    dksh_item_mapping.AWAITING_DKSH_CODE_STATE: "Warning",
    dksh_item_mapping.ACTIVE_STATE: "Success",
    dksh_item_mapping.RETURNED_FOR_CORRECTION_STATE: "Danger",
    dksh_item_mapping.REJECTED_STATE: "Danger",
}

WORKFLOW_STATES: tuple[dict[str, Any], ...] = (
    {"state": dksh_item_mapping.DRAFT_STATE, "doc_status": "0", "allow_edit": "Sales User", "send_email": 0},
    {
        "state": dksh_item_mapping.DRAFT_STATE,
        "doc_status": "0",
        "allow_edit": "Sales Manager",
        "send_email": 0,
    },
    {
        "state": dksh_item_mapping.PENDING_COORDINATOR_REVIEW_STATE,
        "doc_status": "0",
        "allow_edit": COORDINATOR_ROLE,
        "send_email": 0,
    },
    {
        "state": dksh_item_mapping.AWAITING_DKSH_CODE_STATE,
        "doc_status": "0",
        "allow_edit": COORDINATOR_ROLE,
        "send_email": 0,
    },
    {
        "state": dksh_item_mapping.ACTIVE_STATE,
        "doc_status": "0",
        "allow_edit": COORDINATOR_ROLE,
        "send_email": 0,
    },
    {
        "state": dksh_item_mapping.RETURNED_FOR_CORRECTION_STATE,
        "doc_status": "0",
        "allow_edit": "Sales User",
        "send_email": 0,
    },
    {
        "state": dksh_item_mapping.RETURNED_FOR_CORRECTION_STATE,
        "doc_status": "0",
        "allow_edit": "Sales Manager",
        "send_email": 0,
    },
    {
        "state": dksh_item_mapping.REJECTED_STATE,
        "doc_status": "0",
        "allow_edit": "Sales User",
        "send_email": 0,
    },
    {
        "state": dksh_item_mapping.REJECTED_STATE,
        "doc_status": "0",
        "allow_edit": "Sales Manager",
        "send_email": 0,
    },
)


def _transition(
    state: str, action: str, next_state: str, allowed: str, *, allow_self_approval: int = 0
) -> dict[str, Any]:
    return {
        "state": state,
        "action": action,
        "next_state": next_state,
        "allowed": allowed,
        "condition": "",
        "allow_self_approval": allow_self_approval,
        "send_email_to_creator": 0,
    }


WORKFLOW_TRANSITIONS: tuple[dict[str, Any], ...] = (
    _transition(
        dksh_item_mapping.DRAFT_STATE,
        "Send for DKSH coordinator review",
        dksh_item_mapping.PENDING_COORDINATOR_REVIEW_STATE,
        "Sales User",
        allow_self_approval=1,
    ),
    _transition(
        dksh_item_mapping.DRAFT_STATE,
        "Send for DKSH coordinator review",
        dksh_item_mapping.PENDING_COORDINATOR_REVIEW_STATE,
        "Sales Manager",
        allow_self_approval=1,
    ),
    _transition(
        dksh_item_mapping.RETURNED_FOR_CORRECTION_STATE,
        "Resubmit for DKSH coordinator review",
        dksh_item_mapping.PENDING_COORDINATOR_REVIEW_STATE,
        "Sales User",
        allow_self_approval=1,
    ),
    _transition(
        dksh_item_mapping.RETURNED_FOR_CORRECTION_STATE,
        "Resubmit for DKSH coordinator review",
        dksh_item_mapping.PENDING_COORDINATOR_REVIEW_STATE,
        "Sales Manager",
        allow_self_approval=1,
    ),
    _transition(
        dksh_item_mapping.PENDING_COORDINATOR_REVIEW_STATE,
        "Send request to DKSH",
        dksh_item_mapping.AWAITING_DKSH_CODE_STATE,
        COORDINATOR_ROLE,
    ),
    _transition(
        dksh_item_mapping.PENDING_COORDINATOR_REVIEW_STATE,
        "Return for correction",
        dksh_item_mapping.RETURNED_FOR_CORRECTION_STATE,
        COORDINATOR_ROLE,
    ),
    _transition(
        dksh_item_mapping.PENDING_COORDINATOR_REVIEW_STATE,
        "Reject DKSH Item Mapping",
        dksh_item_mapping.REJECTED_STATE,
        COORDINATOR_ROLE,
    ),
    _transition(
        dksh_item_mapping.AWAITING_DKSH_CODE_STATE,
        "Activate DKSH Item Mapping",
        dksh_item_mapping.ACTIVE_STATE,
        COORDINATOR_ROLE,
    ),
    _transition(
        dksh_item_mapping.AWAITING_DKSH_CODE_STATE,
        "Return for correction",
        dksh_item_mapping.RETURNED_FOR_CORRECTION_STATE,
        COORDINATOR_ROLE,
    ),
    _transition(
        dksh_item_mapping.AWAITING_DKSH_CODE_STATE,
        "Reject DKSH Item Mapping",
        dksh_item_mapping.REJECTED_STATE,
        COORDINATOR_ROLE,
    ),
)


def ensure_configuration() -> None:
    """Create the role, permissions, workflow masters, and Desk workflow idempotently."""
    ensure_coordinator_role()
    ensure_item_coordinator_permission()
    ensure_workflow_masters()
    customer_onboarding.ensure_workflow(
        workflow_name=WORKFLOW_NAME,
        document_type=MAPPING_DOCTYPE,
        workflow_state_field=WORKFLOW_STATE_FIELD,
        states=WORKFLOW_STATES,
        transitions=WORKFLOW_TRANSITIONS,
        send_email_alert=0,
    )
    frappe.clear_cache(doctype=MAPPING_DOCTYPE)
    frappe.clear_cache(doctype=ITEM_DOCTYPE)


def ensure_coordinator_role() -> None:
    if frappe.db.exists("Role", COORDINATOR_ROLE):
        role = cast(Document, frappe.get_doc("Role", COORDINATOR_ROLE))
        changed = False
        for fieldname, value in {"disabled": 0, "desk_access": 1, "is_custom": 1}.items():
            if role.get(fieldname) != value:
                role.set(fieldname, value)
                changed = True
        if changed:
            role.save(ignore_permissions=True)
        return
    frappe.get_doc(
        {
            "doctype": "Role",
            "role_name": COORDINATOR_ROLE,
            "disabled": 0,
            "desk_access": 1,
            "is_custom": 1,
        }
    ).insert(ignore_permissions=True)


def ensure_item_coordinator_permission() -> None:
    """Allow the coordinator to update the Item master before a DKSH request is sent."""
    setup_custom_perms(ITEM_DOCTYPE)
    matches = frappe.get_all(
        "Custom DocPerm",
        filters={"parent": ITEM_DOCTYPE, "role": COORDINATOR_ROLE, "permlevel": 0, "if_owner": 0},
        pluck="name",
        order_by="creation asc",
    )
    if matches:
        permission = cast(Document, frappe.get_doc("Custom DocPerm", matches[0]))
        for duplicate in matches[1:]:
            frappe.delete_doc("Custom DocPerm", duplicate, force=True, ignore_permissions=True)
    else:
        permission = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Custom DocPerm",
                    "parent": ITEM_DOCTYPE,
                    "role": COORDINATOR_ROLE,
                    "permlevel": 0,
                    "if_owner": 0,
                }
            ),
        )

    changed = permission.is_new()
    permissions = {"select": 1, "read": 1, "write": 1}
    for fieldname in customer_onboarding.PERMISSION_FIELDS:
        value = permissions.get(fieldname, 0)
        if permission.get(fieldname) != value:
            permission.set(fieldname, value)
            changed = True
    if not changed:
        return
    if permission.is_new():
        permission.insert(ignore_permissions=True)
    else:
        permission.save(ignore_permissions=True)


def ensure_workflow_masters() -> None:
    for state_name, style in WORKFLOW_STATE_STYLES.items():
        if frappe.db.exists("Workflow State", state_name):
            state = cast(Document, frappe.get_doc("Workflow State", state_name))
            if state.get("style") != style:
                state.set("style", style)
                state.save(ignore_permissions=True)
            continue
        frappe.get_doc(
            {
                "doctype": "Workflow State",
                "workflow_state_name": state_name,
                "style": style,
            }
        ).insert(ignore_permissions=True)

    actions = sorted({transition["action"] for transition in WORKFLOW_TRANSITIONS})
    for action_name in actions:
        if frappe.db.exists("Workflow Action Master", action_name):
            continue
        frappe.get_doc(
            {
                "doctype": "Workflow Action Master",
                "workflow_action_name": action_name,
            }
        ).insert(ignore_permissions=True)
