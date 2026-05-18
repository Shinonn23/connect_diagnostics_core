from typing import Any, cast

import frappe
from erpnext.selling.doctype.customer.customer import Customer


class CustomCustomer(Customer):
	custom_cd_customer_code: str | None
	custom_dksh_customer_code: str | None


def before_naming(doc: Customer, _method: Any):
	doc = cast(CustomCustomer, doc)

	if doc.custom_dksh_customer_code:
		doc.name = doc.custom_dksh_customer_code.strip()
		doc.flags.name_set = True

	elif doc.custom_cd_customer_code:
		doc.name = doc.custom_cd_customer_code.strip()
		doc.flags.name_set = True


def validate(doc: Customer, _method: Any):
	doc = cast(CustomCustomer, doc)

	if not doc.is_new() and doc.custom_dksh_customer_code and doc.name != doc.custom_dksh_customer_code:
		frappe.rename_doc(
			"Customer",
			doc.name,
			doc.custom_dksh_customer_code,
			force=True,
		)

		doc.name = doc.custom_dksh_customer_code
