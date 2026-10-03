# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Un-register the "Storage Location" Inventory Dimension and drop its columns.

The dimension generated ``storage_location`` / ``to_storage_location`` /
``from_storage_location`` / ``rejected_storage_location`` Custom Fields on
every stock transaction doctype plus Stock Ledger Entry and Stock Closing
Balance (see the former setup/storage_location.py). Deleting the Inventory
Dimension document triggers ERPNext's own on_trash(), which deletes those
Custom Field records; this patch also drops the now-orphaned columns those
fields leave behind, mirroring drop_workflow_state_doctype_columns.py.

Must run after migrate_storage_locations_to_warehouses.py (data already
copied out) and before remove_storage_location_doctype.py. Idempotent /
no-op once the dimension is gone.
"""

from __future__ import annotations

import frappe

DIMENSION_NAME = "Storage Location"
_GENERATED_FIELDNAMES = (
    "storage_location",
    "to_storage_location",
    "from_storage_location",
    "rejected_storage_location",
)


def execute() -> None:
    if not frappe.db.exists("Inventory Dimension", DIMENSION_NAME):
        return

    affected = frappe.get_all(
        "Custom Field",
        filters={"fieldname": ("in", _GENERATED_FIELDNAMES), "options": DIMENSION_NAME},
        fields=["dt", "fieldname"],
    )

    frappe.delete_doc("Inventory Dimension", DIMENSION_NAME, force=True, ignore_permissions=True)

    for row in affected:
        frappe.db.sql_ddl(f"ALTER TABLE `tab{row.dt}` DROP COLUMN IF EXISTS `{row.fieldname}`")

    frappe.db.commit()
    frappe.logger().info(
        f"retire_storage_location_inventory_dimension: dropped {len(affected)} generated column(s)"
    )
