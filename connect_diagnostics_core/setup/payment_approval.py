# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.permissions import reset_perms, setup_custom_perms

COMPANY_DOCTYPE = "Company"
PAYMENT_ENTRY_DOCTYPE = "Payment Entry"
PAYMENT_REQUEST_DOCTYPE = "Payment Request"
WORKFLOW_NAME = "Payment Request Approval"
LEGACY_WORKFLOW_NAME = "Payment Entry Approval"
WORKFLOW_STATE_FIELD = "payment_approval_state"
APPROVAL_DUE_AT_FIELD = "approval_due_at"
BASE_GRAND_TOTAL_FIELD = "base_grand_total"
PAYMENT_APPROVAL_LIMIT_FIELD = "payment_approval_limit"
LOW_VALUE_PAYMENT_APPROVAL_LIMIT_FIELD = "low_value_payment_approval_limit"

PRIMARY_APPROVER_ROLE = "Payment Approver - Primary"
SECONDARY_APPROVER_ROLE = "Payment Approver - Secondary"
LOW_VALUE_APPROVER_ROLE = "Payment Approver - Low Value"
ESCALATION_ROLE = "Payment Approval Escalation"

PRIMARY_APPROVER_PROFILE = "Executive Payment Approver - Primary Add-on"
SECONDARY_APPROVER_PROFILE = "Executive Payment Approver - Secondary Add-on"
LOW_VALUE_APPROVER_PROFILE = "Accounting Payment Approver Add-on"

PRIMARY_APPROVER_USER = "arirat.ba@connectdiagnostics.com"
SECONDARY_APPROVER_USER = "sasin.ba@connectdiagnostics.com"
LOW_VALUE_APPROVER_USER = "sopha.su@connectdiagnostics.com"

DRAFT_STATE = "Payment Request Draft"
SUBMITTED_STATE = "Payment Request Submitted"
PENDING_LOW_VALUE_STATE = "Pending Low-Value Payment Request Approval"
PENDING_PRIMARY_STATE = "Pending Primary Payment Request Approval"
ESCALATED_LOW_VALUE_STATE = "Escalated Low-Value Payment Request Approval"
ESCALATED_PRIMARY_STATE = "Escalated Payment Request Approval"
APPROVED_STATE = "Payment Request Approved"
REJECTED_STATE = "Payment Request Rejected"
CANCELLED_STATE = "Payment Request Cancelled"

REQUEST_APPROVAL_ACTION = "Request Payment Approval"
APPROVE_ACTION = "Approve Payment Request"
REJECT_ACTION = "Reject Payment Request"
REVISE_ACTION = "Revise Payment Request"
ESCALATE_ACTION = "Escalate Payment Request Approval"
SUBMIT_INWARD_ACTION = "Submit Payment Request"

LOW_VALUE_CONDITION = (
    'doc.payment_request_type == "Outward" '
    f'and (frappe.db.get_value("Company", doc.company, "{LOW_VALUE_PAYMENT_APPROVAL_LIMIT_FIELD}") '
    f"or 0) > 0 and doc.{BASE_GRAND_TOTAL_FIELD} < "
    f'(frappe.db.get_value("Company", doc.company, "{LOW_VALUE_PAYMENT_APPROVAL_LIMIT_FIELD}") or 0)'
)
PRIMARY_VALUE_CONDITION = (
    'doc.payment_request_type == "Outward" and ('
    f'(frappe.db.get_value("Company", doc.company, "{LOW_VALUE_PAYMENT_APPROVAL_LIMIT_FIELD}") '
    f"or 0) <= 0 or doc.{BASE_GRAND_TOTAL_FIELD} >= "
    f'(frappe.db.get_value("Company", doc.company, "{LOW_VALUE_PAYMENT_APPROVAL_LIMIT_FIELD}") or 0))'
)
LOW_VALUE_SNAPSHOT_CONDITION = (
    f"(doc.{PAYMENT_APPROVAL_LIMIT_FIELD} or 0) > 0 and "
    f"doc.{BASE_GRAND_TOTAL_FIELD} < doc.{PAYMENT_APPROVAL_LIMIT_FIELD}"
)
PRIMARY_SNAPSHOT_CONDITION = (
    f"(doc.{PAYMENT_APPROVAL_LIMIT_FIELD} or 0) <= 0 or "
    f"doc.{BASE_GRAND_TOTAL_FIELD} >= doc.{PAYMENT_APPROVAL_LIMIT_FIELD}"
)
INWARD_CONDITION = 'doc.payment_request_type == "Inward"'
ESCALATION_DUE_CONDITION = (
    "doc.approval_due_at and frappe.utils.get_datetime(doc.approval_due_at) <= frappe.utils.now_datetime()"
)

