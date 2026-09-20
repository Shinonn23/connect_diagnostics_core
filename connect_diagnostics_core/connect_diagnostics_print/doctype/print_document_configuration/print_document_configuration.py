# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class PrintDocumentConfiguration(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        document_key: DF.Data
        document_label: DF.Data | None
        enabled: DF.Check
        language: DF.Literal["Thai", "English", "Thai / English"]
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        show_batch_serial: DF.Check
        show_date: DF.Check
    # end: auto-generated types
    pass
