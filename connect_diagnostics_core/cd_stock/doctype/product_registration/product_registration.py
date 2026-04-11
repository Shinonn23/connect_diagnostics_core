# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ProductRegistration(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		document: DF.Attach | None
		expiry_date: DF.Date | None
		issue_date: DF.Date | None
		registration_number: DF.Data
		registration_type: DF.Link | None
		status: DF.Literal["Active", "Expired", "Pending"]
	# end: auto-generated types
	pass