CUSTOM_FIELDS = {
    COMPANY_DOCTYPE: [
        {
            "fieldname": LOW_VALUE_PAYMENT_APPROVAL_LIMIT_FIELD,
            "label": "Low Value Payment Approval Limit",
            "fieldtype": "Currency",
            "options": "default_currency",
            "insert_after": "default_currency",
            "non_negative": 1,
        }
    ],
    PAYMENT_REQUEST_DOCTYPE: [
        {
            "fieldname": WORKFLOW_STATE_FIELD,
            "label": "Payment Approval State",
            "fieldtype": "Link",
            "options": "Workflow State",
            "insert_after": "status",
            "allow_on_submit": 1,
            "hidden": 1,
            "no_copy": 1,
        },
        {
            "fieldname": APPROVAL_DUE_AT_FIELD,
            "label": "Approval Due At",
            "fieldtype": "Datetime",
            "insert_after": WORKFLOW_STATE_FIELD,
            "read_only": 1,
            "no_copy": 1,
            "search_index": 1,
        },
        {
            "fieldname": BASE_GRAND_TOTAL_FIELD,
            "label": "Amount (Company Currency)",
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "insert_after": "grand_total",
            "read_only": 1,
            "no_copy": 1,
            "depends_on": 'eval:doc.payment_request_type == "Outward"',
        },
        {
            "fieldname": PAYMENT_APPROVAL_LIMIT_FIELD,
            "label": "Payment Approval Limit",
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "insert_after": BASE_GRAND_TOTAL_FIELD,
            "read_only": 1,
            "no_copy": 1,
            "depends_on": 'eval:doc.payment_request_type == "Outward"',
        },
    ],
}

MANAGED_ROLES = (
    PRIMARY_APPROVER_ROLE,
    SECONDARY_APPROVER_ROLE,
    LOW_VALUE_APPROVER_ROLE,
    ESCALATION_ROLE,
)

