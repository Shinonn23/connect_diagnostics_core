from typing import Any, Literal, cast

import frappe
from erpnext.selling.doctype.customer.customer import Customer
from frappe.model.naming import make_autoname


def autoname(doc: Customer, _method: Any):
	# Cast naming_series to Literal to avoid type errors
	doc.naming_series: Literal["DKSH-CODE", "CD-CODE", ""] = cast(
		Literal["DKSH-CODE", "CD-CODE", ""], doc.naming_series
	)

	if doc.naming_series == "DKSH-CODE":
		if not doc.custom_dksh_customer_code:  # ty:ignore[unresolved-attribute]
			frappe.throw("DKSH Code is required when Naming Series is set to DKSH-CODE")
		if frappe.db.exists("Customer", doc.custom_dksh_customer_code):  # ty:ignore[unresolved-attribute]
			frappe.throw(
				f"Customer code {doc.custom_dksh_customer_code} already exists in the system"  # ty:ignore[unresolved-attribute]
			)
		doc.name = doc.custom_dksh_customer_code  # ty:ignore[unresolved-attribute]

	elif doc.naming_series == "CD-CODE":
		if not doc.custom_cd_customer_code:  # ty:ignore[unresolved-attribute]
			frappe.throw("CD Code is required when Naming Series is set to CD-CODE")
		if frappe.db.exists("Customer", doc.custom_cd_customer_code):  # ty:ignore[unresolved-attribute]
			frappe.throw(
				f"Customer code {doc.custom_cd_customer_code} already exists in the system"  # ty:ignore[unresolved-attribute]
			)
		doc.name = doc.custom_cd_customer_code  # ty:ignore[unresolved-attribute]

	else:
		doc.name = make_autoname(doc.naming_series)
