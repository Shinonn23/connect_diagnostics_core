# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_alias_name_doctype — one-way.

The forward patch deleted the Alias Name and Alias Supported DocType DocTypes after their
Item rows were migrated into Item Alternative Name. The DocTypes and their records are gone;
migrated aliases live on the Item child table. No automatic reversal is performed."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_remove_alias_name_doctype: no-op; deleted DocTypes and rows are not recoverable (migrated to Item Alternative Name)."
    )