ROLE_PROFILES = {
    PRIMARY_APPROVER_PROFILE: (PRIMARY_APPROVER_ROLE, LOW_VALUE_APPROVER_ROLE),
    SECONDARY_APPROVER_PROFILE: (SECONDARY_APPROVER_ROLE,),
    LOW_VALUE_APPROVER_PROFILE: (LOW_VALUE_APPROVER_ROLE,),
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
PERMISSION_COMPARISON_FIELDS = ("role", "permlevel", "if_owner", *PERMISSION_FIELDS, "mask")

APPROVER_PAYMENT_REQUEST_PERMISSIONS = {fieldname: 0 for fieldname in PERMISSION_FIELDS}
APPROVER_PAYMENT_REQUEST_PERMISSIONS.update(
    {
        "read": 1,
        "write": 1,
        "submit": 1,
    }
)

PAYMENT_REQUEST_PERMISSIONS = {
    PRIMARY_APPROVER_ROLE: APPROVER_PAYMENT_REQUEST_PERMISSIONS,
    SECONDARY_APPROVER_ROLE: APPROVER_PAYMENT_REQUEST_PERMISSIONS,
    LOW_VALUE_APPROVER_ROLE: APPROVER_PAYMENT_REQUEST_PERMISSIONS,
}

PERMISSION_COPY_MARKER = {
    "parent": PAYMENT_REQUEST_DOCTYPE,
    "role": ESCALATION_ROLE,
    "permlevel": 0,
    "if_owner": 1,
}
LEGACY_PERMISSION_COPY_MARKER = {
    "parent": PAYMENT_ENTRY_DOCTYPE,
    "role": ESCALATION_ROLE,
    "permlevel": 0,
    "if_owner": 1,
}

WORKFLOW_STATES: tuple[dict[str, Any], ...] = (
    {"state": DRAFT_STATE, "doc_status": "0", "allow_edit": "Accounts User", "send_email": 0},
    {"state": DRAFT_STATE, "doc_status": "0", "allow_edit": "Accounts Manager", "send_email": 0},
    {"state": SUBMITTED_STATE, "doc_status": "1", "allow_edit": "Accounts Manager", "send_email": 0},
    {
        "state": PENDING_LOW_VALUE_STATE,
        "doc_status": "0",
        "allow_edit": LOW_VALUE_APPROVER_ROLE,
        "send_email": 1,
    },
    {
        "state": PENDING_PRIMARY_STATE,
        "doc_status": "0",
        "allow_edit": PRIMARY_APPROVER_ROLE,
        "send_email": 1,
    },
    {
        "state": ESCALATED_LOW_VALUE_STATE,
        "doc_status": "0",
        "allow_edit": LOW_VALUE_APPROVER_ROLE,
        "send_email": 1,
    },
    {
        "state": ESCALATED_LOW_VALUE_STATE,
        "doc_status": "0",
        "allow_edit": SECONDARY_APPROVER_ROLE,
        "send_email": 1,
    },
    {
        "state": ESCALATED_PRIMARY_STATE,
        "doc_status": "0",
        "allow_edit": PRIMARY_APPROVER_ROLE,
        "send_email": 1,
    },
    {
        "state": ESCALATED_PRIMARY_STATE,
        "doc_status": "0",
        "allow_edit": SECONDARY_APPROVER_ROLE,
        "send_email": 1,
    },
    {"state": APPROVED_STATE, "doc_status": "1", "allow_edit": "Accounts Manager", "send_email": 0},
    {"state": REJECTED_STATE, "doc_status": "0", "allow_edit": "Accounts User", "send_email": 0},
    {"state": REJECTED_STATE, "doc_status": "0", "allow_edit": "Accounts Manager", "send_email": 0},
    {"state": CANCELLED_STATE, "doc_status": "2", "allow_edit": "Accounts Manager", "send_email": 0},
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


def _maker_transitions(state: str, action: str) -> tuple[dict[str, Any], ...]:
    transitions: list[dict[str, Any]] = []
    for role in ("Accounts User", "Accounts Manager"):
        transitions.extend(
            (
                _transition(
                    state,
                    action,
                    PENDING_LOW_VALUE_STATE,
                    role,
                    condition=LOW_VALUE_CONDITION,
                    allow_self_approval=1,
                ),
                _transition(
                    state,
                    action,
                    PENDING_PRIMARY_STATE,
                    role,
                    condition=PRIMARY_VALUE_CONDITION,
                    allow_self_approval=1,
                ),
            )
        )
    return tuple(transitions)


WORKFLOW_TRANSITIONS: tuple[dict[str, Any], ...] = (
    *_maker_transitions(DRAFT_STATE, REQUEST_APPROVAL_ACTION),
    _transition(
        DRAFT_STATE,
        SUBMIT_INWARD_ACTION,
        SUBMITTED_STATE,
        "Accounts Manager",
        condition=INWARD_CONDITION,
        allow_self_approval=1,
    ),
    _transition(
        PENDING_LOW_VALUE_STATE,
        APPROVE_ACTION,
        APPROVED_STATE,
        LOW_VALUE_APPROVER_ROLE,
        condition=LOW_VALUE_SNAPSHOT_CONDITION,
    ),
    _transition(PENDING_LOW_VALUE_STATE, REJECT_ACTION, REJECTED_STATE, LOW_VALUE_APPROVER_ROLE),
    _transition(
        PENDING_LOW_VALUE_STATE,
        ESCALATE_ACTION,
        ESCALATED_LOW_VALUE_STATE,
        ESCALATION_ROLE,
        condition=ESCALATION_DUE_CONDITION,
        allow_self_approval=1,
    ),
    _transition(
        PENDING_PRIMARY_STATE,
        APPROVE_ACTION,
        APPROVED_STATE,
        PRIMARY_APPROVER_ROLE,
        condition=PRIMARY_SNAPSHOT_CONDITION,
    ),
    _transition(PENDING_PRIMARY_STATE, REJECT_ACTION, REJECTED_STATE, PRIMARY_APPROVER_ROLE),
    _transition(
        PENDING_PRIMARY_STATE,
        ESCALATE_ACTION,
        ESCALATED_PRIMARY_STATE,
        ESCALATION_ROLE,
        condition=ESCALATION_DUE_CONDITION,
        allow_self_approval=1,
    ),
    _transition(
        ESCALATED_LOW_VALUE_STATE,
        APPROVE_ACTION,
        APPROVED_STATE,
        LOW_VALUE_APPROVER_ROLE,
        condition=LOW_VALUE_SNAPSHOT_CONDITION,
    ),
    _transition(ESCALATED_LOW_VALUE_STATE, REJECT_ACTION, REJECTED_STATE, LOW_VALUE_APPROVER_ROLE),
    _transition(
        ESCALATED_LOW_VALUE_STATE,
        APPROVE_ACTION,
        APPROVED_STATE,
        SECONDARY_APPROVER_ROLE,
        condition=LOW_VALUE_SNAPSHOT_CONDITION,
    ),
    _transition(ESCALATED_LOW_VALUE_STATE, REJECT_ACTION, REJECTED_STATE, SECONDARY_APPROVER_ROLE),
    _transition(
        ESCALATED_PRIMARY_STATE,
        APPROVE_ACTION,
        APPROVED_STATE,
        PRIMARY_APPROVER_ROLE,
        condition=PRIMARY_SNAPSHOT_CONDITION,
    ),
    _transition(ESCALATED_PRIMARY_STATE, REJECT_ACTION, REJECTED_STATE, PRIMARY_APPROVER_ROLE),
    _transition(
        ESCALATED_PRIMARY_STATE,
        APPROVE_ACTION,
        APPROVED_STATE,
        SECONDARY_APPROVER_ROLE,
        condition=PRIMARY_SNAPSHOT_CONDITION,
    ),
    _transition(ESCALATED_PRIMARY_STATE, REJECT_ACTION, REJECTED_STATE, SECONDARY_APPROVER_ROLE),
    *_maker_transitions(REJECTED_STATE, REVISE_ACTION),
)

WORKFLOW_STATE_STYLES = {
    DRAFT_STATE: "",
    SUBMITTED_STATE: "Success",
    PENDING_LOW_VALUE_STATE: "Warning",
    PENDING_PRIMARY_STATE: "Warning",
    ESCALATED_LOW_VALUE_STATE: "Danger",
    ESCALATED_PRIMARY_STATE: "Danger",
    APPROVED_STATE: "Success",
    REJECTED_STATE: "Danger",
    CANCELLED_STATE: "Danger",
}

WORKFLOW_ACTIONS = (
    REQUEST_APPROVAL_ACTION,
    APPROVE_ACTION,
    REJECT_ACTION,
    REVISE_ACTION,
    ESCALATE_ACTION,
    SUBMIT_INWARD_ACTION,
)

LEGACY_WORKFLOW_STATE_STYLES = {
    "Payment Draft": "",
    "Payment Submitted": "Success",
    "Pending Low-Value Payment Approval": "Warning",
    "Pending Primary Payment Approval": "Warning",
    "Escalated Low-Value Payment Approval": "Danger",
    "Escalated Payment Approval": "Danger",
    "Payment Approved": "Success",
    "Payment Rejected": "Danger",
    "Payment Cancelled": "Danger",
}
LEGACY_WORKFLOW_ACTIONS = (
    REQUEST_APPROVAL_ACTION,
    "Approve Payment",
    "Reject Payment",
    "Revise Payment",
    "Escalate Payment Approval",
    "Submit Payment Entry",
)

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
    ensure_payment_request_permissions()
    ensure_workflow_masters()
    ensure_workflow()
    assign_payment_approvers(require_users=False)
    frappe.clear_cache(doctype=COMPANY_DOCTYPE)
    frappe.clear_cache(doctype=PAYMENT_REQUEST_DOCTYPE)


def assign_payment_approvers(
    primary_user: str = PRIMARY_APPROVER_USER,
    secondary_user: str = SECONDARY_APPROVER_USER,
    low_value_user: str = LOW_VALUE_APPROVER_USER,
    *,
    require_users: bool = True,
) -> None:
    assignments = (
        (primary_user, PRIMARY_APPROVER_PROFILE),
        (low_value_user, LOW_VALUE_APPROVER_PROFILE),
        (secondary_user, SECONDARY_APPROVER_PROFILE),
    )
    unavailable_count = 0
    for user_name, role_profile in assignments:
        if not _assign_role_profile_or_direct_roles(
            user_name,
            role_profile,
            require_user=require_users,
        ):
            unavailable_count += 1

    if unavailable_count:
        frappe.logger(__name__).warning(
            "Skipped %s payment approver assignments because required Users are missing or disabled",
            unavailable_count,
        )


def _assign_role_profile_or_direct_roles(
    user_name: str,
    role_profile: str,
    *,
    require_user: bool = True,
) -> bool:
    user = _get_enabled_user(user_name, required=require_user)
    if not user:
        return False

    current_profiles = {cast(str, row.role_profile) for row in user.get("role_profiles", [])}
    if current_profiles:
        if role_profile in current_profiles:
            return True
        user.append("role_profiles", {"role_profile": role_profile})
        user.save(ignore_permissions=True)
        return True

    current_roles = {cast(str, row.role) for row in user.get("roles", [])}
    missing_roles = [role for role in ROLE_PROFILES[role_profile] if role not in current_roles]
    if not missing_roles:
        return True
    for role in missing_roles:
        user.append("roles", {"role": role})
    user.save(ignore_permissions=True)
    return True


def _get_enabled_user(user_name: str, *, required: bool = True) -> Document | None:
    if not frappe.db.exists("User", user_name):
        if not required:
            return None
        frappe.throw(
            _("Required payment approver User {0} does not exist.").format(frappe.bold(user_name)),
            title=_("Payment approver setup failed"),
        )
    user = cast(Document, frappe.get_doc("User", user_name))
    if user.get("enabled"):
        return user
    if not required:
        return None
    frappe.throw(
        _("Required payment approver User {0} is disabled.").format(frappe.bold(user_name)),
        title=_("Payment approver setup failed"),
    )


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

        profile = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Role Profile",
                    "role_profile": profile_name,
                    "roles": [{"role": role_name} for role_name in role_names],
                }
            ),
        )
        profile.insert(ignore_permissions=True)


