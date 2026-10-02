# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class StockCountSessionLocation(Document):
    def validate(self) -> None:
        if int(self.get("evidence_revision") or 0) < 1:
            frappe.throw(_("Count location must belong to a captured evidence revision."))
        if self.get("coverage_state") not in {"Not Started", "Counted", "Invalidated"}:
            frappe.throw(_("Count location has an invalid coverage state."))
