# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class StockCountAdjustment(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        entry_type: DF.Literal["Material Transfer", "Material Receipt", "Material Issue"]
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        remarks: DF.Data | None
        stock_entry: DF.Link | None
    # end: auto-generated types
    pass
