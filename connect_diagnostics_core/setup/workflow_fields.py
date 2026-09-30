# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Code-managed Custom Fields required by native Frappe Workflows."""

CUSTOM_FIELDS = {
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
    existing = {str(field["fieldname"]) for field in CUSTOM_FIELDS.get(_doctype, [])}
    CUSTOM_FIELDS.setdefault(_doctype, []).extend(
        {
            **field,
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "is_system_generated": 1,
            **(
                {"ignore_user_permissions": 1}
                if _doctype == "Payroll Entry" and field["fieldtype"] == "Link"
                else {}
            ),
        }
        for field in _APPROVAL_FIELDS
        if str(field["fieldname"]) not in existing
    )
