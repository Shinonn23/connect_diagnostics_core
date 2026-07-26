# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PartnerItemMapping(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        active: DF.Check
        external_item_code: DF.Data
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        partner_company: DF.Link
        uom: DF.Link
    # end: auto-generated types

    pass


def on_doctype_update() -> None:
    """Enforce the partner-code uniqueness invariant at the database layer."""
    frappe.db.add_unique(
        "Partner Item Mapping",
        ["parenttype", "partner_company", "external_item_code"],
        constraint_name="unique_partner_item_mapping_code",
    )
