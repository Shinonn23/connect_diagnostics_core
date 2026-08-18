# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.permissions import reset_perms, setup_custom_perms

COMPANY_DOCTYPE = "Company"
PAYMENT_ENTRY_DOCTYPE = "Payment Entry"
PAYMENT_REQUEST_DOCTYPE = "Payment Request"
WORKFLOW_STATE_FIELD = "payment_approval_state"
BASE_GRAND_TOTAL_FIELD = "base_grand_total"

EXECUTIVE_APPROVER_ROLE = "Executive P2P Approver"
AP_REVIEWER_ROLE = "P2P Finance Verifier"

EXECUTIVE_APPROVER_PROFILE = "Executive P2P Approver Add-on"
AP_REVIEWER_PROFILE = "P2P Finance Verifier Add-on"

ARIRAT_USER = "arirat.ba@connectdiagnostics.com"
SASIN_USER = "sasin.ba@connectdiagnostics.com"
KIATTISAK_USER = "kiattisak.ch@connectdiagnostics.com"

DRAFT_STATE = "Payment Request Draft"
SUBMITTED_STATE = "Payment Request Submitted"
PENDING_AP_REVIEW_STATE = "Pending Payment Request AP Review"
PENDING_EXECUTIVE_APPROVAL_STATE = "Pending Executive Payment Request Approval"
APPROVED_STATE = "Payment Request Approved"
REJECTED_STATE = "Payment Request Rejected"
CANCELLED_STATE = "Payment Request Cancelled"

REQUEST_APPROVAL_ACTION = "Request Payment Approval"
APPROVE_ACTION = "Approve Payment Request"
AP_REVIEW_ACTION = "Complete Payment Request AP Review"
REJECT_ACTION = "Reject Payment Request"
REVISE_ACTION = "Revise Payment Request"
SUBMIT_INWARD_ACTION = "Submit Payment Request"

CUSTOM_FIELDS = {
    PAYMENT_REQUEST_DOCTYPE: [
        {
            "fieldname": BASE_GRAND_TOTAL_FIELD,
            "label": "Amount (Company Currency)",
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "insert_after": "grand_total",
            "read_only": 1,
            "no_copy": 1,
            "depends_on": 'eval:doc.payment_request_type == "Outward"',
        },
    ],
}

MANAGED_ROLES = (EXECUTIVE_APPROVER_ROLE, AP_REVIEWER_ROLE)

ROLE_PROFILES = {
    EXECUTIVE_APPROVER_PROFILE: (EXECUTIVE_APPROVER_ROLE,),
    AP_REVIEWER_PROFILE: (AP_REVIEWER_ROLE,),
}

PERMISSION_FIELDS = (
    "select",
    "read",
    "write",
    "create",
    "delete",
    "submit",
    "cancel",
    "amend",
    "report",
    "export",
    "import",
    "share",
    "print",
    "email",
)
PERMISSION_COMPARISON_FIELDS = ("role", "permlevel", "if_owner", *PERMISSION_FIELDS, "mask")

APPROVER_PAYMENT_REQUEST_PERMISSIONS = {fieldname: 0 for fieldname in PERMISSION_FIELDS}
APPROVER_PAYMENT_REQUEST_PERMISSIONS.update(
    {
        "read": 1,
        "write": 1,
        "submit": 1,
    }
)

PAYMENT_REQUEST_PERMISSIONS = {
    EXECUTIVE_APPROVER_ROLE: APPROVER_PAYMENT_REQUEST_PERMISSIONS,
    AP_REVIEWER_ROLE: APPROVER_PAYMENT_REQUEST_PERMISSIONS,
}

PERMISSION_COPY_MARKER = {
    "parent": PAYMENT_REQUEST_DOCTYPE,
    "role": EXECUTIVE_APPROVER_ROLE,
    "permlevel": 0,
    "if_owner": 1,
}


def ensure_configuration() -> None:
    ensure_roles()
    ensure_role_profiles()
    ensure_payment_request_permissions()
    assign_payment_approvers(require_users=False)
    frappe.clear_cache(doctype=COMPANY_DOCTYPE)
    frappe.clear_cache(doctype=PAYMENT_REQUEST_DOCTYPE)


def assign_payment_approvers(
    arirat_user: str = ARIRAT_USER,
    sasin_user: str = SASIN_USER,
    kiattisak_user: str = KIATTISAK_USER,
    *,
    require_users: bool = True,
) -> None:
    assignments = (
        (arirat_user, EXECUTIVE_APPROVER_PROFILE),
        (sasin_user, EXECUTIVE_APPROVER_PROFILE),
        (kiattisak_user, AP_REVIEWER_PROFILE),
    )
    unavailable_count = 0
    for user_name, role_profile in assignments:
        if not _assign_role_profile_or_direct_roles(
            user_name,
            role_profile,
            require_user=require_users,
        ):
            unavailable_count += 1

    if unavailable_count:
        frappe.logger(__name__).warning(
            "Skipped %s payment approver assignments because required Users are missing or disabled",
            unavailable_count,
        )


