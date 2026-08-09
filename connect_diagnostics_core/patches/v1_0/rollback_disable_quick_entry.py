# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for disable_quick_entry — remove the disabling property setters.

disable_quick_entry created (or set to "0") DocType-level ``quick_entry`` Property
Setters to turn Quick Entry off. Deleting the disabling setters returns each DocType to
its shipped default. The pre-patch value of any setter it edited in place is not tracked,
so this restores defaults rather than a prior custom value.
"""

from __future__ import annotations

from typing import cast

import frappe


def execute() -> None:
    names = cast(
        list[str],
        frappe.get_all(
            "Property Setter",
            filters={
                "doctype_or_field": "DocType",
                "property": "quick_entry",
                "value": "0",
            },
            pluck="name",
        ),
    )

    for name in names:
        frappe.delete_doc("Property Setter", name, force=True, ignore_permissions=True)

    frappe.clear_cache()
    frappe.logger(__name__).info(
        "rollback_disable_quick_entry: removed %s quick_entry property setters",
        len(names),
    )
