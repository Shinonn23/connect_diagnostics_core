# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class DKSHItemMapping(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        active: DF.Check
        correction_reason: DF.SmallText | None
        dksh_item_code: DF.Data | None
        dksh_response_reference: DF.Data | None
        item: DF.Link | None
        item_channel: DF.Literal["CD and DKSH", "DKSH"]
        item_group: DF.Link | None
        item_name: DF.Data | None
        mapping_state: DF.Link | None
        mat_group4_code: DF.Data | None
        mat_group_code: DF.Data | None
        material_type_code: DF.Data | None
        rejection_reason: DF.SmallText | None
        request_sent_by: DF.Link | None
        request_sent_on: DF.Datetime | None
        stock_uom: DF.Link | None
        supplier_product_code: DF.Data | None
    # end: auto-generated types

    pass


def on_doctype_update() -> None:
    """Enforce unique DKSH external codes even under concurrent activations."""
    frappe.db.add_unique(
        "DKSH Item Mapping",
        ["dksh_item_code"],
        constraint_name="unique_dksh_item_mapping_code",
    )
