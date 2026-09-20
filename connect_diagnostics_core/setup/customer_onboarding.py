# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Credit approval configuration for Customer.

There is no Customer onboarding workflow. Sales saves a Customer and can sell to
it immediately; the master data a tax invoice needs is required when that invoice
is submitted, not before an order can be raised.

What is left here is the money: payment terms and credit limits stay behind the
Accounting Reviewer role, and everyone else asks for them through a
``Customer Credit Request``, which the Customer Credit Approver approves.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.permissions import setup_custom_perms

CUSTOMER_DOCTYPE = "Customer"
CREDIT_REQUEST_DOCTYPE = "Customer Credit Request"

CREDIT_REQUEST_WORKFLOW_NAME = "Customer Credit Request Approval"

CREDIT_REQUEST_WORKFLOW_STATE_FIELD = "credit_request_state"

CREDIT_REQUEST_DRAFT_STATE = "Customer Credit Request Draft"
PENDING_CREDIT_APPROVAL_STATE = "Pending Customer Credit Approval"
CREDIT_REQUEST_APPROVED_STATE = "Customer Credit Request Approved"
CREDIT_REQUEST_REJECTED_STATE = "Customer Credit Request Rejected"

ACCOUNTING_REVIEWER_ROLE = "Customer Accounting Reviewer"
CREDIT_APPROVER_ROLE = "Customer Credit Approver"

ACCOUNTING_REVIEWER_PROFILE = "Customer Accounting Reviewer Add-on"
CREDIT_APPROVER_PROFILE = "Customer Credit Approver Add-on"

VITTAYA_USER = "vittaya.ch@connectdiagnostics.com"
ARIRAT_USER = "arirat.ba@connectdiagnostics.com"

MANAGED_ROLES = (
    ACCOUNTING_REVIEWER_ROLE,
    CREDIT_APPROVER_ROLE,
)

ROLE_PROFILES = {
    ACCOUNTING_REVIEWER_PROFILE: (ACCOUNTING_REVIEWER_ROLE,),
    CREDIT_APPROVER_PROFILE: (CREDIT_APPROVER_ROLE,),
}

PERMISSION_FIELDS = (
    "select",
    "read",
    "write",
    "create",
    "delete",
    "submit",
    "cancel",
    "amend",
    "report",
    "export",
    "import",
    "share",
    "print",
    "email",
)

CUSTOMER_PERMISSION_COPY_MARKER = {
    "parent": CUSTOMER_DOCTYPE,
    "role": CREDIT_APPROVER_ROLE,
    "permlevel": 0,
    "if_owner": 1,
}

CUSTOMER_PERMISSIONS: dict[str, dict[str, int]] = {
    ACCOUNTING_REVIEWER_ROLE: {"read": 1, "write": 1},
    CREDIT_APPROVER_ROLE: {"read": 1},
}

CREDIT_REQUEST_WORKFLOW_STATES: tuple[dict[str, Any], ...] = (
    {
        "state": CREDIT_REQUEST_DRAFT_STATE,
        "doc_status": "0",
        "allow_edit": "Sales User",
        "send_email": 0,
    },
    {
        "state": CREDIT_REQUEST_DRAFT_STATE,
        "doc_status": "0",
        "allow_edit": "Sales Manager",
        "send_email": 0,
    },
    {
        "state": CREDIT_REQUEST_DRAFT_STATE,
        "doc_status": "0",
        "allow_edit": ACCOUNTING_REVIEWER_ROLE,
        "send_email": 0,
    },
    {
        "state": PENDING_CREDIT_APPROVAL_STATE,
        "doc_status": "0",
        "allow_edit": CREDIT_APPROVER_ROLE,
        "send_email": 1,
    },
    {
        "state": CREDIT_REQUEST_APPROVED_STATE,
        "doc_status": "1",
        "allow_edit": CREDIT_APPROVER_ROLE,
        "send_email": 0,
    },
    {
        "state": CREDIT_REQUEST_REJECTED_STATE,
        "doc_status": "0",
        "allow_edit": "Sales User",
        "send_email": 0,
    },
    {
        "state": CREDIT_REQUEST_REJECTED_STATE,
        "doc_status": "0",
        "allow_edit": "Sales Manager",
        "send_email": 0,
    },
)


def _transition(
    state: str,
    action: str,
    next_state: str,
    allowed: str,
    *,
    condition: str = "",
    allow_self_approval: int = 0,
) -> dict[str, Any]:
    return {
        "state": state,
        "action": action,
        "next_state": next_state,
        "allowed": allowed,
        "condition": condition,
        "allow_self_approval": allow_self_approval,
        "send_email_to_creator": 0,
    }


