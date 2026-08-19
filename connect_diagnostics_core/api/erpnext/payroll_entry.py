# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Payroll Entry accounting-dimension controls."""

from __future__ import annotations

from typing import Any

from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry

from connect_diagnostics_core.setup.accounting_dimension import DEPARTMENT_DIMENSION_FIELDNAME


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
