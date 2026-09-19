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
MATERIAL_REQUEST_ITEM = "Material Request Item"
COMPANY = "Company"
ASSET_MOVEMENT = "Asset Movement"
ASSET_CAPITALIZATION = "Asset Capitalization"
QUALITY_INSPECTION = "Quality Inspection"
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
    MATERIAL_REQUEST_ITEM,
    COMPANY,
    ASSET_MOVEMENT,
    ASSET_CAPITALIZATION,
    QUALITY_INSPECTION,
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
    MATERIAL_REQUEST: [
        {
            "fieldname": "purchase_reason",
            "label": "Request Reason",
            "fieldtype": "Small Text",
            "reqd": 1,
            "insert_after": "status",
        },
        {
            "fieldname": "supporting_document_complete",
            "label": "Supporting Document Complete",
            "fieldtype": "Check",
            "default": "0",
            "insert_after": "purchase_reason",
        },
        {
            "fieldname": "request_usage",
            "label": "Request Usage",
            "fieldtype": "Select",
            "options": "\nEmployee Borrow\nCustomer Demo\nCustomer Loan\nInternal Permanent Use",
            "description": (
                "Customer Demo uses stock at 10,000 THB or less per stock unit, excluding VAT; "
                "higher-cost units must be capitalized as Assets."
            ),
            "insert_after": "supporting_document_complete",
            "in_standard_filter": 1,
        },
        {
            "fieldname": "destination_type",
            "label": "Destination Type",
            "fieldtype": "Select",
            "options": "\nEmployee\nCustomer\nCompany Site",
            "insert_after": "request_usage",
        },
        {
            "fieldname": "responsible_employee",
            "label": "Responsible Employee",
            "fieldtype": "Link",
            "options": "Employee",
            "insert_after": "destination_type",
        },
        {
            "fieldname": "destination_customer",
            "label": "Destination Customer",
            "fieldtype": "Link",
            "options": "Customer",
            "insert_after": "responsible_employee",
        },
        {
            "fieldname": "destination_address",
            "label": "Destination Address",
            "fieldtype": "Link",
            "options": "Address",
            "insert_after": "destination_customer",
        },
        {
            "fieldname": "asset_location",
            "label": "Asset Location",
            "fieldtype": "Link",
            "options": "Location",
            "insert_after": "destination_address",
        },
        {
            "fieldname": "expected_return_date",
            "label": "Expected Return Date",
            "fieldtype": "Date",
            "insert_after": "asset_location",
        },
    ],
    MATERIAL_REQUEST_ITEM: [
        {
            "fieldname": "fulfillment_route",
            "label": "Fulfillment Route",
            "fieldtype": "Select",
            "options": "\nStock Entry\nExisting Asset\nPurchase\nStock Capitalization",
            "allow_on_submit": 1,
            "permlevel": 1,
            "insert_after": "warehouse",
            "in_list_view": 1,
        },
        {
            "fieldname": "allocated_asset",
            "label": "Allocated Asset",
            "fieldtype": "Link",
            "options": "Asset",
            "allow_on_submit": 1,
            "permlevel": 1,
            "insert_after": "fulfillment_route",
        },
        {
            "fieldname": "unit_cost_ex_vat",
            "label": "Unit Cost Excluding VAT",
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "allow_on_submit": 1,
            "permlevel": 1,
            "read_only": 1,
            "insert_after": "allocated_asset",
        },
        {
            "fieldname": "cost_source",
            "label": "Cost Source",
            "fieldtype": "Small Text",
            "allow_on_submit": 1,
            "permlevel": 1,
            "read_only": 1,
            "insert_after": "unit_cost_ex_vat",
        },
    ],
    COMPANY: [
        {
            "fieldname": "borrow_in_transit_warehouse",
            "label": "Borrow In Transit Warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "insert_after": "default_in_transit_warehouse",
        },
        {
            "fieldname": "return_qa_hold_warehouse",
            "label": "Return QA Hold Warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "insert_after": "borrow_in_transit_warehouse",
        },
        {
            "fieldname": "return_repair_warehouse",
            "label": "Return Repair Warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "insert_after": "return_qa_hold_warehouse",
        },
        {
            "fieldname": "return_qa_hold_location",
            "label": "Return QA Hold Location",
            "fieldtype": "Link",
            "options": "Location",
            "insert_after": "return_repair_warehouse",
        },
        {
            "fieldname": "return_repair_location",
            "label": "Return Repair Location",
            "fieldtype": "Link",
            "options": "Location",
            "insert_after": "return_qa_hold_location",
        },
    ],
    ASSET_CAPITALIZATION: [
        {
            "fieldname": "material_request",
            "label": "Material Request",
            "fieldtype": "Link",
            "options": MATERIAL_REQUEST,
            "insert_after": "company",
            "no_copy": 1,
        },
    ],
    QUALITY_INSPECTION: [
        {
            "fieldname": "material_request",
            "label": "Material Request",
            "fieldtype": "Link",
            "options": MATERIAL_REQUEST,
            "insert_after": "reference_name",
            "no_copy": 1,
        },
        {
            "fieldname": "return_dispatch_transfer",
            "label": "Return Dispatch Transfer",
            "fieldtype": "Link",
            "options": "Dispatch Transfer",
            "insert_after": "material_request",
            "no_copy": 1,
        },
        {
            "fieldname": "return_disposition",
            "label": "Return Disposition",
            "fieldtype": "Select",
            "options": "\nRepairable\nDamaged Beyond Repair",
            "insert_after": "return_dispatch_transfer",
            "no_copy": 1,
        },
        {
            "fieldname": "release_stock_entry",
            "label": "Release Stock Entry",
            "fieldtype": "Link",
            "options": STOCK_ENTRY,
            "insert_after": "return_disposition",
            "read_only": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "repair_stock_entry",
            "label": "Repair Stock Entry",
            "fieldtype": "Link",
            "options": STOCK_ENTRY,
            "insert_after": "release_stock_entry",
            "read_only": 1,
            "no_copy": 1,
        },
    ],
    STOCK_ENTRY: [
        {
            "fieldname": "return_dispatch_transfer",
            "label": "Return Dispatch Transfer",
            "fieldtype": "Link",
            "options": "Dispatch Transfer",
            "insert_after": "purpose",
            "no_copy": 1,
        },
        {
            "fieldname": "borrowed_item_resolution",
            "label": "Borrowed Item Resolution",
            "fieldtype": "Link",
            "options": "Borrowed Item Resolution",
            "insert_after": "return_dispatch_transfer",
            "no_copy": 1,
        },
    ],
    ASSET_MOVEMENT: [
        {
            "fieldname": "material_request",
            "label": "Material Request",
            "fieldtype": "Link",
            "options": MATERIAL_REQUEST,
            "insert_after": "assets",
            "no_copy": 1,
        },
        {
            "fieldname": "return_dispatch_transfer",
            "label": "Return Dispatch Transfer",
            "fieldtype": "Link",
            "options": "Dispatch Transfer",
            "insert_after": "material_request",
            "no_copy": 1,
        },
        {
            "fieldname": "borrowed_item_resolution",
            "label": "Borrowed Item Resolution",
            "fieldtype": "Link",
            "options": "Borrowed Item Resolution",
            "insert_after": "return_dispatch_transfer",
            "no_copy": 1,
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
    """Material Request requires a custom permission table for Employee requesters."""
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
    _ensure_material_request_permission(
        C_LEVEL_APPROVER_ROLE,
        0,
        read=1,
        write=1,
        submit=1,
        report=1,
        print=1,
        email=1,
    )
    _ensure_material_request_permission(
        "Accounts User",
        0,
        read=1,
        write=1,
        report=1,
        print=1,
        email=1,
    )
    _ensure_material_request_permission("Accounts User", 1, read=1, write=1)
    # Workflow approval calls ``save`` for draft-to-draft decisions.  Keep the
    # dedicated approver out of create/submit/cancel rights; Workflow State's
    # ``allow_edit`` controls the Desk form while this minimal write right lets
    # Frappe persist the Approve/Reject action.
    # Preserve the native permissions before adding app-specific roles. Frappe
    # switches a DocType to its Custom DocPerm table once the first custom row
    # exists; copying first keeps the native operational roles intact.
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
    """Add only the operational Stock permissions required by the loan loop."""
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