CREDIT_REQUEST_WORKFLOW_TRANSITIONS: tuple[dict[str, Any], ...] = (
    _transition(
        CREDIT_REQUEST_DRAFT_STATE,
        "Request credit approval",
        PENDING_CREDIT_APPROVAL_STATE,
        "Sales User",
        allow_self_approval=1,
    ),
    _transition(
        CREDIT_REQUEST_DRAFT_STATE,
        "Request credit approval",
        PENDING_CREDIT_APPROVAL_STATE,
        "Sales Manager",
        allow_self_approval=1,
    ),
    _transition(
        CREDIT_REQUEST_DRAFT_STATE,
        "Request credit approval",
        PENDING_CREDIT_APPROVAL_STATE,
        ACCOUNTING_REVIEWER_ROLE,
        allow_self_approval=1,
    ),
    _transition(
        PENDING_CREDIT_APPROVAL_STATE,
        "Approve credit request",
        CREDIT_REQUEST_APPROVED_STATE,
        CREDIT_APPROVER_ROLE,
    ),
    _transition(
        PENDING_CREDIT_APPROVAL_STATE,
        "Reject credit request",
        CREDIT_REQUEST_REJECTED_STATE,
        CREDIT_APPROVER_ROLE,
    ),
)

WORKFLOW_STATE_STYLES = {
    CREDIT_REQUEST_DRAFT_STATE: "",
    PENDING_CREDIT_APPROVAL_STATE: "Warning",
    CREDIT_REQUEST_APPROVED_STATE: "Success",
    CREDIT_REQUEST_REJECTED_STATE: "Danger",
}

WORKFLOW_ACTIONS = tuple(sorted({transition["action"] for transition in CREDIT_REQUEST_WORKFLOW_TRANSITIONS}))

STATE_COMPARISON_FIELDS = (
    "state",
    "doc_status",
    "allow_edit",
    "send_email",
    "update_field",
    "update_value",
    "evaluate_as_expression",
)
TRANSITION_COMPARISON_FIELDS = (
    "state",
    "action",
    "next_state",
    "allowed",
    "condition",
    "allow_self_approval",
    "send_email_to_creator",
)
CHECK_FIELDS = {
    "send_email",
    "evaluate_as_expression",
    "allow_self_approval",
    "send_email_to_creator",
}


def ensure_configuration() -> None:
    ensure_roles()
    ensure_role_profiles()
    ensure_customer_permissions()
    ensure_workflow_masters()
    ensure_workflow(
        workflow_name=CREDIT_REQUEST_WORKFLOW_NAME,
        document_type=CREDIT_REQUEST_DOCTYPE,
        workflow_state_field=CREDIT_REQUEST_WORKFLOW_STATE_FIELD,
        states=CREDIT_REQUEST_WORKFLOW_STATES,
        transitions=CREDIT_REQUEST_WORKFLOW_TRANSITIONS,
        send_email_alert=1,
        is_active=0,
    )
    assign_customer_role_holders(require_users=False)
    frappe.clear_cache(doctype=CUSTOMER_DOCTYPE)
    frappe.clear_cache(doctype=CREDIT_REQUEST_DOCTYPE)


def assign_customer_role_holders(*, require_users: bool = True) -> None:
    _assign_role_profile_or_direct_roles(
        VITTAYA_USER,
        ACCOUNTING_REVIEWER_PROFILE,
        require_user=require_users,
    )
    _assign_role_profile_or_direct_roles(
        ARIRAT_USER,
        CREDIT_APPROVER_PROFILE,
        require_user=require_users,
    )


def _assign_role_profile_or_direct_roles(
    user_name: str,
    role_profile: str,
    *,
    require_user: bool,
) -> bool:
    user = _get_enabled_user(user_name, required=require_user)
    if not user:
        return False

    current_profiles = {cast(str, row.role_profile) for row in user.get("role_profiles", [])}
    if current_profiles:
        if role_profile not in current_profiles:
            user.append("role_profiles", {"role_profile": role_profile})
            user.save(ignore_permissions=True)
        return True

    current_roles = {cast(str, row.role) for row in user.get("roles", [])}
    missing_roles = [role for role in ROLE_PROFILES[role_profile] if role not in current_roles]
    if not missing_roles:
        return True
    for role_name in missing_roles:
        user.append("roles", {"role": role_name})
    user.save(ignore_permissions=True)
    return True


def _get_enabled_user(user_name: str, *, required: bool) -> Document | None:
    if not frappe.db.exists("User", user_name):
        if required:
            frappe.throw(
                _("Required customer workflow User {0} does not exist.").format(frappe.bold(user_name)),
                title=_("Customer workflow setup failed"),
            )
        return None
    user = cast(Document, frappe.get_doc("User", user_name))
    if user.get("enabled"):
        return user
    if required:
        frappe.throw(
            _("Required customer workflow User {0} is disabled.").format(frappe.bold(user_name)),
            title=_("Customer workflow setup failed"),
        )
    return None


def ensure_roles() -> None:
    for role_name in MANAGED_ROLES:
        if frappe.db.exists("Role", role_name):
            role = cast(Document, frappe.get_doc("Role", role_name))
            changed = False
            for fieldname, value in {"disabled": 0, "desk_access": 1, "is_custom": 1}.items():
                if role.get(fieldname) != value:
                    role.set(fieldname, value)
                    changed = True
            if changed:
                role.save(ignore_permissions=True)
            continue
        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": role_name,
                "disabled": 0,
                "desk_access": 1,
                "is_custom": 1,
            }
        ).insert(ignore_permissions=True)


