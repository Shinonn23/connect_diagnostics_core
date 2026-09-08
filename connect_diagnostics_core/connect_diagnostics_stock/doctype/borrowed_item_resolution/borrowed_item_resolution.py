# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

RETURNABLE_USAGES = frozenset({"Employee Borrow", "Customer Demo", "Customer Loan"})


class BorrowedItemResolution(Document):
    def validate(self) -> None:
        self._validate_request()
        if self.get("resolution_type") not in {"Settlement", "Write-off"}:
            frappe.throw(_("Resolution Type must be Settlement or Write-off."))
        self._validate_items()
        self._validate_not_already_resolved()
        if self.get("resolution_type") == "Settlement":
            self._validate_settlement()
        elif self.get("resolution_type") == "Write-off":
            self._validate_write_off()

    def before_cancel(self) -> None:
        if self.get("stock_entry") or frappe.db.exists(
            "Asset Movement", {"reference_doctype": self.doctype, "reference_name": self.name, "docstatus": 1}
        ):
            frappe.throw(
                _("Discard or reverse native resolution movements before cancelling this Resolution.")
            )
        if any(
            row.get("asset")
            and frappe.db.get_value("Asset", row.get("asset"), "status") in {"Scrapped", "Sold"}
            for row in self.get("items", [])
        ):
            frappe.throw(
                _("Cancel the native Asset sale or scrap transaction before cancelling this Resolution.")
            )

    def on_submit(self) -> None:
        self._create_stock_resolution()
        self._resolve_assets()

    def _validate_request(self) -> None:
        request = frappe.db.get_value(
            "Material Request",
            self.get("material_request"),
            ["company", "docstatus", "request_usage"],
            as_dict=True,
        )
        if not request or request.docstatus != 1 or request.request_usage not in RETURNABLE_USAGES:
            frappe.throw(_("Borrowed Item Resolution requires a submitted returnable Material Request."))
        if request.get("company") != self.get("company"):
            frappe.throw(_("Resolution and Material Request must belong to the same Company."))

    def _validate_items(self) -> None:
        if not self.get("items"):
            frappe.throw(_("Add at least one item to resolve."))
        seen: set[tuple[str, str]] = set()
        for row in self.get("items", []):
            if flt(row.get("qty")) <= 0:
                frappe.throw(_("Row {0}: Quantity must be greater than zero.").format(row.idx))
            item = frappe.db.get_value(
                "Material Request Item",
                row.get("material_request_item"),
                ["parent", "item_code", "fulfillment_route"],
                as_dict=True,
            )
            if (
                not item
                or item.get("parent") != self.get("material_request")
                or item.get("item_code") != row.get("item_code")
            ):
                frappe.throw(_("Row {0}: Item does not belong to the Material Request.").format(row.idx))
            if (row.get("material_request_item"), row.get("asset") or "") in seen:
                frappe.throw(_("Row {0}: Duplicate resolution line.").format(row.idx))
            seen.add((row.get("material_request_item"), row.get("asset") or ""))
            if item.get("fulfillment_route") in {"Existing Asset", "Stock Capitalization"}:
                if not row.get("asset") or flt(row.get("qty")) != 1:
                    frappe.throw(_("Row {0}: Asset resolution must contain one Asset.").format(row.idx))
            elif not row.get("warehouse"):
                frappe.throw(
                    _("Row {0}: Current Warehouse is required for stock resolution.").format(row.idx)
                )
            elif row.get("warehouse") not in self._allowed_stock_warehouses():
                frappe.throw(
                    _(
                        "Row {0}: Resolution must use the current Borrow, QA Hold, or Repair Warehouse."
                    ).format(row.idx)
                )
            if row.get("against_dispatch_transfer"):
                self._validate_against_transfer(row)
            if (
                self.get("resolution_type") == "Write-off"
                and self.get("write_off_reason") == "Damaged Beyond Repair"
            ):
                self._validate_damaged_return(row)

    def _validate_against_transfer(self, row: Any) -> None:
        transfer = frappe.db.get_value(
            "Dispatch Transfer",
            row.get("against_dispatch_transfer"),
            ["parent", "material_request_item", "item_code", "asset"],
            as_dict=True,
        )
        dispatch = (
            frappe.db.get_value(
                "Dispatch",
                transfer.get("parent"),
                ["material_request", "dispatch_type", "delivery_status", "docstatus"],
                as_dict=True,
            )
            if transfer
            else None
        )
        if (
            not transfer
            or not dispatch
            or dispatch.get("docstatus") != 1
            or dispatch.get("dispatch_type") != "Return"
            or dispatch.get("delivery_status") != "Delivered"
            or transfer.get("material_request_item") != row.get("material_request_item")
            or transfer.get("item_code") != row.get("item_code")
            or (transfer.get("asset") or "") != (row.get("asset") or "")
        ):
            frappe.throw(
                _("Row {0}: Resolution reference must be a delivered Return Dispatch line.").format(row.idx)
            )

    def _validate_damaged_return(self, row: Any) -> None:
        if not row.get("against_dispatch_transfer"):
            frappe.throw(_("Row {0}: Damaged Beyond Repair requires a Return Dispatch line.").format(row.idx))
        if row.get("asset"):
            valid = frappe.db.exists(
                "Borrowed Asset Return Inspection",
                {
                    "return_dispatch_transfer": row.get("against_dispatch_transfer"),
                    "asset": row.get("asset"),
                    "inspection_result": "Rejected",
                    "return_disposition": "Damaged Beyond Repair",
                    "docstatus": 1,
                },
            )
        else:
            valid = frappe.db.exists(
                "Quality Inspection",
                {
                    "return_dispatch_transfer": row.get("against_dispatch_transfer"),
                    "status": "Rejected",
                    "return_disposition": "Damaged Beyond Repair",
                    "docstatus": 1,
                },
            )
        if not valid:
            frappe.throw(_("Row {0}: Damaged stock requires a rejected QA inspection.").format(row.idx))

    def _validate_not_already_resolved(self) -> None:
        existing = frappe.db.sql(
            """
            SELECT ri.material_request_item, ri.asset, COALESCE(SUM(ri.qty), 0) AS qty
            FROM `tabBorrowed Item Resolution Item` ri
            INNER JOIN `tabBorrowed Item Resolution` r ON r.name = ri.parent
            WHERE r.material_request = %s AND r.docstatus = 1 AND r.name != %s
            GROUP BY ri.material_request_item, ri.asset
            """,
            (self.get("material_request"), self.name or ""),
            as_dict=True,
        )
        existing_by_key = {
            (row.material_request_item, row.asset or ""): float(row.qty or 0) for row in existing
        }
        current_by_key: dict[tuple[str, str], float] = {}
        for row in self.get("items", []):
            key = (row.get("material_request_item"), row.get("asset") or "")
            current_by_key[key] = current_by_key.get(key, 0.0) + float(row.get("qty") or 0)

        for row in self.get("items", []):
            item = frappe.db.get_value(
                "Material Request Item",
                row.get("material_request_item"),
                ["stock_qty", "fulfillment_route"],
                as_dict=True,
            )
            if not item:
                continue
            key = (row.get("material_request_item"), row.get("asset") or "")
            limit = (
                1.0
                if item.get("fulfillment_route") in {"Existing Asset", "Stock Capitalization"}
                else float(item.get("stock_qty") or 0)
            )
            if existing_by_key.get(key, 0.0) + current_by_key[key] > limit + 0.00001:
                frappe.throw(
                    _("Row {0}: The item has already been resolved in another Resolution.").format(row.idx)
                )

    def _validate_settlement(self) -> None:
        usage = frappe.db.get_value("Material Request", self.get("material_request"), "request_usage")
        if usage not in {"Customer Demo", "Customer Loan"}:
            frappe.throw(_("Settlement is allowed only for Customer Demo or Customer Loan."))
        invoice = frappe.db.get_value(
            "Sales Invoice",
            self.get("sales_invoice"),
            ["docstatus", "status", "outstanding_amount", "customer"],
            as_dict=True,
        )
        customer = frappe.db.get_value(
            "Material Request", self.get("material_request"), "destination_customer"
        )
        if (
            not invoice
            or invoice.docstatus != 1
            or invoice.status != "Paid"
            or flt(invoice.outstanding_amount) > 0
            or invoice.customer != customer
        ):
            frappe.throw(_("Settlement requires a submitted paid Sales Invoice."))

    def _validate_write_off(self) -> None:
        if self.get("write_off_reason") not in {"Missing", "Damaged Beyond Repair"}:
            frappe.throw(_("Select Missing or Damaged Beyond Repair as the write-off reason."))
        if self.get("write_off_reason") == "Missing":
            for row in self.get("items", []):
                if row.get("asset") or row.get("warehouse") != self._borrow_warehouse():
                    frappe.throw(
                        _("Missing items must be resolved from the responsible Employee Borrow Warehouse.")
                    )

    def _borrow_warehouse(self) -> str | None:
        employee = frappe.db.get_value(
            "Material Request", self.get("material_request"), "responsible_employee"
        )
        return frappe.db.get_value("Employee", employee, "borrow_warehouse") if employee else None

    def _allowed_stock_warehouses(self) -> set[str]:
        values = frappe.db.get_value(
            "Company",
            self.get("company"),
            ["return_qa_hold_warehouse", "return_repair_warehouse"],
            as_dict=True,
        )
        return {
            warehouse
            for warehouse in (
                self._borrow_warehouse(),
                values and values.return_qa_hold_warehouse,
                values and values.return_repair_warehouse,
            )
            if warehouse
        }

    def _create_stock_resolution(self) -> None:
        stock_rows = [row for row in self.get("items", []) if not row.get("asset")]
        if not stock_rows:
            return
        entry = frappe.new_doc("Stock Entry")
        entry.update(
            {
                "stock_entry_type": "Material Issue",
                "purpose": "Material Issue",
                "company": self.get("company"),
                "borrowed_item_resolution": self.name,
            }
        )
        for row in stock_rows:
            entry.append(
                "items",
                {
                    "item_code": row.get("item_code"),
                    "qty": row.get("qty"),
                    "s_warehouse": row.get("warehouse"),
                    "material_request": self.get("material_request"),
                    "material_request_item": row.get("material_request_item"),
                },
            )
        entry.insert()
        entry.submit()
        self.db_set("stock_entry", entry.name, update_modified=False)

    def _resolve_assets(self) -> None:
        for row in (item for item in self.get("items", []) if item.get("asset")):
            asset = frappe.get_doc("Asset", row.get("asset"))
            if self.get("resolution_type") == "Settlement":
                if asset.status != "Sold":
                    frappe.throw(
                        _("Asset {0} must be Sold through the native asset sale flow first.").format(
                            row.get("asset")
                        )
                    )
            else:
                from erpnext.assets.doctype.asset.depreciation import scrap_asset

                scrap_asset(asset.name, self.get("resolution_date"))
