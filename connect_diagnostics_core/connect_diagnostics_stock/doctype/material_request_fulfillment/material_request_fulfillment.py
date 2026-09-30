# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class MaterialRequestFulfillment(Document):
    if TYPE_CHECKING:
        from frappe.types import DF

        from connect_diagnostics_core.connect_diagnostics_stock.doctype.material_request_fulfillment_allocation.material_request_fulfillment_allocation import (
            MaterialRequestFulfillmentAllocation,
        )

        allocations: DF.Table[MaterialRequestFulfillmentAllocation]
        material_request: DF.Link
        operation_id: DF.Data
        source_digest: DF.Data
        source_version: DF.Int
        plan_revision: DF.Int
        status: DF.Literal["Planned", "Superseded", "Cancelled"]

    def before_insert(self) -> None:
        if not getattr(frappe.flags, "material_request_fulfillment_handoff", False):
            frappe.throw(
                _("Material Request Fulfillment can only be created by a submitted Material Request.")
            )

    def validate(self) -> None:
        if not self.is_new():
            frappe.throw(_("Material Request Fulfillment revisions are immutable."))
        if self.source_version != 1 or self.plan_revision < 1 or self.status != "Planned":
            frappe.throw(_("Material Request Fulfillment must have a valid planned revision."))
        requested = {
            row.name: flt(row.qty)
            for row in frappe.get_all(
                "Material Request Item",
                filters={"parent": self.material_request},
                fields=["name", "qty"],
            )
        }
        planned = {name: 0.0 for name in requested}
        for row in self.allocations:
            if row.material_request_item not in requested:
                frappe.throw(_("Every allocation must belong to the linked Material Request."))
            planned[row.material_request_item] += flt(row.qty)
            if row.downstream_doctype or row.downstream_reference:
                frappe.throw(_("Planning cannot attach downstream documents."))
            if self.plan_revision == 1 and row.source_type != "Unplanned":
                frappe.throw(_("Initial allocations must remain Unplanned."))
            if row.source_type == "Unplanned":
                if row.selected_source or row.asset_reservation or row.expected_available_on:
                    frappe.throw(_("Unplanned allocations cannot select an Asset."))
            elif row.source_type == "Stock Conversion":
                if row.selected_source or row.asset_reservation or row.expected_available_on:
                    frappe.throw(_("Stock Conversion allocations cannot select an Asset."))
            elif row.source_type in {"Existing Asset", "Returning Asset"}:
                if flt(row.qty) != 1 or not row.selected_source:
                    frappe.throw(_("Asset allocations require exactly one selected Asset."))
                if row.source_type == "Returning Asset" and not row.expected_available_on:
                    frappe.throw(_("Returning Asset allocations require an expected availability date."))
                if row.source_type == "Existing Asset" and row.expected_available_on:
                    frappe.throw(_("Existing Assets cannot have a future availability date."))
            else:
                frappe.throw(_("Allocation source type is not supported."))
        if not requested or any(abs(planned[name] - qty) > 0.000001 for name, qty in requested.items()):
            frappe.throw(_("Allocation quantities must equal every Material Request row quantity."))
