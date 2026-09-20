# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Backfill sales_representative_employee on already-submitted Quotations.

Nothing enforced sales_representative_employee before this app's submit-time
validation (see validate_signatory_before_submit in api/erpnext/quotation.py)
was added, so a submitted, effectively immutable Quotation could resolve to
signatory type "Sales Representative" with no Employee -- print-time then
throws with "Sales Representative is required when a Sales Representative
signs the quotation." This resolves the Employee the same way
set_sales_representative_default() does client-side: the Active Employee
linked to the document owner's user account. Documents that can't be resolved
this way are logged and left for manual follow-up, not blocked.
"""

from __future__ import annotations

import frappe

from connect_diagnostics_core.setup import quotation as quotation_setup


def execute() -> None:
    backfilled = 0
    quotations = frappe.get_all(
        "Quotation",
        filters={
            "docstatus": 1,
            "sales_representative_employee": ("in", ("", None)),
        },
        fields=["name", "owner", "quotation_signatory_type"],
    )
    for quotation in quotations:
        signatory_type = quotation.quotation_signatory_type or quotation_setup.SIGNATORY_SALES_REPRESENTATIVE
        if signatory_type not in quotation_setup.SIGNATORY_PRINTS_NAME:
            continue

        employee = frappe.db.get_value(
            "Employee",
            {"user_id": quotation.owner, "status": "Active"},
            "name",
        )
        if not employee:
            frappe.log_error(
                title="backfill_quotation_signatory_employee",
                message=(
                    f"Could not resolve an Active Employee for {quotation.name} "
                    f"(owner: {quotation.owner}). Needs manual follow-up."
                ),
            )
            continue

        frappe.db.set_value("Quotation", quotation.name, "sales_representative_employee", employee)
        backfilled += 1

    frappe.db.commit()
    frappe.logger(__name__).info(
        f"backfill_quotation_signatory_employee: backfilled {backfilled} document(s)"
    )
