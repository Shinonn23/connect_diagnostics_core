# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Retire the Connect Diagnostics Accounting Script Reports.

Deletes the ``Report`` records for General Ledger TH, Trial Balance TH, and
Trial Balance TH Detail. Their stale Workspace card and sidebar shortcuts on
"Financial Reports" are cleaned up separately by
``setup.workspace.ensure_workspace_navigation`` (via ``RETIRED_CARD_LINKS`` /
``RETIRED_SIDEBAR_LINKS``) on the next ``after_migrate``. Idempotent: a no-op
once already removed.
"""

import frappe

REPORTS = (
    "General Ledger TH",
    "Trial Balance TH",
    "Trial Balance TH Detail",
)


def execute():
    for report in REPORTS:
        if frappe.db.exists("Report", report):
            frappe.delete_doc("Report", report, force=True, ignore_missing=True)

    frappe.db.commit()
