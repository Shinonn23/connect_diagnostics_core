# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.model.document import Document

from connect_diagnostics_core.api.erpnext.company import validate_quotation_authorized_signatory_employee


class QuotationAuthorizedSignatory(Document):
    """One Employee in a Company's Quotation signing allow-list."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        employee: DF.Link
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
    # end: auto-generated types

    def validate(self) -> None:
        if self.employee and self.parent:
            validate_quotation_authorized_signatory_employee(self.employee, self.parent)
