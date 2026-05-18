from typing import Any, cast

import frappe
from erpnext.buying.doctype.supplier.supplier import Supplier


class CustomSupplier(Supplier):
	custom_cd_supplier_code: str | None
	custom_dksh_supplier_code: str | None


def before_naming(doc: Supplier, _method: Any):
	doc = cast(CustomSupplier, doc)

	if doc.custom_dksh_supplier_code:
		doc.name = doc.custom_dksh_supplier_code.strip()
		doc.flags.name_set = True

	elif doc.custom_cd_supplier_code:
		doc.name = doc.custom_cd_supplier_code.strip()
		doc.flags.name_set = True


def validate(doc: Supplier, _method: Any):
	doc = cast(CustomSupplier, doc)

	if not doc.is_new() and doc.custom_dksh_supplier_code and doc.name != doc.custom_dksh_supplier_code:
		frappe.rename_doc(
			"Supplier",
			doc.name,
			doc.custom_dksh_supplier_code,
			force=True,
		)

		doc.name = doc.custom_dksh_supplier_code
