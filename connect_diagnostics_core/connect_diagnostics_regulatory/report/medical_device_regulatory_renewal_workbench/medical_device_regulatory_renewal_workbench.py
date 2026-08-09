# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe import _


def execute(filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    del filters
    rows = frappe.db.sql(
        """
        SELECT action.name, action.registration, registration.expiry_date, action.current_stage, action.assigned_to,
            action.fda_application_number, action.submitted_date, action.response_due_date, action.new_expiry_date
        FROM `tabMedical Device Registration Action` AS action
        INNER JOIN `tabMedical Device Product Registration` AS registration ON registration.name = action.registration
        WHERE action.action_type = 'Renewal'
        ORDER BY registration.expiry_date ASC, action.modified DESC
        """,
        as_dict=True,
    )
    return _columns(), rows


def _columns() -> list[dict[str, Any]]:
    return [
        {
            "fieldname": "registration",
            "label": _("Registration"),
            "fieldtype": "Link",
            "options": "Medical Device Product Registration",
            "width": 180,
        },
        {"fieldname": "expiry_date", "label": _("Expiry"), "fieldtype": "Date", "width": 100},
        {"fieldname": "current_stage", "label": _("Stage"), "fieldtype": "Data", "width": 130},
        {
            "fieldname": "assigned_to",
            "label": _("Assigned To"),
            "fieldtype": "Link",
            "options": "User",
            "width": 140,
        },
        {
            "fieldname": "fda_application_number",
            "label": _("FDA Application"),
            "fieldtype": "Data",
            "width": 150,
        },
        {"fieldname": "submitted_date", "label": _("Submitted"), "fieldtype": "Date", "width": 100},
        {"fieldname": "response_due_date", "label": _("Query Due"), "fieldtype": "Date", "width": 100},
    ]
