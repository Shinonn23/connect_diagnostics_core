# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class PrintLog(Document):
    """Audit record of one printed or downloaded document.

    Rows are written by ``connect_diagnostics_core.api.frappe.print_log`` and are
    never edited afterwards: no role has write or delete permission, and the
    DocType is ``in_create`` so Desk offers no new-document form.
    """

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        channel: DF.Literal["Print", "PDF"]
        copies: DF.Int
        copy_labels: DF.SmallText | None
        customer: DF.Link | None
        language: DF.Data | None
        print_format: DF.Link | None
        reference_doctype: DF.Link
        reference_name: DF.DynamicLink
    # end: auto-generated types
    pass
