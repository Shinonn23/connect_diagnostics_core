"""Rollback for set_customer_code_is_dksh_flag.

Restores dksh_customer_code from the record name for DKSH-only Customers, then
unticks the flag. Idempotent.
"""

import frappe


def execute():
    if not frappe.db.has_column("Customer", "customer_code_is_dksh_code"):
        return

    frappe.db.sql(
        """
        UPDATE `tabCustomer`
        SET dksh_customer_code = name
        WHERE customer_code_is_dksh_code = 1
          AND (dksh_customer_code IS NULL OR dksh_customer_code = '')
        """
    )
    frappe.db.sql("UPDATE `tabCustomer` SET customer_code_is_dksh_code = 0")
    frappe.db.commit()
