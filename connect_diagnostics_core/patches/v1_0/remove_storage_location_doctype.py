# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Delete the "Storage Location" DocType and its table.

Its records were already copied into Warehouse by
migrate_storage_locations_to_warehouses.py, and its Inventory Dimension
custom fields already removed by
retire_storage_location_inventory_dimension.py. Must run after both.
"""

import frappe


def execute():
    if frappe.db.exists("DocType", "Storage Location"):
        frappe.delete_doc("DocType", "Storage Location", force=True, ignore_permissions=True)
        frappe.db.commit()
