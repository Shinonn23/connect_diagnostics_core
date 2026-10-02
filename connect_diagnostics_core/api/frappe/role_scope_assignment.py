# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Private WF-15 scope validation and grant-provenance helpers.

These helpers are intentionally not whitelisted. The coordinated Workflow
activation owns their only caller and the User validation guard that consumes
the private, one-shot role capability.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import frappe
from frappe import _

if TYPE_CHECKING:
    from frappe.model.document import Document

OWNER_ROLES = {
    "Company": "Company Owner",
    "Department": "Department Head",
    "Warehouse": "Warehouse Manager",
}
FUNCTIONAL_ROLES = frozenset(
    {
        "Stock User",
        "Stock Manager",
        "C-Level Approver",
        "Accounts User",
        "Accounts Manager",
        "Sales User",
        "Sales Manager",
        "Purchase User",
        "Purchase Manager",
        "HR User",
        "HR Manager",
        "Asset Administrator",
    }
)


@dataclass
class _UserRoleCapability:
    assignment: str
    user: str
    role: str
    operation: str
    _nonce: object
    consumed: bool = False


@dataclass
class _WorkflowTransitionCapability:
    document: object
    assignment: str
    action: str
    operation: str
    nonce: object


_WORKFLOW_CAPABILITY_FLAG = "_role_scope_assignment_transition_capability"
_TRANSITION_OPERATIONS = {
    "Request Assignment": "save",
    "Approve Assignment": "submit",
    "Reject Assignment": "save",
    "Cancel": "cancel",
}
_role_capability: ContextVar[_UserRoleCapability | None] = ContextVar(
    "wf15_user_role_capability", default=None
)


def authorize_workflow_transition(doc: Document, assignment: str, action: str, operation: str) -> None:
    """Attach an opaque one-shot capability to the exact Workflow-loaded document."""
    if (
        doc.doctype != "Role Scope Assignment"
        or assignment != str(doc.name)
        or _TRANSITION_OPERATIONS.get(action) != operation
    ):
        frappe.throw(_("The Role Scope Assignment Workflow transition is not valid."))
    existing = doc.flags.get(_WORKFLOW_CAPABILITY_FLAG)
    if existing:
        frappe.throw(_("A Role Scope Assignment Workflow transition is already armed."))
    doc.flags[_WORKFLOW_CAPABILITY_FLAG] = _WorkflowTransitionCapability(
        document=doc,
        assignment=assignment,
        action=action,
        operation=operation,
        nonce=object(),
    )


def is_authorized_workflow_transition(doc: Document, action: str, operation: str) -> bool:
    capability = doc.flags.get(_WORKFLOW_CAPABILITY_FLAG)
    return bool(
        capability
        and capability.document is doc
        and capability.assignment == str(doc.name)
        and capability.action == action
        and capability.operation == operation
    )


def consume_workflow_transition(doc: Document, action: str, operation: str) -> bool:
    if not is_authorized_workflow_transition(doc, action, operation):
        return False
    doc.flags.pop(_WORKFLOW_CAPABILITY_FLAG, None)
    return True


def _arm_role_capability(assignment: str, user: str, role: str, operation: str) -> Any:
    """Arm an unforgeable request-local capability for one native User write."""
    if operation not in {"add", "remove"}:
        frappe.throw(_("The User role operation is not valid."))
    capability = _UserRoleCapability(assignment, user, role, operation, object())
    return _role_capability.set(capability)


def _disarm_role_capability(token: Any) -> None:
    _role_capability.reset(token)


def consume_user_role_capability(user: str, role: str, operation: str) -> bool:
    """Consume the current exact capability from the future User guard."""
    capability = _role_capability.get()
    if (
        capability is None
        or capability.consumed
        or capability.user != user
        or capability.role != role
        or capability.operation != operation
    ):
        return False
    capability.consumed = True
    _role_capability.set(None)
    return True


def _lock_scope(scope_type: str, scope_name: str, company: str) -> None:
    if scope_type not in OWNER_ROLES or not scope_name or not company:
        frappe.throw(_("Choose one supported scope and its Company."))
    if scope_type == "Company":
        if scope_name != company:
            frappe.throw(_("Company scope must match the selected Company."))
        row = frappe.db.get_value("Company", scope_name, "name", for_update=True)
    else:
        row = frappe.db.get_value(scope_type, scope_name, ["name", "company"], as_dict=True, for_update=True)
        if not row or row.company != company:
            frappe.throw(_("The selected scope must belong to the selected Company."))
    if not row:
        frappe.throw(_("The selected scope does not exist."))


