"""Rollback for remove_customer_name_th_field.

Recreates the Custom Field and restores values from the first Customer Alternative
Name row of each customer. Best-effort: only the migrated alternative names are
available as a source.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
    if not frappe.db.exists("Custom Field", "Customer-customer_name_th"):
        create_custom_field(
            "Customer",
            {
                "fieldname": "customer_name_th",
                "label": "Customer Name TH",
                "fieldtype": "Data",
                "insert_after": "customer_name",
                "no_copy": 1,
            },
        )

    frappe.db.sql(
        """
        UPDATE `tabCustomer` c
        SET customer_name_th = (
            SELECT can.name_value
            FROM `tabCustomer Alternative Name` can
            WHERE can.parent = c.name
              AND can.parentfield = 'alternative_names'
            ORDER BY can.idx
            LIMIT 1
        )
        WHERE (c.customer_name_th IS NULL OR c.customer_name_th = '')
        """
    )
    frappe.db.commit()
