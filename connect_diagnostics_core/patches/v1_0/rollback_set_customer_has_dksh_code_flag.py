"""Rollback for set_customer_has_dksh_code_flag — untick the flag. Idempotent."""

import frappe


def execute():
    if not frappe.db.has_column("Customer", "has_dksh_code"):
        return

    frappe.db.sql("UPDATE `tabCustomer` SET has_dksh_code = 0")
    frappe.db.commit()
