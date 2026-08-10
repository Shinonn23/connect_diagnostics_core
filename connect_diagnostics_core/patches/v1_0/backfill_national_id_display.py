# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Backfill the read-only ``national_id_display`` field on existing Employee records.

``national_id_display`` is computed by ``normalize_national_id`` on ``Employee.validate``,
so it only gets populated the next time a record is saved. Employees that already had a
``national_id`` before this field existed would otherwise show a blank formatted value
until someone happens to resave them. This patch computes it once from the already-stored
``national_id``.

This patch runs in ``post_model_sync``, which is *before* this app's own ``after_migrate``
hook creates ``national_id_display`` (see ``connect_diagnostics_core.setup.after_migrate``).
So, like ``restructure_employee_names``, it creates the field itself first — reusing the
same definition from ``setup.employee.CUSTOM_FIELDS`` rather than duplicating it — to be
correct on both a fresh migrate and a rerun.

Idempotent: only touches rows where ``national_id_display`` is still blank, so a second run
after all records are backfilled is a no-op. Records whose ``national_id`` isn't a clean
13-digit value with a valid checksum after stripping non-digits are skipped and logged, not
thrown, so pre-existing dirty data doesn't block the migration.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.api.erpnext.employee import (
    NATIONAL_ID_LENGTH,
    clean_national_id,
    format_national_id_display,
    has_valid_national_id_checksum,
)
from connect_diagnostics_core.setup.employee import CUSTOM_FIELDS as EMPLOYEE_CUSTOM_FIELDS

EMPLOYEE = "Employee"
NATIONAL_ID_DISPLAY_FIELD = next(
    field for field in EMPLOYEE_CUSTOM_FIELDS[EMPLOYEE] if field["fieldname"] == "national_id_display"
)


def execute() -> None:
    if not frappe.db.has_column(EMPLOYEE, "national_id"):
        return

    create_custom_fields({EMPLOYEE: [NATIONAL_ID_DISPLAY_FIELD]}, update=True)

    employees = frappe.get_all(
        EMPLOYEE,
        filters={
            "national_id": ["is", "set"],
            "national_id_display": ["is", "not set"],
        },
        fields=["name", "national_id"],
    )

    skipped = 0
    for employee in employees:
        cleaned = clean_national_id(employee.national_id)
        if len(cleaned) != NATIONAL_ID_LENGTH or not has_valid_national_id_checksum(cleaned):
            skipped += 1
            continue

        frappe.db.set_value(
            EMPLOYEE,
            employee.name,
            "national_id_display",
            format_national_id_display(cleaned),
            update_modified=False,
        )

    if skipped:
        frappe.logger(__name__).warning(
            f"backfill_national_id_display: skipped {skipped} Employee record(s) whose national_id "
            "is not a clean 13-digit value with a valid checksum"
        )
