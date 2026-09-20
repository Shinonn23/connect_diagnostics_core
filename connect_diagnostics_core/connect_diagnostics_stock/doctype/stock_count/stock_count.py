# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
import frappe.defaults
from frappe import _
from frappe.model.document import Document

MONTHLY = "Cycle Count (Monthly)"
YEARLY = "Yearly Count"


class StockCount(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        from connect_diagnostics_core.connect_diagnostics_stock.doctype.stock_count_adjustment.stock_count_adjustment import (
            StockCountAdjustment,
        )
        from connect_diagnostics_core.connect_diagnostics_stock.doctype.stock_count_item.stock_count_item import (
            StockCountItem,
        )

        adjustments: DF.Table[StockCountAdjustment]
        amended_from: DF.Link | None
        company: DF.Link
        count_type: DF.Literal["Cycle Count (Monthly)", "Yearly Count"]
        holding_warehouse: DF.Link | None
        items: DF.Table[StockCountItem]
        naming_series: DF.Literal["STK-CNT-.YYYY.-"]
        posting_date: DF.Date
        posting_time: DF.Time
        remarks: DF.SmallText | None
        sample_count: DF.Int
        sample_percentage: DF.Percent
        selection_method: DF.Literal["Manual", "Random by Count", "Random by Percentage", "Random by Zone"]
        storage_location: DF.Link | None
        total_variance_qty: DF.Float
        warehouse: DF.Link
    # end: auto-generated types

    def validate(self) -> None:
        self.set_defaults()
        self.validate_scope()
        self.validate_duplicate_lines()
        self.update_variance()

    def before_submit(self) -> None:
        if not self.items:
            frappe.throw(_("Add at least one count line before submitting."))

    def set_defaults(self) -> None:
        if not self.company:
            self.company = frappe.defaults.get_user_default("Company")
        if self.count_type == MONTHLY and not self.holding_warehouse:
            self.holding_warehouse = frappe.db.get_single_value("Stock Settings", "default_holding_warehouse")

    def validate_scope(self) -> None:
        if self.count_type != MONTHLY:
            return
        if self.selection_method == "Random by Count" and self.sample_count <= 0:
            frappe.throw(_("Sample Count must be greater than zero for Random by Count."))
        if self.selection_method == "Random by Percentage" and not 0 < self.sample_percentage <= 100:
            frappe.throw(_("Sample Percentage must be between 0 and 100 for Random by Percentage."))
        if self.selection_method == "Random by Zone" and not self.storage_location:
            frappe.throw(_("Storage Location is required for Random by Zone."))

    def validate_duplicate_lines(self) -> None:
        seen: set[tuple[str, str, str, str, str]] = set()
        for row in self.items:
            key = (
                row.item_code or "",
                row.warehouse or "",
                row.storage_location or "",
                row.batch_no or "",
                (row.serial_no or "").strip(),
            )
            if key in seen:
                frappe.throw(
                    _("Row #{0}: Duplicate count line for the same item, location, batch and serial.").format(
                        row.idx
                    )
                )
            seen.add(key)

    def update_variance(self) -> None:
        total = 0.0
        for row in self.items:
            row.variance_qty = (row.count_qty or 0.0) - (row.system_qty or 0.0)
            total += row.variance_qty
        self.total_variance_qty = total
