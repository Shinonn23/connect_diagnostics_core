# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Copy Storage Location records into real child Warehouses.

Storage Location modeled a physical location as a flat master scoped to a
Warehouse via a plain Link field. The app now uses ERPNext's native Warehouse
tree instead -- each location becomes a leaf Warehouse nested under its old
parent Warehouse. This patch must run before remove_storage_location_doctype
drops the source table.

Idempotent: a Warehouse is only created if none already exists with the same
warehouse_name under the same parent_warehouse. No-op if Storage Location no
longer exists (fresh install or already-migrated site). Rows with a missing or
dangling parent Warehouse link, or a parent with no company, are skipped and
logged rather than crashing the migration.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    if not frappe.db.exists("DocType", "Storage Location"):
        return

    locations = frappe.get_all(
        "Storage Location",
        fields=["name", "location_code", "location_name", "warehouse"],
    )
    migrated = 0
    skipped = 0
    for location in locations:
        warehouse_name = location.location_name or location.location_code
        parent_warehouse = location.warehouse
        if not parent_warehouse or not frappe.db.exists("Warehouse", parent_warehouse):
            frappe.log_error(
                title="migrate_storage_locations_to_warehouses",
                message=f"Storage Location {location.name} has no valid parent Warehouse; skipped.",
            )
            skipped += 1
            continue

        company = frappe.db.get_value("Warehouse", parent_warehouse, "company")
        if not company:
            frappe.log_error(
                title="migrate_storage_locations_to_warehouses",
                message=f"Warehouse {parent_warehouse} (parent of {location.name}) has no company; skipped.",
            )
            skipped += 1
            continue

        if frappe.db.exists(
            "Warehouse", {"warehouse_name": warehouse_name, "parent_warehouse": parent_warehouse}
        ):
            continue

        frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": warehouse_name,
                "parent_warehouse": parent_warehouse,
                "company": company,
                "is_group": 0,
            }
        ).insert(ignore_permissions=True)
        migrated += 1

    frappe.db.commit()
    frappe.logger().info(
        f"migrate_storage_locations_to_warehouses: migrated {migrated}, skipped {skipped} of {len(locations)}"
    )
