# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class StockCountItem(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        batch_no: DF.Link | None
        count_qty: DF.Float
        expiry_date: DF.Date | None
        item_code: DF.Link
        item_name: DF.Data | None
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        serial_and_batch_bundle: DF.Link | None
        serial_no: DF.SmallText | None
        stock_uom: DF.Link | None
        system_qty: DF.Float
        valuation_rate: DF.Currency
        variance_qty: DF.Float
        warehouse: DF.Link | None
    # end: auto-generated types
    pass
