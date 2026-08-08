# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Reverse ``retire_customer_onboarding_workflow``.

Recreates the onboarding fields, the duplicate verifier role, and the workflow
states, then puts every enabled Customer back into the active state so the
restored workflow has a consistent starting point.

The readiness values are **not** restored: they were always derived from Address
and Contact data, so a later save recalculates them. Which Customers were mid-flight
when the workflow was retired is likewise gone; they come back active rather than
back in the queue, because guessing a review step would be worse than not
reviewing at all.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.patches.v1_0.retire_customer_onboarding_workflow import (
    ACTIVE_STATE,
    ONBOARDING_STATE_FIELD,
    RETIRED_ROLE,
    RETIRED_WORKFLOW_STATES,
)

RESTORED_FIELDS: list[dict[str, Any]] = [
    {
        "fieldname": "customer_onboarding_section",
        "label": "Customer Onboarding",
        "fieldtype": "Tab Break",
        "insert_after": "portal_users",
    },
    {
        "fieldname": ONBOARDING_STATE_FIELD,
        "label": "Customer Onboarding State",
        "fieldtype": "Link",
        "options": "Workflow State",
        "insert_after": "customer_onboarding_section",
        "read_only": 1,
        "no_copy": 1,
    },
    {
        "fieldname": "correction_reason",
        "label": "Correction Reason",
        "fieldtype": "Small Text",
        "insert_after": ONBOARDING_STATE_FIELD,
        "no_copy": 1,
    },
    {
        "fieldname": "readiness_section",
        "label": "Document Readiness",
        "fieldtype": "Section Break",
        "insert_after": "correction_reason",
    },
    *(
        {
            "fieldname": fieldname,
            "label": label,
            "fieldtype": "Select",
            "options": "Ready\nMissing information\nNot applicable",
            "insert_after": insert_after,
            "read_only": 1,
            "no_copy": 1,
        }
        for fieldname, label, insert_after in (
            ("quotation_readiness", "Quotation Readiness", "readiness_section"),
            ("delivery_readiness", "Delivery Readiness", "quotation_readiness"),
            ("tax_invoice_readiness", "Tax Invoice Readiness", "delivery_readiness"),
            ("email_readiness", "Email Readiness", "tax_invoice_readiness"),
        )
    ),
    {
        "fieldname": "customer_readiness_summary",
        "label": "Readiness Summary",
        "fieldtype": "Small Text",
        "insert_after": "email_readiness",
        "read_only": 1,
        "no_copy": 1,
    },
    {
        "fieldname": "no_delivery_required",
        "label": "No Delivery Required",
        "fieldtype": "Check",
        "insert_after": "customer_readiness_summary",
        "default": "0",
    },
    {
        "fieldname": "no_delivery_reason",
        "label": "No Delivery Reason",
        "fieldtype": "Small Text",
        "insert_after": "no_delivery_required",
        "depends_on": "eval:doc.no_delivery_required",
    },
]

STATE_STYLES = {
    "Customer Request": "",
    "Customer Pending Duplicate Verification": "Warning",
    "Customer Pending Accounting & Credit Review": "Warning",
    ACTIVE_STATE: "Success",
}


def execute() -> None:
    """Restore the fields, states, and role the retirement removed."""
    create_custom_fields({"Customer": RESTORED_FIELDS}, ignore_validate=True)

    for state in RETIRED_WORKFLOW_STATES:
        if not frappe.db.exists("Workflow State", state):
            frappe.get_doc(
                {
                    "doctype": "Workflow State",
                    "workflow_state_name": state,
                    "style": STATE_STYLES.get(state, ""),
                }
            ).insert(ignore_permissions=True)

    if not frappe.db.exists("Role", RETIRED_ROLE):
        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": RETIRED_ROLE,
                "disabled": 0,
                "desk_access": 1,
                "is_custom": 1,
            }
        ).insert(ignore_permissions=True)

    for name in frappe.get_all("Customer", filters={"disabled": 0}, pluck="name"):
        frappe.db.set_value("Customer", name, ONBOARDING_STATE_FIELD, ACTIVE_STATE, update_modified=False)

    frappe.clear_cache(doctype="Customer")
    frappe.db.commit()
