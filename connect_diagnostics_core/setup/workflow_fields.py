# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Code-managed fields for the normalized native Workflow baseline."""

from typing import Any

TARGET_DOCTYPES = (
    "Stock Entry",
    "Stock Reconciliation",
    "Asset Movement",
    "Journal Entry",
    "Sales Order",
    "Sales Invoice",
    "Purchase Order",
    "Purchase Invoice",
    "Payment Entry",
    "Payroll Entry",
)

_WORKFLOW_STATE = {
    "fieldname": "workflow_state",
    "label": "Workflow State",
    "fieldtype": "Link",
    "options": "Workflow State",
    "hidden": 1,
    "allow_on_submit": 1,
    "no_copy": 1,
    "is_system_generated": 1,
    "ignore_user_permissions": 1,
}

_SHARED_APPROVAL_FIELDS = (
    ("approval_maker_user", "Approval Maker User", "Link", "User"),
    ("approval_reviewer_user", "Approval Reviewer User", "Link", "User"),
    ("approval_authorized_user", "Approval Authorized User", "Link", "User"),
    ("approval_critical_digest", "Approval Critical Digest", "Data", None),
)

_PAYROLL_OUTPUT_FIELDS = (
    ("output_reviewed_by", "Output Reviewed By", "Link", "User"),
    ("output_reviewed_at", "Output Reviewed At", "Datetime", None),
    ("output_review_signature", "Output Review Signature", "Data", None),
    ("output_review_digest", "Output Review Digest", "Data", None),
    ("output_review_version", "Output Review Version", "Data", None),
    ("output_review_revision", "Output Review Revision", "Int", None),
)

