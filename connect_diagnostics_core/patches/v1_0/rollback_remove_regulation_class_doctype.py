# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_regulation_class_doctype — one-way.

The forward patch deleted the Regulation Class DocType; its JSON/controller files were
also removed from the repo in the same change, and its records are gone. No automatic
reversal is performed.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_remove_regulation_class_doctype: no-op; deleted DocType and rows are "
        "not recoverable. Restore connect_diagnostics_stock/doctype/regulation_class/ "
        "from git history and re-run `bench migrate` if the DocType must come back."
    )
