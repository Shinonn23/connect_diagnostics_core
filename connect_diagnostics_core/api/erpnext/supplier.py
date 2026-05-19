from typing import Any, cast

import frappe
from erpnext.buying.doctype.supplier.supplier import Supplier


class CustomSupplier(Supplier):
    custom_cd_supplier_code: str | None
    custom_dksh_supplier_code: str | None

    def autoname(self):
        if self.custom_dksh_supplier_code:
            self.name = self.custom_dksh_supplier_code.strip()
            self.flags.name_set = True

        elif self.custom_cd_supplier_code:
            self.name = self.custom_cd_supplier_code.strip()
            self.flags.name_set = True


def validate(doc: CustomSupplier, _method: Any):
    if not doc.name:
        raise frappe.ValidationError("Supplier name is required to update DKSH Supplier Code")

    if not doc.is_new() and doc.custom_dksh_supplier_code and doc.name != doc.custom_dksh_supplier_code:
        frappe.rename_doc(
            "Supplier",
            doc.name,
            doc.custom_dksh_supplier_code,
            force=True,
        )

        doc.name = doc.custom_dksh_supplier_code
