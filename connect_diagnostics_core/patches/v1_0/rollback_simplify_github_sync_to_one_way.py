# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt
"""Rollback of simplify_github_sync_to_one_way.

Restores the comment-dedup custom field and clears the resolved_status setting. The
removed two-way settings toggles are restored by reverting the code/JSON, not by data —
they held only booleans with no recoverable state. Idempotent.
"""

import frappe

SETTINGS = "GitHub Helpdesk Sync Settings"
DEAD_CUSTOM_FIELD = "HD Ticket Comment-github_comment_id"


def execute() -> None:
    _restore_comment_id_field()
    if frappe.db.exists("DocType", SETTINGS):
        frappe.db.delete("Singles", {"doctype": SETTINGS, "field": "resolved_status"})
    frappe.clear_cache()
    frappe.db.commit()


def _restore_comment_id_field() -> None:
    if not frappe.db.exists("DocType", "HD Ticket Comment"):
        return
    if frappe.db.exists("Custom Field", DEAD_CUSTOM_FIELD):
        return
    frappe.get_doc(
        {
            "doctype": "Custom Field",
            "dt": "HD Ticket Comment",
            "fieldname": "github_comment_id",
            "module": "Connect Diagnostics Core",
            "label": "GitHub Comment ID",
            "fieldtype": "Data",
            "insert_after": "is_pinned",
            "read_only": 1,
            "no_copy": 1,
            "hidden": 1,
        }
    ).insert(ignore_permissions=True)
