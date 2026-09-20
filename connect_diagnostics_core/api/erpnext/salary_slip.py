# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Submission guard for the Salary Slip review workflow."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.setup.payroll import SALARY_SLIP_REVIEWED_STATE


def validate_submission(doc: Document, _method: str | None = None) -> None:
    """Allow Salary Slip submission only from the reviewed Payroll Entry batch."""
    if not frappe.flags.via_payroll_entry:
        frappe.throw(
            _("Salary Slips can only be submitted from Payroll Entry."),
            title=_("Submit from Payroll Entry"),
        )

    review_state = str(doc.get("salary_slip_review_state") or "")
    if review_state != SALARY_SLIP_REVIEWED_STATE:
        frappe.throw(
            _("Salary Slip {0} must be reviewed before Payroll Entry can submit it.").format(
                frappe.bold(doc.name or "")
            ),
            title=_("Salary Slip review required"),
        )
