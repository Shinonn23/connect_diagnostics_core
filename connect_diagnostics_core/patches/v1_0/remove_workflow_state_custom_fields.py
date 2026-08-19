"""Remove the workflow-state Link custom fields left by the custom-workflow reset.

Phase 4 of the reset. These fields only ever held a Frappe Workflow state (a Link
to "Workflow State"); with the workflows gone they have no purpose. The field
definitions were dropped from setup, so this deletes the Custom Field docs already
created on existing sites and drops the orphan columns. Idempotent / no-op once
removed. Per-record values are not preserved (they were workflow state only).
"""

import frappe

# (doctype, fieldname) — the Custom Field is named "<doctype>-<fieldname>".
WORKFLOW_STATE_FIELDS = (
    ("Payment Request", "payment_approval_state"),
    ("Salary Slip", "salary_slip_review_state"),
    ("Supplier", "supplier_onboarding_state"),
    ("Material Request", "p2p_workflow_state"),
    ("Purchase Order", "p2p_workflow_state"),
    ("Purchase Receipt", "p2p_workflow_state"),
    ("Purchase Invoice", "p2p_workflow_state"),
)


def execute():
    for doctype, fieldname in WORKFLOW_STATE_FIELDS:
        custom_field = f"{doctype}-{fieldname}"
        if frappe.db.exists("Custom Field", custom_field):
            frappe.delete_doc("Custom Field", custom_field, force=True, ignore_permissions=True)

        if frappe.db.has_column(doctype, fieldname):
            frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{fieldname}`")

    frappe.db.commit()
