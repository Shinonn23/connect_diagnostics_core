# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Retire the Department User Permission bulk-permission helper.

Force-deletes ``Department User Permission`` and its child table
``Department User Permission User``. The real access grants this tool
generated are plain ``User Permission`` records and are untouched — only the
generator doctype itself is removed. Its stale Workspace card and sidebar
shortcuts on "ERPNext Settings" are cleaned up separately by
``setup.workspace.ensure_workspace_navigation`` (via ``RETIRED_CARD_LINKS`` /
``RETIRED_SIDEBAR_LINKS``) on the next ``after_migrate``. Idempotent: a no-op
once already removed.
"""

import frappe

DOCTYPES = (
    "Department User Permission",
    "Department User Permission User",
)


def execute():
    for doctype in DOCTYPES:
        if frappe.db.exists("DocType", doctype):
            frappe.delete_doc("DocType", doctype, force=True, ignore_missing=True)

    frappe.db.commit()
