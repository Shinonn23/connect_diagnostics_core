# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class StockCountSessionScope(Document):
    def validate(self) -> None:
        if self.get("scope_kind") not in {"Warehouse", "Item/Warehouse"}:
            frappe.throw(_("Count scope must identify a Warehouse or Item/Warehouse."))
        if self.get("scope_kind") == "Item/Warehouse" and not self.get("item_code"):
            frappe.throw(_("Cycle Count scope requires an Item."))
        if self.get("scope_kind") == "Warehouse" and self.get("item_code"):
            frappe.throw(_("Full Count scope cannot select a single Item."))
