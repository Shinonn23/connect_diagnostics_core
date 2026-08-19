"""Drop the workflow-state columns from app-owned DocTypes.

Phase 4 of the custom-workflow reset. These fields were removed from the DocType
JSON (they only held a Frappe Workflow state); this drops the orphan columns that
a JSON field removal leaves behind. Idempotent / no-op once dropped. Per-record
values are not preserved (they were workflow state only).
"""

import frappe

# (doctype, column)
WORKFLOW_STATE_COLUMNS = (
    ("Stock Count", "count_state"),
    ("Customer Credit Request", "credit_request_state"),
    ("Medical Device Product Registration", "regulatory_workflow_state"),
    ("Supplier Bank Change Request", "bank_change_request_state"),
)


def execute():
    # DROP ... IF EXISTS keeps this idempotent whether or not the DocType sync
    # already removed the column when the field left the JSON.
    for doctype, column in WORKFLOW_STATE_COLUMNS:
        frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN IF EXISTS `{column}`")

    frappe.db.commit()
