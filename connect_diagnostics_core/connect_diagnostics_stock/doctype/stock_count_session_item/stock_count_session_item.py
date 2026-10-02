# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class StockCountSessionItem(Document):
    def validate(self) -> None:
        if int(self.get("evidence_revision") or 0) < 1 or not self.get("line_key"):
            frappe.throw(_("Count line must have a captured revision and identity key."))
        if self.get("line_state") not in {"Pending", "Counted", "Recounted", "Invalidated"}:
            frappe.throw(_("Count line has an invalid evidence state."))
