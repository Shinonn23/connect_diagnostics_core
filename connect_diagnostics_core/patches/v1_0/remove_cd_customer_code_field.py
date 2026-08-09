"""Remove the now-unused ``cd_customer_code`` field from Customer.

The CD code is the auto naming-series number (= the Customer ID), so the manual
field is gone. Existing IDs are left untouched. Deletes the Custom Field doc and
drops the orphan column. Idempotent / no-op once dropped.
"""

import frappe


def execute():
    if frappe.db.exists("Custom Field", "Customer-cd_customer_code"):
        frappe.delete_doc("Custom Field", "Customer-cd_customer_code", force=True)

    if frappe.db.has_column("Customer", "cd_customer_code"):
        frappe.db.sql_ddl("ALTER TABLE `tabCustomer` DROP COLUMN `cd_customer_code`")

    frappe.db.commit()