def ensure_payment_request_permissions() -> None:
    copied_standard_permissions = bool(setup_custom_perms(PAYMENT_REQUEST_DOCTYPE))
    if copied_standard_permissions:
        _ensure_permission_copy_marker()

    for role_name, permissions in PAYMENT_REQUEST_PERMISSIONS.items():
        matches = frappe.get_all(
            "Custom DocPerm",
            filters={"parent": PAYMENT_REQUEST_DOCTYPE, "role": role_name, "permlevel": 0},
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
                        "parent": PAYMENT_REQUEST_DOCTYPE,
                        "role": role_name,
                        "permlevel": 0,
                        "if_owner": 0,
                    }
                ),
            )

        changed = permission.is_new()
        for fieldname, value in permissions.items():
            if permission.get(fieldname) != value:
                permission.set(fieldname, value)
                changed = True

        if not changed:
            continue
        if permission.is_new():
            permission.insert(ignore_permissions=True)
        else:
            permission.save(ignore_permissions=True)


def _ensure_permission_copy_marker() -> None:
    if frappe.db.exists("Custom DocPerm", PERMISSION_COPY_MARKER):
        return

    frappe.get_doc(
        {
            "doctype": "Custom DocPerm",
            **PERMISSION_COPY_MARKER,
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


def ensure_workflow() -> None:
    if frappe.db.exists("Workflow", WORKFLOW_NAME):
        workflow = cast(Document, frappe.get_doc("Workflow", WORKFLOW_NAME))
    else:
        workflow = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Workflow",
                    "workflow_name": WORKFLOW_NAME,
                    "document_type": PAYMENT_REQUEST_DOCTYPE,
                }
            ),
        )

    changed = workflow.is_new()
    scalar_values = {
        "document_type": PAYMENT_REQUEST_DOCTYPE,
        "is_active": 1,
        "override_status": 0,
        "send_email_alert": 1,
        "enable_action_confirmation": 1,
        "workflow_state_field": WORKFLOW_STATE_FIELD,
    }
    for fieldname, value in scalar_values.items():
        if workflow.get(fieldname) != value:
            workflow.set(fieldname, value)
            changed = True

    if not _child_rows_match(workflow.get("states", []), WORKFLOW_STATES, STATE_COMPARISON_FIELDS):
        workflow.set("states", list(WORKFLOW_STATES))
        changed = True
    if not _child_rows_match(
        workflow.get("transitions", []), WORKFLOW_TRANSITIONS, TRANSITION_COMPARISON_FIELDS
    ):
        workflow.set("transitions", list(WORKFLOW_TRANSITIONS))
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
            if fieldname in CHECK_FIELDS:
                value = int(value or 0)
            else:
                value = value or ""
            values.append(value)
        normalized.append(tuple(values))
    return normalized


