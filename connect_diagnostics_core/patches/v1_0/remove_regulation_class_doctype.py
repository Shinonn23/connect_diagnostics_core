# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Delete the "Regulation Class" DocType and its table.

Superseded by the Regulatory module's own item classification fields
(is_medical_device / medical_device_category / regulatory_registration_requirement);
nothing consumed it in code. Must run after remove_item_regulation_class_field so no
Link field still points at it.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    if frappe.db.exists("DocType", "Regulation Class"):
        frappe.delete_doc("DocType", "Regulation Class", force=True, ignore_permissions=True)
        frappe.db.commit()
