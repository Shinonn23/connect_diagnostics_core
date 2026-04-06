# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class SubDepartmentAssignment(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		sub_department: DF.Link | None
	# end: auto-generated types
	pass
