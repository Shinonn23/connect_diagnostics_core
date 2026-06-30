"""Tick ``customer_code_is_dksh_code`` for DKSH-only Customers.

A Customer whose ID (name) already equals its DKSH code is DKSH-only: the DKSH code
is the primary ID and there is no CD code yet. Tick the flag and clear the duplicate
in dksh_customer_code so it doesn't trip the field's unique constraint (matches
party_dksh.validate / set_item_code_is_dksh_flag).
"""

import frappe


def execute():
    if not frappe.db.has_column("Customer", "customer_code_is_dksh_code"):
        return

    frappe.db.sql(
        """
        UPDATE `tabCustomer`
        SET customer_code_is_dksh_code = 1
        WHERE has_dksh_code = 1
          AND dksh_customer_code = name
        """
    )
    frappe.db.sql(
        """
        UPDATE `tabCustomer`
        SET dksh_customer_code = NULL
        WHERE customer_code_is_dksh_code = 1
        """
    )
    frappe.db.commit()
