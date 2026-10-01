# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.erpnext import regulatory
from connect_diagnostics_core.connect_diagnostics_dksh import reference


def get_item_dashboard_data(data: dict[str, Any]) -> dict[str, Any]:
    """Surface the linked regulatory masters and DKSH Item under Connections."""
    data = reference.inject_connection(
        data,
        reference_doctype="DKSH Item",
        link_field="item",
        group_label=_("Reference"),
    )
    return regulatory.inject_item_dashboard_connections(data)


def validate(doc: Document, method: str) -> None:
    """Validate Item regulatory classification and refresh derived coverage."""
    del method
    if doc.get("allow_borrow") and (
        not doc.get("is_stock_item") or doc.get("has_serial_no") or doc.get("has_batch_no")
    ):
        frappe.throw(_("Only non-serialized, non-batched Stock Items can allow Borrow."))
    regulatory.validate_item_classification(doc)
