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
PURCHASE_ORDER = "Purchase Order"
PURCHASE_RECEIPT = "Purchase Receipt"
PURCHASE_INVOICE = "Purchase Invoice"

SASIN_USER = "sasin.ba@connectdiagnostics.com"
ARIRAT_USER = "arirat.ba@connectdiagnostics.com"
KIATTISAK_USER = "kiattisak.ch@connectdiagnostics.com"

EXECUTIVE_ROLE = "Executive P2P Approver"
P2P_VERIFIER_ROLE = "P2P Finance Verifier"
SUPPLIER_ACTIVATOR_ROLE = "Supplier Activator"
PURCHASE_REQUESTER_ROLE = "Purchase Requester"

EXECUTIVE_PROFILE = "Executive P2P Approver Add-on"
VERIFIER_PROFILE = "P2P Finance Verifier Add-on"
ACTIVATOR_PROFILE = "Supplier Activator Add-on"

SUPPLIER_DRAFT = "Supplier Draft"
SUPPLIER_VERIFICATION = "Pending Supplier Verification"
SUPPLIER_ACTIVATION = "Pending Supplier Activation"
SUPPLIER_ACTIVE = "Supplier Active"
SUPPLIER_LEGACY_ACTIVE = "Supplier Active (Legacy)"

BANK_DRAFT = "Supplier Bank Change Draft"
BANK_VERIFICATION = "Pending Supplier Bank Verification"
BANK_APPROVAL = "Pending Supplier Bank Approval"
BANK_VERIFIED = "Supplier Bank Verified"
BANK_REJECTED = "Supplier Bank Change Rejected"

MR_DRAFT = "Material Request Draft"
MR_PENDING = "Pending Material Request Approval"
MR_APPROVED = "Material Request Approved"
MR_REJECTED = "Material Request Rejected"

PO_DRAFT = "Purchase Order Draft"
PO_FINANCE = "Pending Purchase Order Finance Review"
PO_EXCEPTION = "Pending Purchase Order Exception Approval"
PO_APPROVED = "Purchase Order Approved"
PO_REJECTED = "Purchase Order Rejected"

RECEIPT_DRAFT = "Purchase Receipt Draft"
RECEIPT_CHECK = "Pending Goods Inspection"
RECEIPT_ACCEPTED = "Purchase Receipt Accepted"

PI_DRAFT = "Purchase Invoice Draft"
PI_VERIFICATION = "Pending Purchase Invoice Verification"
PI_EXCEPTION = "Pending Purchase Invoice Exception Approval"
PI_VERIFIED = "Purchase Invoice Verified"
PI_REJECTED = "Purchase Invoice Rejected"

CACHE_CLEAR_DOCTYPES = (
    SUPPLIER,
    BANK_CHANGE_REQUEST,
    MATERIAL_REQUEST,
    PURCHASE_ORDER,
    PURCHASE_RECEIPT,
    PURCHASE_INVOICE,
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
            "label": "Purchase Reason",
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

_ROLES = (EXECUTIVE_ROLE, P2P_VERIFIER_ROLE, SUPPLIER_ACTIVATOR_ROLE, PURCHASE_REQUESTER_ROLE)
_PROFILES = {
    EXECUTIVE_PROFILE: (EXECUTIVE_ROLE,),
    VERIFIER_PROFILE: (P2P_VERIFIER_ROLE,),
    ACTIVATOR_PROFILE: (SUPPLIER_ACTIVATOR_ROLE,),
}


def ensure_configuration() -> None:
    ensure_roles()
    ensure_role_profiles()
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


def ensure_role_profiles() -> None:
    for profile_name, roles in _PROFILES.items():
        if frappe.db.exists("Role Profile", profile_name):
            profile = cast(Document, frappe.get_doc("Role Profile", profile_name))
            if tuple(sorted(cast(str, row.role) for row in profile.get("roles", []))) == tuple(sorted(roles)):
                continue
            profile.set("roles", [{"role": role} for role in roles])
            profile.save(ignore_permissions=True)
            continue
        frappe.get_doc(
            {
                "doctype": "Role Profile",
                "role_profile": profile_name,
                "roles": [{"role": role} for role in roles],
            }
        ).insert(ignore_permissions=True)


def assign_role_holders() -> None:
    for user, profile in (
        (SASIN_USER, ACTIVATOR_PROFILE),
        (KIATTISAK_USER, VERIFIER_PROFILE),
        (SASIN_USER, EXECUTIVE_PROFILE),
        (ARIRAT_USER, EXECUTIVE_PROFILE),
    ):
        _assign_profile(user, profile)
    for user in frappe.get_all(
        "Employee", filters={"status": "Active", "user_id": ["is", "set"]}, pluck="user_id"
    ):
        _assign_role(cast(str, user), PURCHASE_REQUESTER_ROLE)


def _assign_profile(user_name: str, profile_name: str) -> None:
    if not frappe.db.exists("User", user_name):
        return
    user = cast(Document, frappe.get_doc("User", user_name))
    if not user.get("enabled"):
        return
    profiles = {cast(str, row.role_profile) for row in user.get("role_profiles", [])}
    if profiles:
        if profile_name not in profiles:
            user.append("role_profiles", {"role_profile": profile_name})
            user.save(ignore_permissions=True)
        return
    for role_name in _PROFILES[profile_name]:
        _assign_role(user_name, role_name)


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
