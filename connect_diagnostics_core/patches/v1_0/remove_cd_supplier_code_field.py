"""Remove the now-unused ``cd_supplier_code`` field from Supplier.

The CD code is the auto naming-series number (= the Supplier ID), so the manual
field is gone. Existing IDs are left untouched. Deletes the Custom Field doc and
drops the orphan column. Idempotent / no-op once dropped.
"""

import frappe


def execute():
    if frappe.db.exists("Custom Field", "Supplier-cd_supplier_code"):
        frappe.delete_doc("Custom Field", "Supplier-cd_supplier_code", force=True)

    if frappe.db.has_column("Supplier", "cd_supplier_code"):
        frappe.db.sql_ddl("ALTER TABLE `tabSupplier` DROP COLUMN `cd_supplier_code`")

    frappe.db.commit()
