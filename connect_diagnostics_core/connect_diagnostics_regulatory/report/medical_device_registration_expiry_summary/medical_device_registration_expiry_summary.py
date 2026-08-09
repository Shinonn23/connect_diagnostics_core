# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

from frappe import _

from connect_diagnostics_core.api.erpnext.regulatory_reporting import registration_rows


def execute(filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _columns(), registration_rows(filters)


def _columns() -> list[dict[str, Any]]:
    return [
        {"fieldname": "registration_number", "label": _("Registration"), "fieldtype": "Link", "options": "Medical Device Product Registration", "width": 180},
        {"fieldname": "certificate_type", "label": _("Certificate Type"), "fieldtype": "Data", "width": 130},
        {"fieldname": "device_category", "label": _("Category"), "fieldtype": "Data", "width": 100},
        {"fieldname": "product_family_name", "label": _("Product Family"), "fieldtype": "Data", "width": 180},
        {"fieldname": "expiry_date", "label": _("Expiry Date"), "fieldtype": "Date", "width": 100},
        {"fieldname": "days_remaining", "label": _("Days Remaining"), "fieldtype": "Int", "width": 100},
        {"fieldname": "renewal_status", "label": _("Renewal Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "responsible_user", "label": _("Responsible User"), "fieldtype": "Link", "options": "User", "width": 150},
        {"fieldname": "affected_item_count", "label": _("Affected Items"), "fieldtype": "Int", "width": 100},
        {"fieldname": "current_stock_qty", "label": _("Current Stock"), "fieldtype": "Float", "width": 110},
        {"fieldname": "stock_value", "label": _("Stock Value"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "open_po_qty", "label": _("Open PO"), "fieldtype": "Float", "width": 90},
        {"fieldname": "open_so_qty", "label": _("Open SO"), "fieldtype": "Float", "width": 90},
    ]
