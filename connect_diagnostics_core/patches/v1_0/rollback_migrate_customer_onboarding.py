# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for migrate_customer_onboarding.

Run this manually before reverting the customer-onboarding source change.  It
restores the previous Customer and Item form configuration and deactivates the
new workflows without deleting Customers, Items, Partner Item Mappings, or
credit-request history.
"""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

_WORKFLOW_NAMES = (
    "Customer Onboarding",
    "Customer Credit Request Approval",
)
_WORKFLOW_ACTION_DOCTYPES = (
    "Customer",
    "Customer Credit Request",
)

_ROLLBACK_FIELD_PROPERTIES: dict[str, dict[str, dict[str, int | str]]] = {
    "Customer": {
        "customer_code": {"hidden": 1, "reqd": 0},
        "customer_channel": {"hidden": 1, "reqd": 0},
        "dksh_sap_customer_code": {"hidden": 1},
        "customer_onboarding_section": {"hidden": 1},
        "customer_onboarding_state": {"hidden": 1},
        "correction_reason": {"hidden": 1},
        "readiness_section": {"hidden": 1},
        "quotation_readiness": {"hidden": 1},
        "delivery_readiness": {"hidden": 1},
        "tax_invoice_readiness": {"hidden": 1},
        "email_readiness": {"hidden": 1},
        "customer_readiness_summary": {"hidden": 1},
        "no_delivery_required": {"hidden": 1},
        "no_delivery_reason": {"hidden": 1},
        "has_dksh_code": {"hidden": 0},
        "customer_code_is_dksh_code": {
            "hidden": 0,
            "depends_on": "eval:doc.has_dksh_code",
            "description": (
                "Tick when the customer has no CD code yet and the DKSH code is used as the "
                "Customer ID. Untick and save to issue a CD code (the DKSH code is kept)."
            ),
        },
        "dksh_customer_code": {
            "hidden": 0,
            "depends_on": "eval:doc.has_dksh_code",
            "description": (
                "When 'Customer Code is DKSH Code' is ticked, enter the DKSH code here — it "
                "becomes the Customer ID."
            ),
        },
    },
    "Item": {
        "item_channel": {"hidden": 1, "reqd": 0},
        "partner_item_mappings_section": {"hidden": 1},
        "partner_item_mappings": {"hidden": 1},
        "has_dksh_code": {"hidden": 0},
        "item_code_is_dksh_code": {
            "hidden": 0,
            "depends_on": "eval:doc.has_dksh_code",
            "description": "Tick when the item has no CD code and Item Code itself is the DKSH code (e.g. OPTI).",
        },
        "dksh_item_code": {
            "hidden": 0,
            "depends_on": "eval:doc.has_dksh_code",
            "read_only_depends_on": "eval:doc.item_code_is_dksh_code",
        },
        "mat_group_code": {"depends_on": "eval:doc.has_dksh_code"},
        "mat_group4_code": {"depends_on": "eval:doc.has_dksh_code"},
        "material_type_code": {"depends_on": "eval:doc.has_dksh_code"},
        "supplier_product_code": {"depends_on": "eval:doc.has_dksh_code"},
    },
}

_LEGACY_CUSTOMER_NAMING_PROPERTIES: tuple[tuple[str, str, str], ...] = (
    ("default", "2S.###", "Text"),
    (
        "description",
        "CD code, auto-selected by customer type: Individual→2S, Company→4A, Hospital/Gov→4H. "
        "Ignored when the DKSH code is used as the Customer ID.",
        "Text",
    ),
    ("hidden", "0", "Check"),
    ("options", "2S.###\n4A.###\n4H.###", "Text"),
)


def execute() -> None:
    _deactivate_workflows()
    _remove_open_workflow_actions()
    _restore_legacy_custom_fields()
    _restore_legacy_customer_naming()
    frappe.clear_cache(doctype="Customer")
    frappe.clear_cache(doctype="Item")
    frappe.clear_cache(doctype="Customer Credit Request")
    frappe.db.commit()


def _deactivate_workflows() -> None:
    frappe.db.set_value(
        "Workflow",
        {"name": ["in", _WORKFLOW_NAMES]},
        "is_active",
        0,
        update_modified=False,
    )


def _remove_open_workflow_actions() -> None:
    action_names = cast(
        list[str],
        frappe.get_all(
            "Workflow Action",
            filters={
                "reference_doctype": ["in", _WORKFLOW_ACTION_DOCTYPES],
                "status": "Open",
            },
            pluck="name",
            order_by="name asc",
        ),
    )
    for action_name in action_names:
        frappe.delete_doc("Workflow Action", action_name, force=True, ignore_permissions=True)


def _restore_legacy_custom_fields() -> None:
    doctypes = tuple(sorted(_ROLLBACK_FIELD_PROPERTIES))
    fieldnames = sorted({fieldname for fields in _ROLLBACK_FIELD_PROPERTIES.values() for fieldname in fields})
    rows = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Custom Field",
            filters={"dt": ["in", doctypes], "fieldname": ["in", fieldnames]},
            fields=["name", "dt", "fieldname"],
            order_by="name asc",
        ),
    )
    updates: dict[str, dict[str, int | str]] = {}
    for row in rows:
        doctype = cast(str, row["dt"])
        fieldname = cast(str, row["fieldname"])
        properties = _ROLLBACK_FIELD_PROPERTIES.get(doctype, {}).get(fieldname)
        if properties:
            updates[cast(str, row["name"])] = properties
    frappe.db.bulk_update("Custom Field", updates, update_modified=False)


def _restore_legacy_customer_naming() -> None:
    for property_name, value, property_type in _LEGACY_CUSTOMER_NAMING_PROPERTIES:
        make_property_setter(
            "Customer",
            "naming_series",
            property_name,
            value,
            property_type,
            validate_fields_for_doctype=False,
        )
