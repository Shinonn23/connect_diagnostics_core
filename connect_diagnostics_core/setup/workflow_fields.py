# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Code-managed fields for the normalized native Workflow baseline."""

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

CUSTOM_FIELDS = {
    doctype: [
        dict(_WORKFLOW_STATE),
        *[
            {
                "fieldname": fieldname,
                "label": label,
                "fieldtype": fieldtype,
                **({"options": options} if options else {}),
                "hidden": 1,
                "read_only": 1,
                "allow_on_submit": 1,
                "no_copy": 1,
                "is_system_generated": 1,
                **({"ignore_user_permissions": 1} if fieldtype == "Link" else {}),
            }
            for fieldname, label, fieldtype, options in _SHARED_APPROVAL_FIELDS
        ],
    ]
    for doctype in TARGET_DOCTYPES
}

_ROUTE_FIELDS = {
    "Asset Movement": (("approval_approver_user", "Approval Approver User", "Link", "User"),),
    "Journal Entry": (
        ("approval_digest", "Approval Digest", "Data", None),
        ("approval_digest_schema", "Approval Digest Schema", "Long Text", None),
        ("approval_maker_at", "Approval Maker At", "Datetime", None),
        ("approval_checker_user", "Approval Checker User", "Link", "User"),
        ("approval_checker_at", "Approval Checker At", "Datetime", None),
        ("approval_checker_employee", "Approval Checker Employee", "Link", "Employee"),
        ("approval_checker_signature", "Approval Checker Signature", "Long Text", None),
        ("approval_approver_user", "Approval Approver User", "Link", "User"),
        ("approval_approver_at", "Approval Approver At", "Datetime", None),
        ("approval_approver_employee", "Approval Approver Employee", "Link", "Employee"),
        ("approval_approver_signature", "Approval Approver Signature", "Long Text", None),
        ("approval_submit_proof", "Approval Submit Proof", "Data", None),
        ("approval_cancel_proof", "Approval Cancel Proof", "Data", None),
        ("approval_submit_actor", "Approval Submit Actor", "Link", "User"),
        ("approval_cancel_actor", "Approval Cancel Actor", "Link", "User"),
        ("approval_source_doctype", "Approval Source DocType", "Data", None),
        ("approval_source_name", "Approval Source Name", "Dynamic Link", "approval_source_doctype"),
        ("approval_source_action", "Approval Source Action", "Data", None),
        ("approval_operation_id", "Approval Operation ID", "Data", None),
        ("approval_source_proof", "Approval Source Proof", "Data", None),
    ),
    "Sales Order": (
        ("approval_revision", "Approval Revision", "Data", None),
        ("approval_digest", "Approval Digest", "Data", None),
        ("approval_maker_at", "Approval Maker At", "Datetime", None),
        ("approval_reviewer_at", "Approval Reviewer At", "Datetime", None),
        ("approval_approver_user", "Approval Approver User", "Link", "User"),
        ("approval_approver_at", "Approval Approver At", "Datetime", None),
    ),
    "Payment Entry": (
        ("approval_digest", "Approval Digest", "Data", None),
        ("approval_maker_at", "Approval Maker At", "Datetime", None),
        ("approval_checker_user", "Approval Checker User", "Link", "User"),
        ("approval_checker_at", "Approval Checker At", "Datetime", None),
        ("approval_approver_user", "Approval Approver User", "Link", "User"),
        ("approval_approver_at", "Approval Approver At", "Datetime", None),
    ),
}

for _doctype, _fields in _ROUTE_FIELDS.items():
    _existing = {str(field["fieldname"]) for field in CUSTOM_FIELDS[_doctype]}
    CUSTOM_FIELDS[_doctype].extend(
        {
            "fieldname": fieldname,
            "label": label,
            "fieldtype": fieldtype,
            **({"options": options} if options else {}),
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
            **({"ignore_user_permissions": 1} if fieldtype in {"Link", "Dynamic Link"} else {}),
        }
        for fieldname, label, fieldtype, options in _fields
        if fieldname not in _existing
    )

next(field for field in CUSTOM_FIELDS["Journal Entry"] if field["fieldname"] == "approval_operation_id")[
    "unique"
] = 1
