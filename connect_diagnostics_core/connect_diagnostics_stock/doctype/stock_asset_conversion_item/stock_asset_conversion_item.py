# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.model.document import Document


class StockAssetConversionItem(Document):
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        batch_no: DF.Link | None
        item_code: DF.Link
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        qty: DF.Float
        serial_and_batch_bundle: DF.Link | None
        serial_no: DF.SmallText | None
        stock_qty: DF.Float
        stock_uom: DF.Link | None
        uom: DF.Link | None
        warehouse: DF.Link
