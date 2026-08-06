# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class SupplierBankChangeRequest(Document):
<<<<<<< HEAD
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        approved_by: DF.Link | None
        approved_on: DF.Datetime | None
        bank_account: DF.Link
        bank_change_request_state: DF.Link | None
        naming_series: DF.Literal["SBCR-.#####"]
        reason: DF.SmallText
        supplier: DF.Link
        supporting_document: DF.Attach
        verification_notes: DF.SmallText | None
        verified_by: DF.Link | None
        verified_on: DF.Datetime | None
    # end: auto-generated types

    pass
=======
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amended_from: DF.Link | None
		approved_by: DF.Link | None
		approved_on: DF.Datetime | None
		bank_account: DF.Link
		bank_change_request_state: DF.Link | None
		naming_series: DF.Literal["SBCR-.#####"]
		reason: DF.SmallText
		supplier: DF.Link
		supporting_document: DF.Attach
		verification_notes: DF.SmallText | None
		verified_by: DF.Link | None
		verified_on: DF.Datetime | None
	# end: auto-generated types

	pass
>>>>>>> 4543b3b (feat: Add workflow action master and state fixtures for procure-to-pay workflow)
