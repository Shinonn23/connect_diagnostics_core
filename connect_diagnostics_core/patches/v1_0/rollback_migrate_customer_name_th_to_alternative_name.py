"""Rollback for migrate_customer_name_th_to_alternative_name.

Deletes only the rows that the forward patch inserted — identified by their
deterministic MD5 name (MD5(parent + name_value)). Idempotent.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Customer Alternative Name"):
        return

    frappe.db.sql(
        """
        DELETE FROM `tabCustomer Alternative Name`
        WHERE parenttype = 'Customer'
          AND parentfield = 'alternative_names'
          AND name = MD5(CONCAT(parent, name_value))
        """
    )
    frappe.db.commit()
