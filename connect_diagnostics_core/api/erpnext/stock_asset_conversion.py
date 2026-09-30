# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _

from connect_diagnostics_core.connect_diagnostics_stock.doctype.stock_asset_conversion.stock_asset_conversion import (
    StockAssetConversion,
)


@frappe.whitelist(methods=["POST"])
def approve_preview(conversion: str) -> dict[str, Any]:
    if not set(frappe.get_roles()) & {"Accounts Manager", "System Manager"}:
        frappe.throw(
            _("Only Accounts Manager or System Manager can approve a conversion preview."),
            frappe.PermissionError,
        )
    doc = cast(StockAssetConversion, frappe.get_doc("Stock Asset Conversion", conversion))
    if doc.docstatus != 0:
        frappe.throw(_("Only a Draft conversion can be previewed."))
    if not frappe.has_permission("Stock Asset Conversion", "write", doc=doc):
        frappe.throw(_("You do not have permission to review this conversion."), frappe.PermissionError)
    if not doc.fulfillment_allocation:
        frappe.throw(_("Preview approval is available only for linked Demo conversions."))
    doc.validate()
    facts = doc.build_preview_facts()
    if (
        doc.accounting_treatment != facts["recommendation"]
        and not (doc.treatment_override_reason or "").strip()
    ):
        frappe.throw(
            _("A Treatment Override Reason is required when treatment differs from the recommendation.")
        )
    doc.db_set(
        {
            "preview_stock_value": facts["stock_value"],
            "preview_valuation_rate": facts["valuation_rate"],
            "preview_recommendation": facts["recommendation"],
            "preview_hash": facts["preview_hash"],
            "preview_approved_by": frappe.session.user,
            "preview_approved_on": frappe.utils.now_datetime(),
        },
        update_modified=False,
    )
    return {"data": {"name": doc.name, "facts": facts}, "message": _("Conversion preview approved.")}
