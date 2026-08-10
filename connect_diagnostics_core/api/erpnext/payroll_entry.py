# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Payroll Entry controls for reviewed Salary Slip submission."""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _
from hrms.payroll.doctype.payroll_entry.payroll_entry import (
    PayrollEntry,
)
from hrms.payroll.doctype.payroll_entry.payroll_entry import (
    submit_salary_slips_for_employees as submit_hrms_salary_slips_for_employees,
)

from connect_diagnostics_core.setup.accounting_dimension import DEPARTMENT_DIMENSION_FIELDNAME
from connect_diagnostics_core.setup.payroll import SALARY_SLIP_REVIEWED_STATE


class PayrollEntryAccountingDimensionMixin:
    """Keep the HR-Department employee filter out of Accounting Department GL rows.

    HRMS's ``update_accounting_dimensions`` copies each enabled dimension value
    off the Payroll Entry itself (``row.update({dimension: self.get(dimension)})``).
    Payroll Entry's own ``department`` field is the HR Department used to filter
    employees, but the registered Accounting Dimension ``department`` field is a
    Link to Accounting Department — so without this override every generated
    Journal Entry Account row would receive an HR Department docname in a field
    that expects an Accounting Department record. Blank it instead; per-employee
    Accounting Department resolution is intentionally out of scope here.
    """

    def update_accounting_dimensions(
        self: PayrollEntry, row: dict[str, Any], accounting_dimensions: list[str]
    ) -> dict[str, Any]:
        row = PayrollEntry.update_accounting_dimensions(self, row, accounting_dimensions)
        if DEPARTMENT_DIMENSION_FIELDNAME in accounting_dimensions:
            row[DEPARTMENT_DIMENSION_FIELDNAME] = None
        return row


class PayrollEntryReviewMixin:
    """Require every draft Salary Slip to pass review before batch submission."""

    def submit_salary_slips(self: PayrollEntry) -> None:
        self.check_permission("write")
        salary_slips = self.get_sal_slip_list(ss_status=0)
        payroll_entry_name = cast(str, self.name or "")
        validate_salary_slip_reviews(payroll_entry_name)

        if len(salary_slips) > 30 or frappe.flags.enqueue_payroll_entry:
            self.db_set("status", "Queued")
            frappe.enqueue(
                submit_reviewed_salary_slips_for_employees,
                queue="long",
                timeout=3000,
                job_id=f"payroll-entry-submit-{self.name}",
                deduplicate=True,
                enqueue_after_commit=True,
                payroll_entry=self,
                salary_slips=salary_slips,
                publish_progress=False,
            )
            frappe.msgprint(
                _("Salary Slip submission is queued. It may take a few minutes"),
                alert=True,
                indicator="blue",
            )
            return

        submit_reviewed_salary_slips_for_employees(self, salary_slips, publish_progress=False)


def validate_salary_slip_reviews(payroll_entry_name: str) -> None:
    """Reject a Payroll Entry before submission if any draft slip is not reviewed."""
    salary_slip = frappe.qb.DocType("Salary Slip")
    unreviewed = (
        frappe.qb.from_(salary_slip)
        .select(salary_slip.name)
        .where(
            (salary_slip.payroll_entry == payroll_entry_name)
            & (salary_slip.docstatus == 0)
            & (
                (salary_slip.salary_slip_review_state != SALARY_SLIP_REVIEWED_STATE)
                | salary_slip.salary_slip_review_state.isnull()
                | (salary_slip.salary_slip_review_state == "")
            )
        )
        .orderby(salary_slip.name)
    ).run(pluck=True)
    if not unreviewed:
        return

    links = ", ".join(frappe.get_desk_link("Salary Slip", name) for name in unreviewed)
    frappe.throw(
        _("All Salary Slips must be reviewed before submission. Unreviewed: {0}").format(links),
        title=_("Salary Slip review required"),
    )


def submit_reviewed_salary_slips_for_employees(
    payroll_entry: PayrollEntry,
    salary_slips: list[Any],
    publish_progress: bool = True,
) -> None:
    """Repeat review validation in queued work, then delegate to HRMS unchanged."""
    validate_salary_slip_reviews(cast(str, payroll_entry.name))
    submit_hrms_salary_slips_for_employees(payroll_entry, salary_slips, publish_progress=publish_progress)