def remove_legacy_payment_entry_configuration() -> None:
    _delete_workflow(LEGACY_WORKFLOW_NAME)
    _remove_managed_permissions(
        PAYMENT_ENTRY_DOCTYPE,
        tuple(PAYMENT_REQUEST_PERMISSIONS),
        LEGACY_PERMISSION_COPY_MARKER,
    )
    _delete_custom_fields(PAYMENT_ENTRY_DOCTYPE, (WORKFLOW_STATE_FIELD, APPROVAL_DUE_AT_FIELD))
    _remove_unused_workflow_masters(LEGACY_WORKFLOW_ACTIONS, LEGACY_WORKFLOW_STATE_STYLES)
    frappe.clear_cache(doctype=PAYMENT_ENTRY_DOCTYPE)


def remove_configuration() -> None:
    _delete_workflow(WORKFLOW_NAME)
    _remove_managed_permissions(
        PAYMENT_REQUEST_DOCTYPE,
        tuple(PAYMENT_REQUEST_PERMISSIONS),
        PERMISSION_COPY_MARKER,
    )
    remove_legacy_payment_entry_configuration()

    for profile_name in ROLE_PROFILES:
        if frappe.db.exists("Role Profile", profile_name):
            frappe.delete_doc("Role Profile", profile_name, force=True, ignore_permissions=True)

    for role_name in MANAGED_ROLES:
        if frappe.db.exists("Role", role_name):
            frappe.delete_doc("Role", role_name, force=True, ignore_permissions=True)

    _delete_custom_fields(
        PAYMENT_REQUEST_DOCTYPE,
        (
            WORKFLOW_STATE_FIELD,
            APPROVAL_DUE_AT_FIELD,
            BASE_GRAND_TOTAL_FIELD,
            PAYMENT_APPROVAL_LIMIT_FIELD,
        ),
    )
    _delete_custom_fields(COMPANY_DOCTYPE, (LOW_VALUE_PAYMENT_APPROVAL_LIMIT_FIELD,))
    _remove_unused_workflow_masters(WORKFLOW_ACTIONS, WORKFLOW_STATE_STYLES)
    frappe.clear_cache(doctype=COMPANY_DOCTYPE)
    frappe.clear_cache(doctype=PAYMENT_REQUEST_DOCTYPE)


