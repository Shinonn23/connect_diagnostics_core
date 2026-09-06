# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for migrate_accounting_departments_to_departments — one-way."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_migrate_accounting_departments_to_departments: no-op; Accounting Department "
        "rows were migrated to Department and the source DocType was deleted."
    )
