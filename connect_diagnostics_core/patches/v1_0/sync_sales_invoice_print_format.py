# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Synchronize the app-owned Sales Invoice Print Format record."""

from __future__ import annotations

import frappe


def execute() -> None:
    """Load the current source Print Format, including traceability rendering."""
    frappe.reload_doc(
        "Connect Diagnostics Print",
        "print_format",
        "tax_invoice_delivery_note_and_invoice",
        force=True,
    )