def _delete_workflow(workflow_name: str) -> None:
    if not frappe.db.exists("Workflow", workflow_name):
        return
    frappe.db.set_value("Workflow", workflow_name, "is_active", 0)
    frappe.delete_doc("Workflow", workflow_name, force=True, ignore_permissions=True)


def _delete_custom_fields(doctype: str, fieldnames: tuple[str, ...]) -> None:
    for fieldname in fieldnames:
        custom_field_name = frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname})
        if custom_field_name:
            frappe.delete_doc("Custom Field", custom_field_name, force=True, ignore_permissions=True)


def _remove_managed_permissions(
    doctype: str,
    managed_permission_roles: tuple[str, ...],
    copy_marker: dict[str, Any],
) -> None:
    copied_standard_permissions = bool(frappe.db.exists("Custom DocPerm", copy_marker))
    permission_names = frappe.get_all(
        "Custom DocPerm",
        filters={
            "parent": doctype,
            "role": ["in", managed_permission_roles],
            "permlevel": 0,
        },
        pluck="name",
    )
    marker_name = frappe.db.exists("Custom DocPerm", copy_marker)
    if marker_name:
        permission_names.append(cast(str, marker_name))

    for permission_name in set(permission_names):
        if frappe.db.exists("Custom DocPerm", permission_name):
            frappe.delete_doc("Custom DocPerm", permission_name, force=True, ignore_permissions=True)

    if copied_standard_permissions and _custom_permissions_match_standard(doctype):
        reset_perms(doctype)