def validate_scope_binding(scope_type: str, scope_name: str, company: str) -> None:
    """Validate the single exact scope-to-Company binding without granting access."""
    _lock_scope(scope_type, scope_name, company)


def resolve_scope_owners(scope_type: str, scope_name: str, company: str) -> list[str]:
    """Return enabled exact-scope owners; an empty result is a fail-closed state."""
    _lock_scope(scope_type, scope_name, company)
    owner_role = OWNER_ROLES[scope_type]
    candidates = frappe.db.sql(
        """
        SELECT u.name
        FROM `tabUser` AS u
        INNER JOIN `tabHas Role` AS hr ON hr.parent = u.name
        INNER JOIN `tabUser Permission` AS up ON up.user = u.name
        WHERE u.enabled = 1
          AND hr.parenttype = 'User'
          AND hr.role = %s
          AND up.allow = %s
          AND up.for_value = %s
          AND up.apply_to_all_doctypes = 1
          AND up.hide_descendants = 1
          AND (up.applicable_for IS NULL OR up.applicable_for = '')
        FOR UPDATE
        """,
        (owner_role, scope_type, scope_name),
        as_dict=True,
    )
    owners: list[str] = []
    scope_doc = frappe.get_doc(scope_type, scope_name)
    for user in sorted({str(candidate.name) for candidate in candidates}):
        if frappe.has_permission(scope_type, ptype="read", doc=scope_doc, user=user):
            owners.append(user)
    return owners


def validate_assignment_actor(
    *,
    scope_type: str,
    scope_name: str,
    company: str,
    requester: str,
    actor: str,
) -> None:
    if actor == requester:
        frappe.throw(_("The requester cannot approve or revoke their own assignment."))
    if actor not in resolve_scope_owners(scope_type, scope_name, company):
        frappe.throw(_("You are not an authorized owner of this exact scope."))


def _locked_user(user: str) -> Document:
    if not frappe.db.get_value("User", user, "name", for_update=True):
        frappe.throw(_("The target User does not exist."))
    doc = frappe.get_doc("User", user)
    if not doc.get("enabled"):
        frappe.throw(_("The target User must be enabled."))
    return doc


def _permission_filters(user: str, scope_type: str, scope_name: str) -> dict[str, Any]:
    return {
        "user": user,
        "allow": scope_type,
        "for_value": scope_name,
        "apply_to_all_doctypes": 1,
        "hide_descendants": 1,
        "applicable_for": ["in", ["", None]],
    }


def _exact_permission_rows(user: str, scope_type: str, scope_name: str) -> list[dict[str, Any]]:
    return frappe.db.sql(
        """
        SELECT name
        FROM `tabUser Permission`
        WHERE user = %s
          AND allow = %s
          AND for_value = %s
          AND apply_to_all_doctypes = 1
          AND hide_descendants = 1
          AND (applicable_for IS NULL OR applicable_for = '')
        FOR UPDATE
        """,
        (user, scope_type, scope_name),
        as_dict=True,
    )


def grant_assignment(assignment: Document) -> None:
    """Grant the approved exact role/scope and record only grants created here."""
    name = str(assignment.name)
    user = str(assignment.get("target_user"))
    role = str(assignment.get("functional_role"))
    scope_type = str(assignment.get("scope_type"))
    scope_name = str(assignment.get(scope_type.lower()))
    company = str(assignment.get("company"))
    if role not in FUNCTIONAL_ROLES:
        frappe.throw(_("The selected functional role is not assignable."))
    if not frappe.db.get_value("Role", role, "name", for_update=True):
        frappe.throw(_("The selected functional role does not exist."))
    _lock_scope(scope_type, scope_name, company)
    target = _locked_user(user)
    matching_role = next((row for row in target.get("roles") if row.get("role") == role), None)
    if matching_role:
        assignment.set("role_grant_created", 0)
        assignment.set("role_grant_row", None)
    else:
        target.append("roles", {"role": role})
        token = _arm_role_capability(name, user, role, "add")
        try:
            target.save(ignore_permissions=True)
        finally:
            _disarm_role_capability(token)
        role_row = next((row for row in target.get("roles") if row.get("role") == role), None)
        role_row_name = role_row.get("name") if role_row else None
        if not role_row_name:
            frappe.throw(_("The created User role row could not be identified."))
        assignment.set("role_grant_created", 1)
        assignment.set("role_grant_row", role_row_name)

    existing = _exact_permission_rows(user, scope_type, scope_name)
    if existing:
        assignment.set("user_permission_created", 0)
        assignment.set("user_permission_row", None)
    else:
        permission = frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": user,
                "allow": scope_type,
                "for_value": scope_name,
                "apply_to_all_doctypes": 1,
                "hide_descendants": 1,
            }
        )
        permission.insert(ignore_permissions=True)
        assignment.set("user_permission_created", 1)
        assignment.set("user_permission_row", permission.name)


