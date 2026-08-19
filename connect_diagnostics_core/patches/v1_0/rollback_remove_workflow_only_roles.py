"""Rollback for remove_workflow_only_roles — recreate the empty roles/profiles.

User assignments, Custom DocPerm rows, and per-record base_grand_total values are
not recovered (they were workflow-only and were deleted); this restores the Role
and Role Profile definitions and the base_grand_total column so the schema matches
the pre-removal state. The workflows themselves are restored by reverting the reset
commits, not by this patch.
"""

import frappe

from connect_diagnostics_core.patches.v1_0.remove_workflow_only_roles import (
    WORKFLOW_ONLY_ROLE_PROFILES,
    WORKFLOW_ONLY_ROLES,
)

# Profile -> its role, for restoring the Role Profile row.
_PROFILE_ROLE = {
    "Executive P2P Approver Add-on": "Executive P2P Approver",
    "P2P Finance Verifier Add-on": "P2P Finance Verifier",
    "Supplier Activator Add-on": "Supplier Activator",
}


def execute():
    for role in WORKFLOW_ONLY_ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1, "is_custom": 1}).insert(
                ignore_permissions=True
            )

    for profile in WORKFLOW_ONLY_ROLE_PROFILES:
        if not frappe.db.exists("Role Profile", profile):
            frappe.get_doc(
                {
                    "doctype": "Role Profile",
                    "role_profile": profile,
                    "roles": [{"role": _PROFILE_ROLE[profile]}],
                }
            ).insert(ignore_permissions=True)

    frappe.db.sql_ddl(
        "ALTER TABLE `tabPayment Request` ADD COLUMN IF NOT EXISTS `base_grand_total` decimal(21,9)"
    )

    frappe.db.commit()
