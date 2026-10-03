# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from typing import Any

import frappe
from frappe import _

from connect_diagnostics_core.api.erpnext.regulatory_reporting import registration_rows


def execute(filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    report_filters = dict(filters or {})
    report_filters.setdefault("expiry_within_days", 365)
    data: list[dict[str, Any]] = []
    for registration in registration_rows(report_filters):
        for item_code in frappe.get_all(
            "Medical Device Registered Product", filters={"parent": registration["name"]}, pluck="item_code"
        ):
            if item_code:
                data.append({**registration, "item_code": item_code})
    return _columns(), data


def _columns() -> list[dict[str, Any]]:
    return [
        {"fieldname": "registration_number", "label": _("Registration"), "fieldtype": "Data", "width": 180},
        {"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
        {"fieldname": "expiry_date", "label": _("Expiry"), "fieldtype": "Date", "width": 100},
        {"fieldname": "current_stock_qty", "label": _("Warehouse Stock"), "fieldtype": "Float", "width": 120},
        {"fieldname": "open_po_qty", "label": _("Open PO"), "fieldtype": "Float", "width": 100},
        {"fieldname": "open_so_qty", "label": _("Open SO"), "fieldtype": "Float", "width": 100},
        {
            "fieldname": "responsible_user",
            "label": _("Owner"),
            "fieldtype": "Link",
            "options": "User",
            "width": 140,
        },
        {"fieldname": "renewal_status", "label": _("Renewal Status"), "fieldtype": "Data", "width": 130},
    ]
