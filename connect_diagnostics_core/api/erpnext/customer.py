from typing import Any

import frappe
from erpnext.selling.doctype.customer.customer import Customer
from frappe.model.naming import make_autoname


def autoname(doc: Customer, _method: Any):
	if doc.naming_series == "DKSH-CODE":
		if not doc.custom_dksh_customer_code:
			frappe.throw("DKSH Code is required when Naming Series is set to DKSH-CODE")
		if frappe.db.exists("Customer", doc.custom_dksh_customer_code):
			frappe.throw(f"Customer code {doc.custom_dksh_customer_code} already exists in the system")
		doc.name = doc.custom_dksh_customer_code

	elif doc.naming_series == "CD-CODE":
		if not doc.custom_cd_customer_code:
			frappe.throw("CD Code is required when Naming Series is set to CD-CODE")
		if frappe.db.exists("Customer", doc.custom_cd_customer_code):
			frappe.throw(f"Customer code {doc.custom_cd_customer_code} already exists in the system")
		doc.name = doc.custom_cd_customer_code

	else:
		doc.name = make_autoname(doc.naming_series)
