# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Install the Salary Slip review workflow and preserve existing document states."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup.payroll import (
    CUSTOM_FIELDS,
    SALARY_SLIP_CANCELLED_STATE,
    SALARY_SLIP_DRAFT_STATE,
    SALARY_SLIP_SUBMITTED_STATE,
    ensure_salary_slip_review_workflow,
)

_BACKFILL_QUERY = """
    UPDATE `tabSalary Slip`
    SET `salary_slip_review_state` = %s
    WHERE `docstatus` = %s
      AND (`salary_slip_review_state` IS NULL OR `salary_slip_review_state` = '')
"""


def execute() -> None:
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
    ensure_salary_slip_review_workflow()
    _backfill_salary_slip_review_states()


def _backfill_salary_slip_review_states() -> None:
    for docstatus, review_state in (
        (0, SALARY_SLIP_DRAFT_STATE),
        (1, SALARY_SLIP_SUBMITTED_STATE),
        (2, SALARY_SLIP_CANCELLED_STATE),
    ):
        frappe.db.sql(
            _BACKFILL_QUERY,
            (review_state, docstatus),
        )
