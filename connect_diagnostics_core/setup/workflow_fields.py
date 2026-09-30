# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Code-managed Custom Fields required by native Frappe Workflows."""

CUSTOM_FIELDS = {
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

# Nullable unique values allow ordinary Journal Entries to remain unmarked while
# database-enforcing one generated draft for each source operation.
next(field for field in CUSTOM_FIELDS["Journal Entry"] if field["fieldname"] == "approval_operation_id")[
    "unique"
] = 1
