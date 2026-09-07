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

from connect_diagnostics_core.setup import print_action_fields


def capture_print_action(doc: Document, action_key: str) -> None:
    """Write one action snapshot onto ``doc`` without blocking missing signatures.

    This function is called by the named Frappe Workflow Transition Tasks below.
    The transition itself remains site-owned; the task only supplies the common
    audit fields needed by the print formats.
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

    employee = cast(
        Mapping[str, Any] | None,
        frappe.db.get_value(
            "Employee",
            {"user_id": frappe.session.user},
            ["name", "employee_name", "quotation_signature"],
            as_dict=True,
        ),
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

    signature = _text(employee.get("quotation_signature"))
    doc.set(action.employee_field, _text(employee.get("name")))
    doc.set(action.datetime_field, now_datetime())
    doc.set(action.signature_field, signature)

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