def _assign_role_profile_or_direct_roles(
    user_name: str,
    role_profile: str,
    *,
    require_user: bool = True,
) -> bool:
    user = _get_enabled_user(user_name, required=require_user)
    if not user:
        return False

    current_profiles = {cast(str, row.role_profile) for row in user.get("role_profiles", [])}
    if current_profiles:
        if role_profile in current_profiles:
            return True
        user.append("role_profiles", {"role_profile": role_profile})
        user.save(ignore_permissions=True)
        return True

    current_roles = {cast(str, row.role) for row in user.get("roles", [])}
    missing_roles = [role for role in ROLE_PROFILES[role_profile] if role not in current_roles]
    if not missing_roles:
        return True
    for role in missing_roles:
        user.append("roles", {"role": role})
    user.save(ignore_permissions=True)
    return True


def _get_enabled_user(user_name: str, *, required: bool = True) -> Document | None:
    if not frappe.db.exists("User", user_name):
        if not required:
            return None
        frappe.throw(
            _("Required payment approver User {0} does not exist.").format(frappe.bold(user_name)),
            title=_("Payment approver setup failed"),
        )
    user = cast(Document, frappe.get_doc("User", user_name))
    if user.get("enabled"):
        return user
    if not required:
        return None
    frappe.throw(
        _("Required payment approver User {0} is disabled.").format(frappe.bold(user_name)),
        title=_("Payment approver setup failed"),
    )


def ensure_roles() -> None:
    for role_name in MANAGED_ROLES:
        if frappe.db.exists("Role", role_name):
            role = cast(Document, frappe.get_doc("Role", role_name))
            changed = False
            for fieldname, value in {"disabled": 0, "desk_access": 1, "is_custom": 1}.items():
                if role.get(fieldname) != value:
                    role.set(fieldname, value)
                    changed = True
            if changed:
                role.save(ignore_permissions=True)
            continue

        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": role_name,
                "disabled": 0,
                "desk_access": 1,
                "is_custom": 1,
            }
        ).insert(ignore_permissions=True)


def ensure_role_profiles() -> None:
    for profile_name, role_names in ROLE_PROFILES.items():
        if frappe.db.exists("Role Profile", profile_name):
            profile = cast(Document, frappe.get_doc("Role Profile", profile_name))
            current_roles = tuple(sorted(cast(str, row.role) for row in profile.get("roles", [])))
            desired_roles = tuple(sorted(role_names))
            if current_roles == desired_roles:
                continue
            profile.set("roles", [])
            for role_name in role_names:
                profile.append("roles", {"role": role_name})
            profile.save(ignore_permissions=True)
            continue

        profile = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Role Profile",
                    "role_profile": profile_name,
                    "roles": [{"role": role_name} for role_name in role_names],
                }
            ),
        )
        profile.insert(ignore_permissions=True)


def ensure_payment_request_permissions() -> None:
    copied_standard_permissions = bool(setup_custom_perms(PAYMENT_REQUEST_DOCTYPE))
    if copied_standard_permissions:
        _ensure_permission_copy_marker()

    for role_name, permissions in PAYMENT_REQUEST_PERMISSIONS.items():
        matches = frappe.get_all(
            "Custom DocPerm",
            filters={"parent": PAYMENT_REQUEST_DOCTYPE, "role": role_name, "permlevel": 0},
            pluck="name",
            order_by="creation asc",
        )
        if matches:
            permission = cast(Document, frappe.get_doc("Custom DocPerm", matches[0]))
            for duplicate in matches[1:]:
                frappe.delete_doc("Custom DocPerm", duplicate, force=True, ignore_permissions=True)
        else:
            permission = cast(
                Document,
                frappe.get_doc(
                    {
                        "doctype": "Custom DocPerm",
                        "parent": PAYMENT_REQUEST_DOCTYPE,
                        "role": role_name,
                        "permlevel": 0,
                        "if_owner": 0,
                    }
                ),
            )

        changed = permission.is_new()
        for fieldname, value in permissions.items():
            if permission.get(fieldname) != value:
                permission.set(fieldname, value)
                changed = True

        if not changed:
            continue
        if permission.is_new():
            permission.insert(ignore_permissions=True)
        else:
            permission.save(ignore_permissions=True)


def _ensure_permission_copy_marker() -> None:
    if frappe.db.exists("Custom DocPerm", PERMISSION_COPY_MARKER):
        return

    frappe.get_doc(
        {
            "doctype": "Custom DocPerm",
            **PERMISSION_COPY_MARKER,
            **{fieldname: 0 for fieldname in PERMISSION_FIELDS},
        }
    ).insert(ignore_permissions=True)