def ensure_role_profiles() -> None:
    for profile_name, role_names in ROLE_PROFILES.items():
        if frappe.db.exists("Role Profile", profile_name):
            profile = cast(Document, frappe.get_doc("Role Profile", profile_name))
            current_roles = tuple(sorted(cast(str, row.role) for row in profile.get("roles", [])))
            desired_roles = tuple(sorted(role_names))
            if current_roles == desired_roles:
                continue
            profile.set("roles", [])
            for role_name in role_names:
                profile.append("roles", {"role": role_name})
            profile.save(ignore_permissions=True)
            continue
        frappe.get_doc(
            {
                "doctype": "Role Profile",
                "role_profile": profile_name,
                "roles": [{"role": role_name} for role_name in role_names],
            }
        ).insert(ignore_permissions=True)


def ensure_customer_permissions() -> None:
    if setup_custom_perms(CUSTOMER_DOCTYPE):
        _ensure_customer_permission_copy_marker()

    for role_name, permissions in CUSTOMER_PERMISSIONS.items():
        matches = frappe.get_all(
            "Custom DocPerm",
            filters={"parent": CUSTOMER_DOCTYPE, "role": role_name, "permlevel": 0, "if_owner": 0},
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
                        "parent": CUSTOMER_DOCTYPE,
                        "role": role_name,
                        "permlevel": 0,
                        "if_owner": 0,
                    }
                ),
            )

        changed = permission.is_new()
        for fieldname in PERMISSION_FIELDS:
            value = permissions.get(fieldname, 0)
            if permission.get(fieldname) != value:
                permission.set(fieldname, value)
                changed = True
        if not changed:
            continue
        if permission.is_new():
            permission.insert(ignore_permissions=True)
        else:
            permission.save(ignore_permissions=True)


def _ensure_customer_permission_copy_marker() -> None:
    if frappe.db.exists("Custom DocPerm", CUSTOMER_PERMISSION_COPY_MARKER):
        return
    frappe.get_doc(
        {
            "doctype": "Custom DocPerm",
            **CUSTOMER_PERMISSION_COPY_MARKER,
            **{fieldname: 0 for fieldname in PERMISSION_FIELDS},
        }
    ).insert(ignore_permissions=True)


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

    for action_name in WORKFLOW_ACTIONS:
        if not frappe.db.exists("Workflow Action Master", action_name):
            frappe.get_doc(
                {
                    "doctype": "Workflow Action Master",
                    "workflow_action_name": action_name,
                }
            ).insert(ignore_permissions=True)


def ensure_workflow(
    *,
    workflow_name: str,
    document_type: str,
    workflow_state_field: str,
    states: Sequence[dict[str, Any]],
    transitions: Sequence[dict[str, Any]],
    send_email_alert: int,
    is_active: int,
) -> None:
    if is_active:
        conflicting_workflows = frappe.get_all(
            "Workflow",
            filters={"document_type": document_type, "is_active": 1, "name": ["!=", workflow_name]},
            pluck="name",
        )
        if conflicting_workflows:
            frappe.throw(
                _("Cannot activate {0}; {1} is already active for {2}.").format(
                    workflow_name,
                    ", ".join(conflicting_workflows),
                    document_type,
                )
            )

    if frappe.db.exists("Workflow", workflow_name):
        workflow = cast(Document, frappe.get_doc("Workflow", workflow_name))
    else:
        workflow = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Workflow",
                    "workflow_name": workflow_name,
                    "document_type": document_type,
                }
            ),
        )

    changed = workflow.is_new()
    scalar_values = {
        "document_type": document_type,
        "is_active": is_active,
        "override_status": 0,
        "send_email_alert": send_email_alert,
        "enable_action_confirmation": 1,
        "workflow_state_field": workflow_state_field,
    }
    for fieldname, value in scalar_values.items():
        if workflow.get(fieldname) != value:
            workflow.set(fieldname, value)
            changed = True
    if not _child_rows_match(workflow.get("states", []), states, STATE_COMPARISON_FIELDS):
        workflow.set("states", list(states))
        changed = True
    if not _child_rows_match(workflow.get("transitions", []), transitions, TRANSITION_COMPARISON_FIELDS):
        workflow.set("transitions", list(transitions))
        changed = True
    if not changed:
        return
    if workflow.is_new():
        workflow.insert(ignore_permissions=True)
    else:
        workflow.save(ignore_permissions=True)


def _child_rows_match(
    current_rows: Sequence[Any], desired_rows: Sequence[dict[str, Any]], fields: Sequence[str]
) -> bool:
    return _normalize_rows(current_rows, fields) == _normalize_rows(desired_rows, fields)


def _normalize_rows(rows: Sequence[Any], fields: Sequence[str]) -> list[tuple[Any, ...]]:
    normalized: list[tuple[Any, ...]] = []
    for row in rows:
        values: list[Any] = []
        for fieldname in fields:
            value = row.get(fieldname)
            values.append(int(value or 0) if fieldname in CHECK_FIELDS else value or "")
        normalized.append(tuple(values))
    return normalized
