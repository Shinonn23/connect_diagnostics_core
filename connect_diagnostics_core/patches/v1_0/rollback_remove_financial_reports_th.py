# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_financial_reports_th.

These were ``is_standard: "Yes"`` Script Reports, so their logic (.py/.js)
lived in source, not the database — deleting the ``Report`` record alone does
not destroy anything recoverable from data. To restore:

1. Restore the three report folders from git history (before the commit that
   removed them) under
   ``connect_diagnostics_accounting/report/{general_ledger_th,trial_balance_th,
   trial_balance_th_detail}``.
2. Restore the "Financial Reports" ``NavigationGroup``/``SidebarPlacement``
   entries and the ``RETIRED_SIDEBAR_LINKS`` / ``RETIRED_CARD_LINKS`` removals
   in ``setup/workspace.py``.
3. Run ``bench migrate`` — Frappe reimports standard Reports from source and
   ``ensure_workspace_navigation`` re-adds their shortcuts.

Not registered in patches.txt (manual rollback utility only), matching the
existing rollback_remove_customer_name_th_field.py convention. There is no
DB-only reconstruction possible for Script Report source code.
"""

import frappe
from frappe import _


def execute():
    frappe.throw(
        _(
            "Restoring General Ledger TH / Trial Balance TH / Trial Balance TH Detail requires "
            "restoring their report folders from git history and re-running `bench migrate` — "
            "see this file's module docstring. There is nothing this script can do purely "
            "against the database."
        )
    )
