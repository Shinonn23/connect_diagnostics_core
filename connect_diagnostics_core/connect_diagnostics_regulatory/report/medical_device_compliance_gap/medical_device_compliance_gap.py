# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from connect_diagnostics_core.api.erpnext.regulatory import get_effective_mapping


def execute(filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    del filters
    data: list[dict[str, Any]] = []
    for item in frappe.get_all(
        "Item",
        filters={"is_medical_device": 1, "regulatory_registration_requirement": "Required"},
        fields=["name", "item_name"],
    ):
        if not get_effective_mapping(item.name):
            data.append(
                {
                    "subject_type": "Item",
                    "subject": item.name,
                    "item_name": item.item_name,
                    "gap": _("No effective active registration mapping"),
                }
            )
    for registration in frappe.get_all(
        "Medical Device Product Registration", filters={"official_status": "Active"}, pluck="name"
    ):
        if not frappe.db.exists(
            "Medical Device Regulatory Document",
            {"registration": registration, "document_type": "Certificate", "verification_status": "Verified"},
        ):
            data.append(
                {
                    "subject_type": "Registration",
                    "subject": registration,
                    "item_name": "",
                    "gap": _("Missing verified Certificate"),
                }
            )
    return _columns(), data


def _columns() -> list[dict[str, Any]]:
    return [
        {"fieldname": "subject_type", "label": _("Subject Type"), "fieldtype": "Data", "width": 110},
        {
            "fieldname": "subject",
            "label": _("Subject"),
            "fieldtype": "Dynamic Link",
            "options": "subject_type",
            "width": 180,
        },
        {"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
        {"fieldname": "gap", "label": _("Compliance Gap"), "fieldtype": "Data", "width": 300},
    ]
