# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from frappe.model.document import Document

from connect_diagnostics_core.setup.payment_approval import (
    LOW_VALUE_APPROVER_PROFILE,
    MANAGED_ROLES,
    PAYMENT_ENTRY_DOCTYPE,
    PRIMARY_APPROVER_PROFILE,
    SECONDARY_APPROVER_PROFILE,
    WORKFLOW_STATE_STYLES,
    remove_configuration,
)

MANAGED_PROFILES = (
    PRIMARY_APPROVER_PROFILE,
    SECONDARY_APPROVER_PROFILE,
    LOW_VALUE_APPROVER_PROFILE,
)


def execute() -> None:
    remove_payment_approver_assignments()
    _delete_managed_workflow_actions()
    remove_configuration()
    frappe.clear_cache()


def remove_payment_approver_assignments(
    user_names: tuple[str, ...] | None = None,
) -> None:
    if user_names is None:
        user_names = _get_users_with_managed_assignments()

    for user_name in user_names:
        if not frappe.db.exists("User", user_name):
            continue
        user = cast(Document, frappe.get_doc("User", user_name))
        changed = _remove_user_child_rows(user, "role_profiles", "role_profile", MANAGED_PROFILES)
        changed |= _remove_user_child_rows(user, "roles", "role", MANAGED_ROLES)
        if changed:
            user.save(ignore_permissions=True)


def _get_users_with_managed_assignments() -> tuple[str, ...]:
    user_names = set(
        frappe.get_all(
            "Has Role",
            filters={"parenttype": "User", "role": ["in", MANAGED_ROLES]},
            pluck="parent",
        )
    )
    user_names.update(
        frappe.get_all(
            "User Role Profile",
            filters={"parenttype": "User", "role_profile": ["in", MANAGED_PROFILES]},
            pluck="parent",
        )
    )
    return tuple(sorted(user_names))


def _remove_user_child_rows(
    user: Document, table_field: str, value_field: str, managed_values: tuple[str, ...]
) -> bool:
    rows = list(user.get(table_field, []))
    remaining_rows = [row for row in rows if row.get(value_field) not in managed_values]
    if len(rows) == len(remaining_rows):
        return False
    user.set(table_field, remaining_rows)
    return True


def _delete_managed_workflow_actions() -> None:
    workflow_action_names = frappe.get_all(
        "Workflow Action",
        filters={
            "reference_doctype": PAYMENT_ENTRY_DOCTYPE,
            "workflow_state": ["in", tuple(WORKFLOW_STATE_STYLES)],
        },
        pluck="name",
    )
    for workflow_action_name in workflow_action_names:
        if frappe.db.exists("Workflow Action", workflow_action_name):
            frappe.delete_doc("Workflow Action", workflow_action_name, force=True, ignore_permissions=True)
