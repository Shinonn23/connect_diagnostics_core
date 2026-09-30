# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class DispatchTransfer(Document):
    if TYPE_CHECKING:
        from frappe.types import DF

        asset: DF.Link | None
        fulfillment_allocation: DF.Link | None
        qty: DF.Float

    def validate(self) -> None:
        if not self.fulfillment_allocation:
            return
        allocation = frappe.db.get_value(
            "Material Request Fulfillment Allocation",
            self.fulfillment_allocation,
            ["parent", "resolved_asset", "qty"],
            as_dict=True,
        )
        if not allocation or allocation.resolved_asset != self.asset or flt(self.qty) != 1:
            frappe.throw(_("Dispatch Transfer does not match the Fulfillment allocation."))
        if self.is_new():
            return
        persisted = frappe.db.get_value("Dispatch Transfer", self.name, "fulfillment_allocation")
        if persisted and persisted != self.fulfillment_allocation:
            frappe.throw(_("Dispatch Transfer Fulfillment allocation cannot be changed."))
