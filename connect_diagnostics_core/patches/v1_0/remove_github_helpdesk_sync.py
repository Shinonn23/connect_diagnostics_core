# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt
"""Remove the GitHub <-> Helpdesk sync system entirely.

Drops the sync DocTypes, the Scheduled Job Type for the pull cron, the orphan
single values, and the GitHub custom fields/template fields the old setup added
to HD Ticket. Idempotent and guarded so it is safe whether or not the Helpdesk
app is still installed.
"""

import frappe

SYNC_DOCTYPES = (
    "GitHub Helpdesk Sync Settings",
    "GitHub Helpdesk Sync Log",
    "GitHub Status Mapping",
    "GitHub User Map",
    # Pre-rename names, in case a site never ran the rename patch.
    "GitHub Integration Settings",
    "GitHub Sync Log",
)
SINGLE_DOCTYPES = ("GitHub Helpdesk Sync Settings", "GitHub Integration Settings")
SCHEDULED_JOB = "connect_diagnostics_core.github_sync.pull"
HD_TICKET_FIELDS = (
    "github_section",
    "sync_to_github",
    "github_issue_number",
    "github_url",
    "github_col",
    "github_last_synced",
    "github_project_item_id",
)
HD_TICKET_COMMENT_FIELDS = ("github_comment_id",)
HELPDESK_TEMPLATE = "Default"
TEMPLATE_FIELDNAMES = (
    "sync_to_github",
    "github_issue_number",
    "github_url",
    "github_last_synced",
)


def execute() -> None:
    _drop_custom_fields("HD Ticket", HD_TICKET_FIELDS)
    _drop_custom_fields("HD Ticket Comment", HD_TICKET_COMMENT_FIELDS)
    _drop_template_fields()
    _drop_scheduled_job()
    _drop_doctypes()
    _drop_orphan_singles()
    frappe.clear_cache()
    frappe.db.commit()


def _drop_custom_fields(doctype: str, fieldnames: tuple[str, ...]) -> None:
    for fieldname in fieldnames:
        name = f"{doctype}-{fieldname}"
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, force=True, ignore_missing=True)
    if frappe.db.exists("DocType", doctype):
        frappe.clear_cache(doctype=doctype)


def _drop_template_fields() -> None:
    if not frappe.db.exists("DocType", "HD Ticket Template Field"):
        return
    if not frappe.db.exists("HD Ticket Template", HELPDESK_TEMPLATE):
        return
    doc = frappe.get_doc("HD Ticket Template", HELPDESK_TEMPLATE)
    remaining = [row for row in (doc.get("fields") or []) if row.fieldname not in TEMPLATE_FIELDNAMES]
    if len(remaining) != len(doc.get("fields") or []):
        doc.set("fields", remaining)
        doc.save(ignore_permissions=True)


def _drop_scheduled_job() -> None:
    if not frappe.db.exists("DocType", "Scheduled Job Type"):
        return
    for name in frappe.get_all("Scheduled Job Type", filters={"method": SCHEDULED_JOB}, pluck="name"):
        frappe.delete_doc("Scheduled Job Type", name, force=True, ignore_missing=True)


def _drop_doctypes() -> None:
    for doctype in SYNC_DOCTYPES:
        if frappe.db.exists("DocType", doctype):
            frappe.delete_doc("DocType", doctype, force=True, ignore_missing=True)


def _drop_orphan_singles() -> None:
    frappe.db.delete("Singles", {"doctype": ("in", SINGLE_DOCTYPES)})
