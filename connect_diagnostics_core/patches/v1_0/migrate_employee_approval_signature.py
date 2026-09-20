# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Replace the legacy Quotation-only Employee signature with a generic approval signature.

The old ``quotation_signature`` field became the source for approval snapshots outside
Quotation, so its name no longer reflects its actual purpose. This patch creates the
new ``approval_signature`` field from the setup definition, preserves any existing
signature value when the new field is blank, and then removes the legacy Custom Field
and database column.

The patch is idempotent: once the legacy field is gone, rerunning it only ensures that
the new setup-managed field exists.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup.employee import CUSTOM_FIELDS as EMPLOYEE_CUSTOM_FIELDS

EMPLOYEE = "Employee"
LEGACY_FIELD = "quotation_signature"
APPROVAL_FIELD = "approval_signature"
APPROVAL_SIGNATURE_FIELD = next(
    field for field in EMPLOYEE_CUSTOM_FIELDS[EMPLOYEE] if field["fieldname"] == APPROVAL_FIELD
)


def execute() -> None:
    create_custom_fields({EMPLOYEE: [APPROVAL_SIGNATURE_FIELD]}, update=True)

    if frappe.db.has_column(EMPLOYEE, LEGACY_FIELD):
        frappe.db.sql(
            """
            UPDATE `tabEmployee`
            SET approval_signature = quotation_signature
            WHERE COALESCE(approval_signature, '') = ''
              AND COALESCE(quotation_signature, '') != ''
            """
        )

    custom_field = frappe.db.get_value(
        "Custom Field",
        {"dt": EMPLOYEE, "fieldname": LEGACY_FIELD},
        "name",
    )
    if custom_field:
        frappe.delete_doc("Custom Field", custom_field, ignore_permissions=True, force=True)

    if frappe.db.has_column(EMPLOYEE, LEGACY_FIELD):
        frappe.db.sql_ddl("ALTER TABLE `tabEmployee` DROP COLUMN `quotation_signature`")

    frappe.clear_cache(doctype=EMPLOYEE)
    frappe.db.commit()
