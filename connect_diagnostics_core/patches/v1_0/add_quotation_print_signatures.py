# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Prepare existing Quotations for the Employee-backed signing flow."""

from __future__ import annotations

import frappe

from connect_diagnostics_core.setup import quotation as quotation_setup


def execute() -> None:
    """Give legacy blank signatory rows their documented Sales Representative fallback."""
    if not frappe.db.has_column("Quotation", "quotation_signatory_type"):
        return

    frappe.db.sql(
        """
        update `tabQuotation`
        set quotation_signatory_type = %s
        where ifnull(quotation_signatory_type, '') = ''
        """,
        quotation_setup.SIGNATORY_SALES_REPRESENTATIVE,
    )
    frappe.db.commit()
