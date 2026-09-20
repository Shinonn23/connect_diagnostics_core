# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup import procure_to_pay

_CUTOVER_DOCTYPES = (
    "Material Request",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
    "Payment Request",
)
_RETIRED_CUSTOM_FIELDS = {
    "Company": ("low_value_payment_approval_limit",),
    "Payment Request": ("approval_due_at", "payment_approval_limit"),
}
_RETIRED_PAYMENT_STATES = (
    "Escalated Low-Value Payment Request Approval",
    "Escalated Payment Request Approval",
)


def execute() -> None:
    _delete_drafts_for_cutover()
    create_custom_fields(procure_to_pay.CUSTOM_FIELDS, ignore_validate=True)
    _remove_retired_payment_approval_configuration()
    _backfill_legacy_suppliers()
    procure_to_pay.ensure_configuration()
    frappe.clear_cache()


def _remove_retired_payment_approval_configuration() -> None:
    for doctype, fieldnames in _RETIRED_CUSTOM_FIELDS.items():
        for fieldname in fieldnames:
            custom_field = frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname})
            if custom_field:
                frappe.delete_doc("Custom Field", custom_field, force=True, ignore_permissions=True)

    for state in _RETIRED_PAYMENT_STATES:
        frappe.db.set_value(
            "Payment Request",
            {"payment_approval_state": state, "docstatus": 0},
            "payment_approval_state",
            "Payment Request Draft",
            update_modified=False,
        )


def _delete_drafts_for_cutover() -> None:
    for doctype in _CUTOVER_DOCTYPES:
        for name in frappe.get_all(doctype, filters={"docstatus": 0}, pluck="name"):
            frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)


def _backfill_legacy_suppliers() -> None:
    suppliers = cast(list[dict[str, Any]], frappe.get_all("Supplier", fields=["name", "disabled"]))
    updates = {
        row["name"]: {"supplier_onboarding_state": procure_to_pay.SUPPLIER_LEGACY_ACTIVE}
        for row in suppliers
        if not row.get("disabled")
    }
    updates.update(
        {
            row["name"]: {"supplier_onboarding_state": procure_to_pay.SUPPLIER_DRAFT}
            for row in suppliers
            if row.get("disabled")
        }
    )
    if updates:
        frappe.db.bulk_update("Supplier", updates, update_modified=False)
