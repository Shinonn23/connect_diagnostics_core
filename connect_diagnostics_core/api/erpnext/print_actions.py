# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Workflow transition tasks that snapshot Employee-backed print actions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from connect_diagnostics_core.api.frappe.approval_controls import (
    require_distinct_actors,
    require_permission,
)
from connect_diagnostics_core.setup import print_action_fields


def capture_print_action(doc: Document, action_key: str) -> None:
    """Write one Employee-backed action snapshot onto ``doc``.

    This function is called by the named Frappe Workflow Transition Tasks below.
    Actions configured as signed approvals fail closed when the active Employee
    link or signature is missing.
    """
    action = next(
        (
            candidate
            for candidate in print_action_fields.get_actions(doc.doctype)
            if candidate.key == action_key
        ),
        None,
    )
    if action is None:
        return

    if action.protected:
        require_permission(doc)
        if doc.doctype == "Stock Entry":
            previous_actor = doc.get("approval_reviewer_user") if action.key == "authorized" else None
            require_distinct_actors(
                _text(doc.get("owner")),
                frappe.session.user,
                (_text(previous_actor),),
            )

    employee = cast(
        Mapping[str, Any] | None,
        frappe.db.get_value(
            "Employee",
            {"user_id": frappe.session.user, "status": "Active"},
            ["name", "employee_name", "approval_signature"],
            as_dict=True,
        ),
    )
    if not employee and action.required_signature:
        frappe.throw(
            _("A linked Employee with an approval signature is required for the {0} action.").format(
                action_key.replace("_", " ")
            )
        )
    if not employee:
        frappe.msgprint(
            _("No Employee is linked to the user performing the {0} action.").format(
                action_key.replace("_", " ")
            ),
            title=_("Print signature warning"),
            indicator="orange",
        )
        return

    signature = _text(employee.get("approval_signature"))
    if action.required_signature and not signature:
        frappe.throw(
            _("An approval signature is required for the {0} action.").format(action_key.replace("_", " "))
        )
    doc.set(action.employee_field, _text(employee.get("name")))
    doc.set(action.datetime_field, now_datetime())
    doc.set(action.signature_field, signature)

    if doc.doctype == "Stock Entry" and action.key == "checked":
        from connect_diagnostics_core.api.erpnext.stock_entry_workflow import capture_review_snapshot

        capture_review_snapshot(doc)
    elif doc.doctype == "Stock Entry" and action.key == "authorized":
        from connect_diagnostics_core.api.erpnext.stock_entry_workflow import capture_authorization_snapshot

        capture_authorization_snapshot(doc)

    if not signature:
        frappe.msgprint(
            _("Employee {0} has no signature. The {1} action was recorded without a signature.").format(
                _text(employee.get("employee_name")) or _text(employee.get("name")),
                action_key.replace("_", " "),
            ),
            title=_("Print signature warning"),
            indicator="orange",
        )


def capture_submit_action(doc: Document) -> None:
    """Workflow task for the Submit action."""
    capture_print_action(doc, "submit")


def capture_received_action(doc: Document) -> None:
    """Workflow task for the Received action."""
    capture_print_action(doc, "received")


def capture_delivered_action(doc: Document) -> None:
    """Workflow task for the Delivered action."""
    capture_print_action(doc, "delivered")


def capture_prepared_action(doc: Document) -> None:
    """Workflow task for the Prepared action."""
    capture_print_action(doc, "prepared")


def capture_ordered_action(doc: Document) -> None:
    """Workflow task for the Ordered action."""
    capture_print_action(doc, "ordered")


def capture_checked_action(doc: Document) -> None:
    """Workflow task for the Checked action."""
    capture_print_action(doc, "checked")


def capture_authorized_action(doc: Document) -> None:
    """Workflow task for the Authorized action."""
    capture_print_action(doc, "authorized")


def capture_return_received_action(doc: Document) -> None:
    """Workflow task for the Return Received action."""
    capture_print_action(doc, "return_received")


def capture_warehouse_checked_action(doc: Document) -> None:
    """Workflow task for the Warehouse Checked action."""
    capture_print_action(doc, "warehouse_checked")


def capture_signatory_action(doc: Document) -> None:
    """Workflow task for the Quotation Signatory action."""
    capture_print_action(doc, "signatory")


def capture_signed_action(doc: Document) -> None:
    """Workflow task for the Withholding Tax Certificate Signed action."""
    capture_print_action(doc, "signed")


def _text(value: Any) -> str:
    return str(value or "").strip()
