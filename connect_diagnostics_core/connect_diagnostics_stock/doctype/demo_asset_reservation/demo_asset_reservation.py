# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe
from frappe import _
from frappe.model.document import Document


class DemoAssetReservation(Document):
    def before_insert(self) -> None:
        if not getattr(frappe.flags, "demo_asset_reservation_internal", False):
            frappe.throw(_("Demo Asset Reservations are created only by the planner."))

    def validate(self) -> None:
        if not getattr(frappe.flags, "demo_asset_reservation_internal", False):
            frappe.throw(_("Demo Asset Reservations can only be changed by the planner."))
        if self.status == "Active" and self.active_asset_key != self.asset:
            frappe.throw(_("An active reservation key must match its Asset."))
        if self.status != "Active" and self.active_asset_key:
            frappe.throw(_("Inactive reservations cannot keep an active Asset key."))
        if self.reservation_type == "Returning Asset" and not self.expected_available_on:
            frappe.throw(_("Returning Asset reservations require an expected availability date."))
        if self.reservation_type == "Existing Asset" and self.expected_available_on:
            frappe.throw(_("Existing Asset reservations cannot have a future availability date."))
        allocation_parent = frappe.db.get_value(
            "Material Request Fulfillment Allocation", self.fulfillment_allocation, "parent"
        )
        if allocation_parent != self.fulfillment:
            frappe.throw(_("Reservation allocation must belong to its Fulfillment."))

    if TYPE_CHECKING:
        from frappe.types import DF

        active_asset_key: DF.Data
        asset: DF.Link
        expected_available_on: DF.Date | None
        fulfillment: DF.Link
        fulfillment_allocation: DF.Link
        status: DF.Literal["Active", "Released", "Consumed"]
        reservation_type: DF.Literal["Existing Asset", "Returning Asset"]
