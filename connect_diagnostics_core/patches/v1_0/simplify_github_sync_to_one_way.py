# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt
"""Simplify the GitHub/Helpdesk sync to one-way (pull) + manual escalation.

Drops the now-dead two-way settings toggles and the comment-dedup custom field, and
arms the "Resolved" status applied when a linked GitHub issue closes. Idempotent.
"""

import frappe

SETTINGS = "GitHub Helpdesk Sync Settings"
DROPPED_SETTINGS_FIELDS = (
    "push_comments",
    "push_close_state",
    "push_status_to_board",
    "comment_attribution",
    "default_sync_new_tickets",
    "push_create_issue",
)
DEAD_CUSTOM_FIELD = "HD Ticket Comment-github_comment_id"
RESOLVED_STATUS = "Resolved"


def execute() -> None:
    _ensure_resolved_status()
    _arm_resolved_status_setting()
    _drop_orphan_single_values()
    _drop_dead_custom_field()
    frappe.clear_cache()
    frappe.db.commit()


def _ensure_resolved_status() -> None:
    if not frappe.db.exists("DocType", "HD Ticket Status"):
        return
    if frappe.db.exists("HD Ticket Status", RESOLVED_STATUS):
        return
    frappe.get_doc(
        {
            "doctype": "HD Ticket Status",
            "label_agent": RESOLVED_STATUS,
            "label_customer": RESOLVED_STATUS,
            "category": "Resolved",
            "color": "Green",
            "enabled": 1,
        }
    ).insert(ignore_permissions=True)


def _arm_resolved_status_setting() -> None:
    if not frappe.db.exists("DocType", SETTINGS):
        return
    if not frappe.db.get_single_value(SETTINGS, "resolved_status"):
        frappe.db.set_single_value(SETTINGS, "resolved_status", RESOLVED_STATUS)


def _drop_orphan_single_values() -> None:
    frappe.db.delete("Singles", {"doctype": SETTINGS, "field": ("in", DROPPED_SETTINGS_FIELDS)})


def _drop_dead_custom_field() -> None:
    if frappe.db.exists("Custom Field", DEAD_CUSTOM_FIELD):
        frappe.delete_doc("Custom Field", DEAD_CUSTOM_FIELD, force=True, ignore_missing=True)
