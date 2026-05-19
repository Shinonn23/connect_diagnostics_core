# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class AliasName(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        alias_name: DF.Data
        documents: DF.Link | None
        original_display_name: DF.Data | None
        primary_name: DF.DynamicLink
    # end: auto-generated types
