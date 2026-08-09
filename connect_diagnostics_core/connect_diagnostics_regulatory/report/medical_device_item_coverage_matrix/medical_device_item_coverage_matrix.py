# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe import _


def execute(filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    del filters
    rows = frappe.db.sql(
        """
        SELECT item.name AS item_code, item.item_name, product.newcode, product.identifier, product.pack_quantity,
            product.pack_uom, registration.registration_number, registration.expiry_date, registration.official_status,
            COALESCE(SUM(bin.actual_qty), 0) AS current_stock
        FROM `tabMedical Device Registered Product` AS product
        INNER JOIN `tabMedical Device Product Registration` AS registration ON registration.name = product.parent
        INNER JOIN `tabItem` AS item ON item.name = product.item_code
        LEFT JOIN `tabBin` AS bin ON bin.item_code = item.name
        WHERE product.line_status = 'Active'
        GROUP BY item.name, item.item_name, product.name, registration.name
        ORDER BY item.name, product.newcode
        """, as_dict=True
    )
    return _columns(), rows


def _columns() -> list[dict[str, Any]]:
    return [
        {"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
        {"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
        {"fieldname": "newcode", "label": _("NEWCODE"), "fieldtype": "Data", "width": 220},
        {"fieldname": "identifier", "label": _("Identifier"), "fieldtype": "Data", "width": 160},
        {"fieldname": "registration_number", "label": _("Registration"), "fieldtype": "Data", "width": 170},
        {"fieldname": "expiry_date", "label": _("Registration Expiry"), "fieldtype": "Date", "width": 110},
        {"fieldname": "official_status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "current_stock", "label": _("Current Stock"), "fieldtype": "Float", "width": 110},
    ]
