"""Rollback for remove_workflow_state_custom_fields — recreate the empty fields.

The original per-record values cannot be recovered (the columns were dropped and
held only Frappe Workflow state); this restores the Custom Field definitions so the
schema matches the pre-removal state. It does not recreate any Workflow.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

from connect_diagnostics_core.patches.v1_0.remove_workflow_state_custom_fields import (
    WORKFLOW_STATE_FIELDS,
)


def execute():
    for doctype, fieldname in WORKFLOW_STATE_FIELDS:
        if frappe.db.exists("Custom Field", f"{doctype}-{fieldname}"):
            continue
        create_custom_field(
            doctype,
            {
                "fieldname": fieldname,
                "label": frappe.unscrub(fieldname),
                "fieldtype": "Link",
                "options": "Workflow State",
                "read_only": 1,
                "no_copy": 1,
                "allow_on_submit": 1,
            },
        )
    frappe.db.commit()
