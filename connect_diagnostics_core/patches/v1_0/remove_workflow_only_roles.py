"""Remove the workflow-only roles, profiles, and Payment Request approval perms.

Phase 4c of the custom-workflow reset. These roles existed only to gate the
retired approval/verification Workflow transitions; the profiles bundled them, and
the Payment Request Custom DocPerm rows granted approvers submit access. With the
workflows gone none of them have a purpose. The genuine "Purchase Requester" role
and its Material Request permission are intentionally left untouched.

Idempotent: each record is removed only when present. Deleting a Role also clears
its assignments (Has Role) from every user first. base_grand_total was the
company-currency amount used only for approval routing; its column is dropped too.
"""

import frappe

WORKFLOW_ONLY_ROLES = (
    "Executive P2P Approver",
    "P2P Finance Verifier",
    "Supplier Activator",
)

WORKFLOW_ONLY_ROLE_PROFILES = (
    "Executive P2P Approver Add-on",
    "P2P Finance Verifier Add-on",
    "Supplier Activator Add-on",
)

# Payment Request approver Custom DocPerm rows (submit access) — the two roles the
# retired Payment Request Approval workflow used.
PAYMENT_REQUEST_APPROVER_ROLES = ("Executive P2P Approver", "P2P Finance Verifier")


def execute():
    # Payment Request approver permissions first (they reference the roles).
    for role in PAYMENT_REQUEST_APPROVER_ROLES:
        frappe.db.delete("Custom DocPerm", {"parent": "Payment Request", "role": role})

    for profile in WORKFLOW_ONLY_ROLE_PROFILES:
        if frappe.db.exists("Role Profile", profile):
            frappe.delete_doc("Role Profile", profile, force=True, ignore_permissions=True)

    for role in WORKFLOW_ONLY_ROLES:
        frappe.db.delete("Has Role", {"role": role})
        if frappe.db.exists("Role", role):
            frappe.delete_doc("Role", role, force=True, ignore_permissions=True)

    frappe.db.sql_ddl("ALTER TABLE `tabPayment Request` DROP COLUMN IF EXISTS `base_grand_total`")

    frappe.db.commit()