def revoke_assignment(assignment: Document) -> None:
    """Revoke only exact native grants whose identities this assignment owns."""
    user = str(assignment.get("target_user"))
    role = str(assignment.get("functional_role"))
    scope_type = str(assignment.get("scope_type"))
    scope_name = str(assignment.get(scope_type.lower()))
    company = str(assignment.get("company"))
    _lock_scope(scope_type, scope_name, company)
    target = _locked_user(user)

    permission_name = assignment.get("user_permission_row")
    if assignment.get("user_permission_created") and permission_name:
        row = frappe.db.get_value(
            "User Permission",
            permission_name,
            [
                "name",
                "user",
                "allow",
                "for_value",
                "apply_to_all_doctypes",
                "hide_descendants",
                "applicable_for",
            ],
            as_dict=True,
            for_update=True,
        )
        expected = _permission_filters(user, scope_type, scope_name)
        if row and all(row.get(key) == value for key, value in expected.items() if key != "applicable_for"):
            if not row.get("applicable_for"):
                scope_field = scope_type.lower()
                active_scope_assignments = frappe.get_all(
                    "Role Scope Assignment",
                    filters={
                        "name": ["!=", assignment.name],
                        "target_user": user,
                        "scope_type": scope_type,
                        scope_field: scope_name,
                        "docstatus": 1,
                    },
                    fields=["name", "user_permission_created", "user_permission_row"],
                    order_by="name asc",
                )
                permission_owner = next(
                    (
                        item
                        for item in active_scope_assignments
                        if item.user_permission_created and item.user_permission_row == permission_name
                    ),
                    None,
                )
                if permission_owner:
                    # Another approved assignment already owns this shared grant.
                    pass
                elif any(item.user_permission_created for item in active_scope_assignments):
                    frappe.throw(_("A shared User Permission has conflicting assignment provenance."))
                elif active_scope_assignments:
                    successor = active_scope_assignments[0]
                    frappe.db.set_value(
                        "Role Scope Assignment",
                        successor.name,
                        {"user_permission_created": 1, "user_permission_row": permission_name},
                    )
                else:
                    frappe.delete_doc("User Permission", permission_name, ignore_permissions=True)

    role_row_name = assignment.get("role_grant_row")
    if not assignment.get("role_grant_created") or not role_row_name:
        return
    role_row = frappe.db.get_value(
        "Has Role", role_row_name, ["name", "parent", "role", "parenttype"], as_dict=True, for_update=True
    )
    if (
        not role_row
        or role_row.get("parent") != user
        or role_row.get("role") != role
        or role_row.get("parenttype") != "User"
    ):
        return
    other_assignments = frappe.get_all(
        "Role Scope Assignment",
        filters={
            "name": ["!=", assignment.name],
            "target_user": user,
            "functional_role": role,
            "docstatus": 1,
        },
        fields=["name", "role_grant_created", "role_grant_row"],
        order_by="name asc",
    )
    if other_assignments:
        owned_elsewhere = next(
            (
                item
                for item in other_assignments
                if item.role_grant_created and item.role_grant_row == role_row_name
            ),
            None,
        )
        if any(item.role_grant_created for item in other_assignments) and not owned_elsewhere:
            frappe.throw(_("A shared User role has conflicting assignment provenance."))
        if assignment.get("role_grant_created") and not owned_elsewhere:
            frappe.db.set_value(
                "Role Scope Assignment",
                other_assignments[0].name,
                {"role_grant_created": 1, "role_grant_row": role_row_name},
            )
        return
    target.set("roles", [row for row in target.get("roles") if row.get("name") != role_row_name])
    token = _arm_role_capability(str(assignment.name), user, role, "remove")
    try:
        target.save(ignore_permissions=True)
    finally:
        _disarm_role_capability(token)
