# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from frappe.model.document import Document
from frappe.permissions import setup_custom_perms

SUPPLIER = "Supplier"
BANK_ACCOUNT = "Bank Account"
BANK_CHANGE_REQUEST = "Supplier Bank Change Request"
MATERIAL_REQUEST = "Material Request"
COMPANY = "Company"
ASSET_MOVEMENT = "Asset Movement"
STOCK_ENTRY = "Stock Entry"
PURCHASE_ORDER = "Purchase Order"
PURCHASE_RECEIPT = "Purchase Receipt"
PURCHASE_INVOICE = "Purchase Invoice"
PAYMENT_ENTRY = "Payment Entry"

PURCHASE_REQUESTER_ROLE = "Purchase Requester"
C_LEVEL_APPROVER_ROLE = "C-Level Approver"
QUALITY_MANAGER_ROLE = "Quality Manager"

CACHE_CLEAR_DOCTYPES = (
    SUPPLIER,
    BANK_CHANGE_REQUEST,
    MATERIAL_REQUEST,
    COMPANY,
    ASSET_MOVEMENT,
    STOCK_ENTRY,
    PURCHASE_ORDER,
    PURCHASE_RECEIPT,
    PURCHASE_INVOICE,
    PAYMENT_ENTRY,
)

CUSTOM_FIELDS = {
    SUPPLIER: [
        {
            "fieldname": "supplier_verification_notes",
            "label": "Supplier Verification Notes",
            "fieldtype": "Small Text",
            "insert_after": "disabled",
            "no_copy": 1,
        },
    ],
    BANK_ACCOUNT: [
        {
            "fieldname": "supplier_bank_verification_status",
            "label": "Supplier Bank Verification Status",
            "fieldtype": "Select",
            "options": "Unverified\nVerified",
            "default": "Unverified",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "disabled",
            "in_list_view": 1,
        },
        {
            "fieldname": "supplier_bank_change_request",
            "label": "Supplier Bank Change Request",
            "fieldtype": "Link",
            "options": BANK_CHANGE_REQUEST,
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "supplier_bank_verification_status",
        },
    ],
    PURCHASE_ORDER: [
        {
            "fieldname": "p2p_exception_reason",
            "label": "P2P Exception Reason",
            "fieldtype": "Small Text",
            "insert_after": "status",
            "no_copy": 1,
        },
    ],
    PURCHASE_INVOICE: [
        {
            "fieldname": "p2p_exception_reason",
            "label": "P2P Exception Reason",
            "fieldtype": "Small Text",
            "insert_after": "status",
            "no_copy": 1,
        },
    ],
}

PROPERTY_SETTERS = {
    "Purchase Order Item": [
        ("item_name", "in_list_view", "1", "Check"),
    ],
}

_ROLES = (PURCHASE_REQUESTER_ROLE, C_LEVEL_APPROVER_ROLE)


def ensure_configuration() -> None:
    ensure_roles()
    assign_role_holders()
    activate_standard_permissions()
    for doctype in CACHE_CLEAR_DOCTYPES:
        frappe.clear_cache(doctype=doctype)


def ensure_roles() -> None:
    for role_name in _ROLES:
        if frappe.db.exists("Role", role_name):
            role = cast(Document, frappe.get_doc("Role", role_name))
            if role.get("disabled") or not role.get("desk_access") or not role.get("is_custom"):
                role.update({"disabled": 0, "desk_access": 1, "is_custom": 1})
                role.save(ignore_permissions=True)
            continue
        frappe.get_doc({"doctype": "Role", "role_name": role_name, "desk_access": 1, "is_custom": 1}).insert(
            ignore_permissions=True
        )


def assign_role_holders() -> None:
    for user in frappe.get_all(
        "Employee", filters={"status": "Active", "user_id": ["is", "set"]}, pluck="user_id"
    ):
        _assign_role(cast(str, user), PURCHASE_REQUESTER_ROLE)


def _assign_role(user_name: str, role_name: str) -> None:
    if not frappe.db.exists("User", user_name):
        return
    user = cast(Document, frappe.get_doc("User", user_name))
    if not user.get("enabled") or role_name in {cast(str, row.role) for row in user.get("roles", [])}:
        return
    user.append("roles", {"role": role_name})
    user.save(ignore_permissions=True)


def activate_standard_permissions() -> None:
    """Keep native Material Request access available to app-assigned requesters."""
    if setup_custom_perms(MATERIAL_REQUEST):
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": MATERIAL_REQUEST,
                "role": PURCHASE_REQUESTER_ROLE,
                "permlevel": 0,
                "read": 1,
                "write": 1,
                "create": 1,
                "report": 1,
                "print": 1,
                "email": 1,
            }
        ).insert(ignore_permissions=True)
    _ensure_material_request_permission(
        PURCHASE_REQUESTER_ROLE,
        0,
        read=1,
        write=1,
        create=1,
        report=1,
        print=1,
        email=1,
    )
    # Preserve native operational permissions before adding app-specific roles.
    # Frappe switches a DocType to its Custom DocPerm table once the first
    # custom row exists; copying first keeps the native operational roles intact.
    for doctype in (ASSET_MOVEMENT, STOCK_ENTRY, PAYMENT_ENTRY):
        setup_custom_perms(doctype)
    _ensure_permission(PAYMENT_ENTRY, C_LEVEL_APPROVER_ROLE, read=1, write=1)
    for doctype in (ASSET_MOVEMENT, STOCK_ENTRY):
        _ensure_permission(doctype, "Stock User", read=1, write=1, create=1, submit=1, report=1, print=1)
        _ensure_permission(
            doctype,
            "Stock Manager",
            read=1,
            write=1,
            create=1,
            submit=1,
            cancel=1,
            report=1,
            print=1,
        )
        _ensure_permission(doctype, QUALITY_MANAGER_ROLE, read=1, write=1, create=1, report=1, print=1)
        _ensure_permission(doctype, C_LEVEL_APPROVER_ROLE, read=1, write=1)


def _ensure_material_request_permission(role: str, permlevel: int, **rights: int) -> None:
    filters = {
        "parent": MATERIAL_REQUEST,
        "role": role,
        "permlevel": permlevel,
        "if_owner": 0,
    }
    name = frappe.db.get_value("Custom DocPerm", filters, "name")
    if name:
        permission = cast(Document, frappe.get_doc("Custom DocPerm", name))
        changed = False
        for right, value in rights.items():
            if permission.get(right) != value:
                permission.set(right, value)
                changed = True
        if changed:
            permission.save(ignore_permissions=True)
        return

    frappe.get_doc(
        {
            "doctype": "Custom DocPerm",
            "parent": MATERIAL_REQUEST,
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role": role,
            "permlevel": permlevel,
            **rights,
        }
    ).insert(ignore_permissions=True)


def _ensure_permission(doctype: str, role: str, **rights: int) -> None:
    """Maintain app roles used by the surviving Asset Movement and Stock Entry workflows."""
    filters = {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
    name = frappe.db.get_value("Custom DocPerm", filters, "name")
    if name:
        permission = cast(Document, frappe.get_doc("Custom DocPerm", name))
        changed = False
        for right, value in rights.items():
            if permission.get(right) != value:
                permission.set(right, value)
                changed = True
        if changed:
            permission.save(ignore_permissions=True)
        return

    frappe.get_doc(
        {
            "doctype": "Custom DocPerm",
            "parent": doctype,
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role": role,
            "permlevel": 0,
            **rights,
        }
    ).insert(ignore_permissions=True)
