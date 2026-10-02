# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document


class RepostWarehouseReservation(Document):
    pass


def on_doctype_update() -> None:
    frappe.db.add_index("Repost Warehouse Reservation", ["warehouse", "parent"], "warehouse_parent")
