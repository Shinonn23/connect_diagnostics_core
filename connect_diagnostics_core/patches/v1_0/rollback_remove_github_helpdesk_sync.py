# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt
"""Rollback of remove_github_helpdesk_sync.

Restores the structural part that is recoverable from data alone: the GitHub
custom fields on HD Ticket. The sync DocTypes (and their rows), the Scheduled Job
Type, and the dropped single values cannot be rebuilt from data — they require
reverting the code/JSON and re-running the old setup. Idempotent.
"""

import frappe

HD_TICKET_FIELDS = {
    "github_section": {
        "label": "GitHub",
        "fieldtype": "Section Break",
        "insert_after": "key",
        "collapsible": 1,
    },
    "sync_to_github": {
        "label": "Sync to GitHub",
        "fieldtype": "Check",
        "default": "0",
        "insert_after": "github_section",
    },
    "github_issue_number": {
        "label": "GitHub Issue #",
        "fieldtype": "Int",
        "insert_after": "sync_to_github",
        "read_only": 1,
        "no_copy": 1,
        "in_standard_filter": 1,
    },
    "github_url": {
        "label": "GitHub URL",
        "fieldtype": "Data",
        "options": "URL",
        "insert_after": "github_issue_number",
        "read_only": 1,
        "no_copy": 1,
    },
    "github_col": {"fieldtype": "Column Break", "insert_after": "github_url"},
    "github_last_synced": {
        "label": "GitHub Last Synced",
        "fieldtype": "Datetime",
        "insert_after": "github_col",
        "read_only": 1,
        "no_copy": 1,
    },
    "github_project_item_id": {
        "label": "GitHub Project Item ID",
        "fieldtype": "Data",
        "insert_after": "github_last_synced",
        "read_only": 1,
        "no_copy": 1,
        "hidden": 1,
    },
}


def execute() -> None:
    if not frappe.db.exists("DocType", "HD Ticket"):
        return
    for fieldname, spec in HD_TICKET_FIELDS.items():
        if frappe.db.exists("Custom Field", f"HD Ticket-{fieldname}"):
            continue
        frappe.get_doc(
            {
                "doctype": "Custom Field",
                "dt": "HD Ticket",
                "fieldname": fieldname,
                "module": "Connect Diagnostics Core",
                **spec,
            }
        ).insert(ignore_permissions=True)
    frappe.clear_cache(doctype="HD Ticket")
    frappe.db.commit()