CUSTOM_FIELDS: dict[str, list[dict[str, Any]]] = {
    "Journal Entry": [
        {
            "fieldname": "workflow_state",
            "label": "Workflow State",
            "fieldtype": "Link",
            "options": "Workflow State",
            "hidden": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
            "ignore_user_permissions": 1,
        },
        *[
            {
                "fieldname": fieldname,
                "label": label,
                "fieldtype": fieldtype,
                "options": options,
                "hidden": 1,
                "read_only": 1,
                "allow_on_submit": 1,
                "no_copy": 1,
                "is_system_generated": 1,
                **({"ignore_user_permissions": 1} if fieldtype in {"Link", "Dynamic Link"} else {}),
            }
            for fieldname, label, fieldtype, options in (
                ("approval_digest", "Approval Digest", "Data", ""),
                ("approval_critical_digest", "Approval Critical Digest", "Data", ""),
                ("approval_digest_schema", "Approval Digest Schema", "Long Text", ""),
                ("approval_maker_user", "Approval Maker User", "Link", "User"),
                ("approval_maker_at", "Approval Maker At", "Datetime", ""),
                ("approval_checker_user", "Approval Checker User", "Link", "User"),
                ("approval_checker_at", "Approval Checker At", "Datetime", ""),
                ("approval_checker_employee", "Approval Checker Employee", "Link", "Employee"),
                ("approval_checker_signature", "Approval Checker Signature", "Long Text", ""),
                ("approval_approver_user", "Approval Approver User", "Link", "User"),
                ("approval_approver_at", "Approval Approver At", "Datetime", ""),
                ("approval_approver_employee", "Approval Approver Employee", "Link", "Employee"),
                ("approval_approver_signature", "Approval Approver Signature", "Long Text", ""),
                ("approval_submit_proof", "Approval Submit Proof", "Data", ""),
                ("approval_cancel_proof", "Approval Cancel Proof", "Data", ""),
                ("approval_submit_actor", "Approval Submit Actor", "Link", "User"),
                ("approval_cancel_actor", "Approval Cancel Actor", "Link", "User"),
                ("approval_source_doctype", "Approval Source DocType", "Data", ""),
                (
                    "approval_source_name",
                    "Approval Source Name",
                    "Dynamic Link",
                    "approval_source_doctype",
                ),
                ("approval_source_action", "Approval Source Action", "Data", ""),
                ("approval_operation_id", "Approval Operation ID", "Data", ""),
                ("approval_source_proof", "Approval Source Proof", "Data", ""),
            )
        ],
    ],
    "Asset Movement": [
        {
            "fieldname": "workflow_state",
            "label": "Workflow State",
            "fieldtype": "Link",
            "options": "Workflow State",
            "hidden": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_maker_user",
            "label": "Approval Maker User",
            "fieldtype": "Link",
            "options": "User",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_reviewer_user",
            "label": "Approval Reviewer User",
            "fieldtype": "Link",
            "options": "User",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_approver_user",
            "label": "Approval Approver User",
            "fieldtype": "Link",
            "options": "User",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_critical_digest",
            "label": "Approval Critical Digest",
            "fieldtype": "Data",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "checked_by",
            "label": "Print Action: Checked By",
            "fieldtype": "Link",
            "options": "Employee",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "ignore_user_permissions": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "checked_at",
            "label": "Print Action: Checked At",
            "fieldtype": "Datetime",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "checked_signature",
            "label": "Print Action: Checked Signature",
            "fieldtype": "Signature",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "authorized_by",
            "label": "Print Action: Authorized By",
            "fieldtype": "Link",
            "options": "Employee",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "ignore_user_permissions": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "authorized_at",
            "label": "Print Action: Authorized At",
            "fieldtype": "Datetime",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "authorized_signature",
            "label": "Print Action: Authorized Signature",
            "fieldtype": "Signature",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
    ],
    "Sales Order": [
        {
            "fieldname": fieldname,
            "label": label,
            "fieldtype": fieldtype,
            **({"options": "User"} if fieldtype == "Link" else {}),
        }
        for fieldname, label, fieldtype in (
            ("approval_revision", "Approval Revision", "Data"),
            ("approval_digest", "Approval Digest", "Data"),
            ("approval_maker_at", "Approval Maker At", "Datetime"),
            ("approval_reviewer_at", "Approval Reviewer At", "Datetime"),
            ("approval_approver_user", "Approval Approver User", "Link"),
            ("approval_approver_at", "Approval Approver At", "Datetime"),
        )
    ],
    "Payment Entry": [
        {
            "fieldname": "workflow_state",
            "label": "Workflow State",
            "fieldtype": "Link",
            "options": "Workflow State",
            "hidden": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        *[
            {
                "fieldname": fieldname,
                "label": label,
                "fieldtype": fieldtype,
                "options": "User" if fieldtype == "Link" else None,
            }
            for fieldname, label, fieldtype in (
                ("approval_digest", "Approval Digest", "Data"),
                ("approval_maker_at", "Approval Maker At", "Datetime"),
                ("approval_checker_user", "Approval Checker User", "Link"),
                ("approval_checker_at", "Approval Checker At", "Datetime"),
                ("approval_approver_user", "Approval Approver User", "Link"),
                ("approval_approver_at", "Approval Approver At", "Datetime"),
                ("approval_submit_actor", "Approval Submit Actor", "Link"),
                ("approval_cancel_actor", "Approval Cancel Actor", "Link"),
            )
        ],
    ],
    "Purchase Order": [
        {
            "fieldname": "workflow_state",
            "label": "Workflow State",
            "fieldtype": "Link",
            "options": "Workflow State",
            "hidden": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_critical_digest",
            "label": "Approval Critical Digest",
            "fieldtype": "Data",
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_digest_version",
            "label": "Approval Digest Version",
            "fieldtype": "Data",
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_reviewer_user",
            "label": "Approval Reviewer User",
            "fieldtype": "Link",
            "options": "User",
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_authorized_user",
            "label": "Approval Authorized User",
            "fieldtype": "Link",
            "options": "User",
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
    ],
    "Stock Entry": [
        {
            "fieldname": "workflow_state",
            "label": "Workflow State",
            "fieldtype": "Link",
            "options": "Workflow State",
            "hidden": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "freeze_exception",
            "label": "Freeze Exception",
            "fieldtype": "Check",
            "insert_after": "workflow_state",
            "description": "Request the narrowly scoped native Freeze Exception route.",
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "freeze_exception_reason",
            "label": "Freeze Exception Reason",
            "fieldtype": "Small Text",
            "insert_after": "freeze_exception",
            "mandatory_depends_on": "eval:doc.freeze_exception",
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "freeze_exception_reconciliation_scope",
            "label": "Freeze Exception Reconciliation Scope",
            "fieldtype": "Long Text",
            "insert_after": "freeze_exception_reason",
            "description": "Server-captured Freeze scope accepted by the native Emergency approval.",
            "read_only": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_critical_digest",
            "label": "Approval Critical Fields Digest",
            "fieldtype": "Data",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_reviewer_user",
            "label": "Approval Reviewer User",
            "fieldtype": "Link",
            "options": "User",
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_authorized_user",
            "label": "Approval Authorized User",
            "fieldtype": "Link",
            "options": "User",
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
    ],
    "Purchase Invoice": [
        {
            "fieldname": "workflow_state",
            "label": "Workflow State",
            "fieldtype": "Link",
            "options": "Workflow State",
            "hidden": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "trial_policy_warning",
            "label": "Trial Policy Warning",
            "fieldtype": "Small Text",
            "read_only": 1,
            "no_copy": 1,
            "is_system_generated": 1,
            "insert_after": "workflow_state",
            "description": "Test policy only. Review and replace before UAT or production.",
            "default": "TEST POLICY ONLY — Review and replace before UAT or production.",
        },
        {
            "fieldname": "approval_critical_digest",
            "label": "Approval Critical Digest",
            "fieldtype": "Data",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_reviewer_user",
            "label": "Approval Reviewer User",
            "fieldtype": "Link",
            "options": "User",
            "ignore_user_permissions": 1,
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
        {
            "fieldname": "approval_authorized_user",
            "label": "Approval Authorized User",
            "fieldtype": "Link",
            "options": "User",
            "ignore_user_permissions": 1,
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        },
    ],
}

_APPROVAL_FIELDS = (
    {
        "fieldname": "approval_maker_user",
        "label": "Approval Maker User",
        "fieldtype": "Link",
        "options": "User",
    },
    {
        "fieldname": "approval_reviewer_user",
        "label": "Approval Reviewer User",
        "fieldtype": "Link",
        "options": "User",
    },
    {
        "fieldname": "approval_authorized_user",
        "label": "Approval Authorized User",
        "fieldtype": "Link",
        "options": "User",
    },
    {
        "fieldname": "approval_critical_digest",
        "label": "Approval Critical Digest",
        "fieldtype": "Data",
    },
)

for _doctype in (
    "Stock Entry",
    "Stock Reconciliation",
    "Asset Movement",
    "Journal Entry",
    "Sales Order",
    "Sales Invoice",
    "Purchase Order",
    "Purchase Invoice",
    "Payment Entry",
    "Payroll Entry",
):
    if not any(field["fieldname"] == "workflow_state" for field in CUSTOM_FIELDS.get(_doctype, [])):
        CUSTOM_FIELDS.setdefault(_doctype, []).insert(0, dict(_WORKFLOW_STATE))
    existing = {str(field["fieldname"]) for field in CUSTOM_FIELDS.get(_doctype, [])}
    CUSTOM_FIELDS.setdefault(_doctype, []).extend(
        {
            **field,
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
        }
        for field in _APPROVAL_FIELDS
        if str(field["fieldname"]) not in existing
    )

CUSTOM_FIELDS["Payroll Entry"].extend(
    {
        "fieldname": fieldname,
        "label": label,
        "fieldtype": fieldtype,
        "options": options,
        "hidden": 1,
        "read_only": 1,
        "allow_on_submit": 1,
        "no_copy": 1,
        "is_system_generated": 1,
    }
    for fieldname, label, fieldtype, options in _PAYROLL_OUTPUT_FIELDS
)

CUSTOM_FIELDS["Sales Order"].extend(
    {
        "fieldname": fieldname,
        "label": label,
        "fieldtype": fieldtype,
        **({"options": options} if options else {}),
        "hidden": int(fieldname != "billing_receivable_account"),
        "read_only": 1,
        "no_copy": 1,
        "is_system_generated": 1,
        "insert_after": "customer",
    }
    for fieldname, label, fieldtype, options in (
        ("billing_authority_revision", "Billing Authority Revision", "Data", None),
        ("billing_authority_digest", "Billing Authority Digest", "Data", None),
        ("billing_authorized_by", "Billing Authorized By", "Link", "User"),
        ("billing_authorized_at", "Billing Authorized At", "Datetime", None),
        ("billing_authorized_signature", "Billing Authorized Signature", "Signature", None),
        ("billing_authority_source_state", "Billing Authority Source State", "Data", None),
        ("billing_receivable_account", "Billing Receivable Account", "Link", "Account"),
    )
)

for _rows in CUSTOM_FIELDS.values():
    for _field in _rows:
        _fieldname = str(_field["fieldname"])
        if _fieldname == "workflow_state" or _fieldname.startswith("approval_"):
            _field.update(
                hidden=1,
                read_only=1,
                allow_on_submit=1,
                no_copy=1,
                is_system_generated=1,
            )
        if _field.get("fieldtype") == "Link" and _field.get("options") in {
            "User",
            "Employee",
            "Workflow State",
        }:
            _field["ignore_user_permissions"] = 1
