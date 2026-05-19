# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class AliasSupportedDocType(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        alias_field: DF.Literal[None]
        descriptions: DF.SmallText | None
        is_enabled: DF.Check
        reference_doctype: DF.Link | None
    # end: auto-generated types