def _custom_permissions_match_standard(doctype: str) -> bool:
    custom_permissions = frappe.get_all(
        "Custom DocPerm",
        filters={"parent": doctype},
        fields=list(PERMISSION_COMPARISON_FIELDS),
    )
    standard_permissions = frappe.get_all(
        "DocPerm",
        filters={"parent": doctype},
        fields=list(PERMISSION_COMPARISON_FIELDS),
    )
    return _normalized_permissions(custom_permissions) == _normalized_permissions(standard_permissions)


def _normalized_permissions(rows: Sequence[Any]) -> list[tuple[Any, ...]]:
    return sorted(
        tuple(
            (cast(str, row.get(fieldname)) if fieldname == "role" else int(row.get(fieldname) or 0))
            for fieldname in PERMISSION_COMPARISON_FIELDS
        )
        for row in rows
    )


def _remove_unused_workflow_masters(actions: Sequence[str], state_styles: dict[str, str]) -> None:
    for action_name in actions:
        if not frappe.db.exists("Workflow Transition", {"action": action_name}) and frappe.db.exists(
            "Workflow Action Master", action_name
        ):
            frappe.delete_doc("Workflow Action Master", action_name, force=True, ignore_permissions=True)

    for state_name in state_styles:
        is_referenced = (
            frappe.db.exists("Workflow Document State", {"state": state_name})
            or frappe.db.exists("Workflow Transition", {"state": state_name})
            or frappe.db.exists("Workflow Transition", {"next_state": state_name})
        )
        if not is_referenced and frappe.db.exists("Workflow State", state_name):
            frappe.delete_doc("Workflow State", state_name, force=True, ignore_permissions=True)
