# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for restructure_employee_names — one-way.

The forward patch restructured the Thai employee-name custom fields into the new name
layout and removed the old custom_*_th fields. The prior field structure and any dropped
column data are not retained. No automatic reversal is performed."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_restructure_employee_names: no-op; prior employee-name field structure is not recoverable."
    )
