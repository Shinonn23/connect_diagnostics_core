"""Rollback for drop_workflow_state_doctype_columns — recreate the empty columns.

The original per-record values cannot be recovered (the columns were dropped and
held only Frappe Workflow state); this restores the raw columns so the schema
matches the pre-removal state. The DocType field definitions are restored by
reverting the reset commits, not by this patch.
"""

import frappe

from connect_diagnostics_core.patches.v1_0.drop_workflow_state_doctype_columns import (
    WORKFLOW_STATE_COLUMNS,
)


def execute():
    for doctype, column in WORKFLOW_STATE_COLUMNS:
        frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` ADD COLUMN IF NOT EXISTS `{column}` varchar(140)")

    frappe.db.commit()
