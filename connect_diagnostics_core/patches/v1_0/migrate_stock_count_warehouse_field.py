# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Copy Stock Count's old single ``warehouse`` Link into Stock Count Warehouse rows,
then drop both retired scalar columns.

Stock Count's header ``warehouse`` field became the multi-select ``warehouses``
Table MultiSelect (options: Stock Count Warehouse), and ``storage_location``
was removed outright (no replacement -- warehouse is now the finest location
grain). The JSON field removal leaves both columns orphaned rather than
dropping them, so ``warehouse`` is still readable here via raw SQL (the
DocType meta no longer knows about it) before both are dropped.

Idempotent: a Stock Count is only backfilled if it has no Stock Count
Warehouse child rows yet; both column drops use ``DROP COLUMN IF EXISTS``.
No-op once ``warehouse`` itself is already dropped (fresh install, or a
second run after cleanup).
"""

from __future__ import annotations

import frappe


def execute() -> None:
    if not frappe.db.has_column("Stock Count", "warehouse"):
        return

    rows = frappe.db.sql(
        """
        select name, warehouse from `tabStock Count`
        where warehouse is not null and warehouse != ''
        """,
        as_dict=True,
    )
    migrated = 0
    for row in rows:
        if frappe.db.exists("Stock Count Warehouse", {"parent": row.name, "parenttype": "Stock Count"}):
            continue
        child = frappe.get_doc(
            {
                "doctype": "Stock Count Warehouse",
                "name": frappe.generate_hash(length=10),
                "parent": row.name,
                "parenttype": "Stock Count",
                "parentfield": "warehouses",
                "idx": 1,
                "warehouse": row.warehouse,
            }
        )
        child.db_insert()
        migrated += 1

    frappe.db.sql_ddl("ALTER TABLE `tabStock Count` DROP COLUMN IF EXISTS `warehouse`")
    frappe.db.sql_ddl("ALTER TABLE `tabStock Count` DROP COLUMN IF EXISTS `storage_location`")
    frappe.db.commit()
    frappe.logger().info(
        f"migrate_stock_count_warehouse_field: migrated {migrated} of {len(rows)} Stock Count(s)"
    )
