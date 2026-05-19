from typing import Any, cast

import frappe
from erpnext.selling.doctype.customer.customer import Customer


class CustomCustomer(Customer):
    custom_cd_customer_code: str | None
    custom_dksh_customer_code: str | None

    def autoname(self):
        if self.custom_dksh_customer_code:
            self.name = self.custom_dksh_customer_code.strip()
            self.flags.name_set = True
        elif self.custom_cd_customer_code:
            self.name = self.custom_cd_customer_code.strip()
            self.flags.name_set = True


def validate(doc: CustomCustomer, _method: Any):
    if not doc.name:
        raise frappe.ValidationError("Customer name is required to update DKSH Customer Code")

    if not doc.is_new() and doc.custom_dksh_customer_code and doc.name != doc.custom_dksh_customer_code:
        frappe.rename_doc(
            "Customer",
            doc.name,
            doc.custom_dksh_customer_code,
            force=True,
        )

        doc.name = doc.custom_dksh_customer_code
