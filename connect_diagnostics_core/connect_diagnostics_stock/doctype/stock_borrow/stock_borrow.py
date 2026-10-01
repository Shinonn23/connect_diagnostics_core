# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document


def derive_status(*, issued: float, returned: float, pending_issue: float, outstanding: float) -> str:
    if not issued:
        return "Pending Issue"
    if pending_issue:
        return "Partially Issued"
    if not outstanding:
        return "Returned"
    if returned:
        return "Partially Returned"
    return "Issued"


class StockBorrow(Document):
    def before_insert(self) -> None:
        if not self.flags.get("from_borrow_service"):
            frappe.throw(_("Stock Borrow records must be created through the Borrow service."))

    def validate(self) -> None:
        items = cast(list[Any], self.get("items") or [])
        if not items:
            frappe.throw(_("Stock Borrow must contain at least one item."))
        if (
            not self.flags.get("from_borrow_service")
            and not self.flags.get("from_borrow_rebuild")
            and not self.is_new()
        ):
            previous = frappe.db.get_value(
                "Stock Borrow",
                self.name,
                [
                    "material_request",
                    "company",
                    "responsible_employee",
                    "destination_type",
                    "destination_customer",
                    "destination_address",
                    "expected_return_date",
                    "borrow_warehouse",
                    "return_hold_warehouse",
                    "issued_qty",
                    "returned_qty",
                    "pending_issue_qty",
                    "outstanding_qty",
                    "status",
                ],
                as_dict=True,
            )
            protected = [
                "material_request",
                "company",
                "responsible_employee",
                "destination_type",
                "destination_customer",
                "destination_address",
                "expected_return_date",
                "borrow_warehouse",
                "return_hold_warehouse",
                "issued_qty",
                "returned_qty",
                "pending_issue_qty",
                "outstanding_qty",
                "status",
            ]
            if previous and any(self.get(field) != previous.get(field) for field in protected):
                frappe.throw(_("Stock Borrow identity and derived fields are service-managed."))
            old_items = frappe.get_all(
                "Stock Borrow Item",
                filters={"parent": self.name},
                fields=["material_request_item", "item_code", "uom", "requested_qty"],
                order_by="idx asc",
            )
            new_items = [
                {
                    "material_request_item": row.material_request_item,
                    "item_code": row.item_code,
                    "uom": row.uom,
                    "requested_qty": row.requested_qty,
                }
                for row in items
            ]
            if old_items != new_items:
                frappe.throw(_("Stock Borrow item identity and requested quantities are service-managed."))
        issued = sum(row.issued_qty or 0 for row in items)
        returned = sum(row.returned_qty or 0 for row in items)
        pending_issue = sum(row.pending_issue_qty or 0 for row in items)
        outstanding = sum(row.outstanding_qty or 0 for row in items)
        self.set("issued_qty", issued)
        self.set("returned_qty", returned)
        self.set("pending_issue_qty", pending_issue)
        self.set("outstanding_qty", outstanding)
        self.set(
            "status",
            derive_status(
                issued=issued,
                returned=returned,
                pending_issue=pending_issue,
                outstanding=outstanding,
            ),
        )
