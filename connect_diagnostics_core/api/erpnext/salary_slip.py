# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Submission guard restricting Salary Slip submission to Payroll Entry."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


def validate_submission(doc: Document, _method: str | None = None) -> None:
    """Allow Salary Slip submission only through a Payroll Entry batch."""
    if not frappe.flags.via_payroll_entry:
        frappe.throw(
            _("Salary Slips can only be submitted from Payroll Entry."),
            title=_("Submit from Payroll Entry"),
        )
