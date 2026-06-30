"""Rollback for set_supplier_code_is_dksh_flag.

Restores dksh_supplier_code from the record name for DKSH-only Suppliers, then
unticks the flag. Idempotent.
"""

import frappe


def execute():
    if not frappe.db.has_column("Supplier", "supplier_code_is_dksh_code"):
        return

    frappe.db.sql(
        """
        UPDATE `tabSupplier`
        SET dksh_supplier_code = name
        WHERE supplier_code_is_dksh_code = 1
          AND (dksh_supplier_code IS NULL OR dksh_supplier_code = '')
        """
    )
    frappe.db.sql("UPDATE `tabSupplier` SET supplier_code_is_dksh_code = 0")
    frappe.db.commit()
