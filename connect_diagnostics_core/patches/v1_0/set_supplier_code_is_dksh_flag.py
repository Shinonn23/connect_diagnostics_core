"""Tick ``supplier_code_is_dksh_code`` for DKSH-only Suppliers.

A Supplier whose ID (name) already equals its DKSH code is DKSH-only. Tick the flag
and clear the duplicate in dksh_supplier_code so it doesn't trip the unique
constraint (matches party_dksh.validate / set_customer_code_is_dksh_flag).
"""

import frappe


def execute():
    if not frappe.db.has_column("Supplier", "supplier_code_is_dksh_code"):
        return

    frappe.db.sql(
        """
        UPDATE `tabSupplier`
        SET supplier_code_is_dksh_code = 1
        WHERE has_dksh_code = 1
          AND dksh_supplier_code = name
        """
    )
    frappe.db.sql(
        """
        UPDATE `tabSupplier`
        SET dksh_supplier_code = NULL
        WHERE supplier_code_is_dksh_code = 1
        """
    )
    frappe.db.commit()
