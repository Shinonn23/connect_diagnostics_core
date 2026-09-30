# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Code-managed Custom Fields required by native Frappe Workflows."""

CUSTOM_FIELDS = {
    "Sales Order": [
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
        for fieldname, label, fieldtype, options in (
            ("approval_revision", "Approval Revision", "Data", ""),
            ("approval_digest", "Approval Digest", "Data", ""),
            ("approval_maker_user", "Approval Maker User", "Link", "User"),
            ("approval_maker_at", "Approval Maker At", "Datetime", ""),
            ("approval_reviewer_user", "Approval Reviewer User", "Link", "User"),
            ("approval_reviewer_at", "Approval Reviewer At", "Datetime", ""),
            ("approval_approver_user", "Approval Approver User", "Link", "User"),
            ("approval_approver_at", "Approval Approver At", "Datetime", ""),
        )
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
    ],
}
