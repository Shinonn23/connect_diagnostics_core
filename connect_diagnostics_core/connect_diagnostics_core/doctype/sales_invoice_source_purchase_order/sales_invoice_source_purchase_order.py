# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""One source Purchase Order copy required on a Sales Invoice.

A tax invoice can carry goods from several Purchase Orders, so the source copy is
a table: one row per Purchase Order, each with its own copy count. A row names
either a linked Purchase Order or, for one raised before ERPNext, an attached
file.
"""

from __future__ import annotations

from frappe.model.document import Document


class SalesInvoiceSourcePurchaseOrder(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        copies: DF.Int
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        purchase_order: DF.Link | None
        purchase_order_file: DF.Attach | None
    # end: auto-generated types

    pass
