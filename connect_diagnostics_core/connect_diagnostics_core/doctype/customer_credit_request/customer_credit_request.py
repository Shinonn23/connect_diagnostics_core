# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class CustomerCreditRequest(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        approved_by: DF.Link | None
        approved_on: DF.Datetime | None
        company: DF.Link
        credit_applied: DF.Check
        credit_request_state: DF.Link | None
        customer: DF.Link
        naming_series: DF.Literal["CCR-.#####"]
        payment_terms: DF.Link
        reason: DF.SmallText
        requested_credit_limit: DF.Currency
        review_reason: DF.SmallText | None
    # end: auto-generated types

    pass
