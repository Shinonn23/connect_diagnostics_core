# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""DKSH Customer — a DKSH customer code as its own master, optionally linked to Customer.

Some customers carry a 9-digit DKSH code that differs from their CD Customer Code.
They are kept here as a standalone reference master with an **optional** ``customer``
link: blank means a DKSH stand-alone customer with no CD Customer. The record name
is the DKSH Customer Code, so uniqueness of the code is enforced by naming; a second
record mapping the same CD Customer is rejected in ``validate``.

This is reference data only. It has no workflow, no roles of its own, and does not
control Customer lifecycle or transaction eligibility. When CD decides to sell to a
DKSH customer directly, the Convert to CD Customer action prefills a new Customer
form; saving it links back here (see ``api.erpnext.customer.link_source_dksh_customer``).
"""

from __future__ import annotations

from frappe.model.document import Document

from connect_diagnostics_core.connect_diagnostics_dksh import reference

CODE_FIELDS = ("dksh_customer_code",)


class DKSHCustomer(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        address_line1: DF.Data | None
        address_line2: DF.Data | None
        branch_code: DF.Data | None
        city: DF.Data | None
        country: DF.Link | None
        county: DF.Data | None
        customer: DF.Link | None
        customer_name: DF.Data | None
        dksh_customer_code: DF.Data
        email_id: DF.Data | None
        phone: DF.Data | None
        pincode: DF.Data | None
        state: DF.Data | None
        tax_id: DF.Data | None
    # end: auto-generated types

    def validate(self) -> None:
        reference.validate_reference(
            self,
            code_fields=CODE_FIELDS,
            link_field="customer",
            master_doctype="Customer",
        )
