# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for migrate_item_name_th_to_alternative_name.

The forward patch inserted one ``Item Alternative Name`` row per non-empty
``custom_item_name_th`` value, naming each row ``MD5(CONCAT(parent, name_value))`` with
label "Thai". This deletes exactly those rows by recomputing that deterministic name, so
manually added Thai alternative names (which carry random hash names) are left untouched.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.db.sql(
        """
        DELETE FROM `tabItem Alternative Name`
        WHERE name_label = 'Thai'
          AND name = MD5(CONCAT(parent, name_value))
        """
    )
    deleted = frappe.db.sql("SELECT ROW_COUNT()")[0][0]
    frappe.db.commit()
    frappe.logger(__name__).info(f"rollback_migrate_item_name_th_to_alternative_name: deleted {deleted} rows")
