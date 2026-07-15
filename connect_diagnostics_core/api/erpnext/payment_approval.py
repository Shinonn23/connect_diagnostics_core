# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, flt, get_datetime, now_datetime
from frappe.workflow.doctype.workflow_action.workflow_action import process_workflow_actions

from connect_diagnostics_core.setup.payment_approval import (
    APPROVAL_DUE_AT_FIELD,
    APPROVED_STATE,
    CANCELLED_STATE,
    ESCALATED_LOW_VALUE_STATE,
    ESCALATED_PRIMARY_STATE,
    ESCALATION_ROLE,
    LOW_VALUE_APPROVER_ROLE,
    PAYMENT_ENTRY_DOCTYPE,
    PENDING_LOW_VALUE_STATE,
    PENDING_PRIMARY_STATE,
    PRIMARY_APPROVER_ROLE,
    REJECTED_STATE,
    SECONDARY_APPROVER_ROLE,
    WORKFLOW_STATE_FIELD,
)

PENDING_ESCALATION_STATES = (PENDING_LOW_VALUE_STATE, PENDING_PRIMARY_STATE)
ACCOUNTING_ROLES = frozenset({"Accounts User", "Accounts Manager"})
PAYMENT_APPROVER_ROLES = frozenset(
    {
        PRIMARY_APPROVER_ROLE,
        SECONDARY_APPROVER_ROLE,
        LOW_VALUE_APPROVER_ROLE,
    }
)
ACTIONABLE_WORKFLOW_STATES = frozenset(
    {
        PENDING_LOW_VALUE_STATE,
        PENDING_PRIMARY_STATE,
        ESCALATED_LOW_VALUE_STATE,
        ESCALATED_PRIMARY_STATE,
        REJECTED_STATE,
    }
)
ESCALATED_STATE_BY_PENDING_STATE = {
    PENDING_LOW_VALUE_STATE: ESCALATED_LOW_VALUE_STATE,
    PENDING_PRIMARY_STATE: ESCALATED_PRIMARY_STATE,
}
ESCALATION_BATCH_SIZE = 100
APPROVAL_DECISION_STATES = frozenset(
    {
        PENDING_LOW_VALUE_STATE,
        PENDING_PRIMARY_STATE,
        ESCALATED_LOW_VALUE_STATE,
        ESCALATED_PRIMARY_STATE,
    }
)
LOW_VALUE_APPROVAL_STATES = frozenset(
    {
        PENDING_LOW_VALUE_STATE,
        ESCALATED_LOW_VALUE_STATE,
    }
)
APPROVAL_EDIT_ROLES_BY_STATE = {
    PENDING_LOW_VALUE_STATE: frozenset({LOW_VALUE_APPROVER_ROLE}),
    PENDING_PRIMARY_STATE: frozenset({PRIMARY_APPROVER_ROLE}),
    ESCALATED_LOW_VALUE_STATE: frozenset({LOW_VALUE_APPROVER_ROLE, SECONDARY_APPROVER_ROLE}),
    ESCALATED_PRIMARY_STATE: frozenset({PRIMARY_APPROVER_ROLE, SECONDARY_APPROVER_ROLE}),
}


def validate_before_submit(doc: Document, _method: str) -> None:
    previous_doc = _get_previous_doc(doc)
    _validate_creator_unchanged(doc, previous_doc)
    _validate_workflow_state_write_access(doc, previous_doc)
    _maintain_approval_deadline(doc, previous_doc)
    previous_state = cast(str, previous_doc.get(WORKFLOW_STATE_FIELD) or "") if previous_doc else ""
    payment_type = cast(str, doc.get("payment_type") or "")
    approval_state = cast(str, doc.get(WORKFLOW_STATE_FIELD) or "")

    if approval_state in {APPROVED_STATE, REJECTED_STATE}:
        _validate_approval_decision(doc, previous_doc)

    if payment_type != "Pay" and previous_state not in APPROVAL_DECISION_STATES:
        _validate_non_payment_submitter(doc)
        return

    if payment_type != "Pay" or approval_state != APPROVED_STATE:
        frappe.throw(
            _(
                "Outgoing Payment Entry must be approved through the payment approval workflow before submission."
            ),
            title=_("Payment approval required"),
        )


def validate_payment_approval_transition(doc: Document, _method: str) -> None:
    previous_doc = _get_previous_doc(doc)
    _validate_creator_unchanged(doc, previous_doc)
    _validate_workflow_state_write_access(doc, previous_doc)
    _maintain_approval_deadline(doc, previous_doc)
    _validate_approval_decision(doc, previous_doc)


def set_cancelled_workflow_state(doc: Document, _method: str) -> None:
    doc.set(WORKFLOW_STATE_FIELD, CANCELLED_STATE)


def validate_before_discard(doc: Document, _method: str) -> None:
    approval_state = cast(str, doc.get(WORKFLOW_STATE_FIELD) or "")
    if doc.get("payment_type") != "Pay" or approval_state not in ACTIONABLE_WORKFLOW_STATES:
        return
    frappe.throw(
        _(
            "An outgoing Payment Entry in the approval workflow cannot be discarded. "
            "Complete the workflow instead."
        ),
        title=_("Payment approval is active"),
    )


def clear_completed_workflow_actions_for_next_state(doc: Document, _method: str) -> None:
    previous_doc = _get_previous_doc(doc)
    if not previous_doc:
        return

    previous_state = cast(str, previous_doc.get(WORKFLOW_STATE_FIELD) or "")
    next_state = cast(str, doc.get(WORKFLOW_STATE_FIELD) or "")
    payment_entry_name = cast(str, doc.get("name") or "")
    if not payment_entry_name or previous_state == next_state or next_state not in ACTIONABLE_WORKFLOW_STATES:
        return

    _delete_completed_workflow_actions(payment_entry_name, next_state)


def _get_previous_doc(doc: Document) -> Document | None:
    get_doc_before_save = getattr(doc, "get_doc_before_save", None)
    if not callable(get_doc_before_save):
        return None
    return cast(Document | None, get_doc_before_save())


def _validate_approval_decision(doc: Document, previous_doc: Document | None) -> None:
    next_state = cast(str, doc.get(WORKFLOW_STATE_FIELD) or "")
    if next_state not in {APPROVED_STATE, REJECTED_STATE}:
        return

    previous_state = cast(str, previous_doc.get(WORKFLOW_STATE_FIELD) or "") if previous_doc else ""
    if previous_state == next_state:
        return
    if previous_state not in APPROVAL_DECISION_STATES:
        frappe.throw(
            _("Payment approval decisions are only allowed from a pending approval state."),
            title=_("Invalid payment approval transition"),
        )

    if frappe.session.user != "Administrator" and doc.get("owner") == frappe.session.user:
        frappe.throw(
            _("You cannot approve or reject a Payment Entry that you created."),
            title=_("Self approval is not allowed"),
        )

    if next_state != APPROVED_STATE:
        return
    if doc.get("payment_type") != "Pay":
        frappe.throw(
            _("Only outgoing Payment Entries can use the payment approval states."),
            title=_("Invalid payment approval transition"),
        )
    if previous_state in LOW_VALUE_APPROVAL_STATES and flt(doc.get("base_paid_amount")) >= 1500:
        frappe.throw(
            _("Payments of THB 1,500 or more require primary approval."),
            title=_("Primary payment approval required"),
        )


def _validate_creator_unchanged(doc: Document, previous_doc: Document | None) -> None:
    if not previous_doc or doc.get("owner") == previous_doc.get("owner"):
        return
    frappe.throw(
        _("The creator of a Payment Entry cannot be changed."),
        title=_("Payment creator cannot be changed"),
    )


def _validate_workflow_state_write_access(doc: Document, previous_doc: Document | None) -> None:
    if not previous_doc or frappe.session.user == "Administrator" or bool(doc.flags.ignore_permissions):
        return

    roles = set(frappe.get_roles())
    previous_state = cast(str, previous_doc.get(WORKFLOW_STATE_FIELD) or "")
    allowed_roles = set(APPROVAL_EDIT_ROLES_BY_STATE.get(previous_state, ()))

    if previous_state in APPROVAL_DECISION_STATES:
        if doc.get("payment_type") != "Pay":
            allowed_roles.clear()
        elif previous_state in LOW_VALUE_APPROVAL_STATES and flt(doc.get("base_paid_amount")) >= 1500:
            allowed_roles.discard(LOW_VALUE_APPROVER_ROLE)

        if allowed_roles.intersection(roles):
            return
        frappe.throw(
            _("You cannot edit this Payment Entry in its current payment approval state."),
            title=_("Payment approval role required"),
        )

    if PAYMENT_APPROVER_ROLES.intersection(roles) and not ACCOUNTING_ROLES.intersection(roles):
        frappe.throw(
            _("Payment approver roles do not grant general Payment Entry editing access."),
            title=_("Accounts role required"),
        )


def _maintain_approval_deadline(doc: Document, previous_doc: Document | None) -> None:
    next_state = cast(str, doc.get(WORKFLOW_STATE_FIELD) or "")
    previous_state = cast(str, previous_doc.get(WORKFLOW_STATE_FIELD) or "") if previous_doc else ""

    if next_state in PENDING_ESCALATION_STATES and previous_state != next_state:
        doc.set(APPROVAL_DUE_AT_FIELD, add_to_date(now_datetime(), hours=24))
        return

    if not previous_doc:
        doc.set(APPROVAL_DUE_AT_FIELD, None)
        return

    current_due_at = doc.get(APPROVAL_DUE_AT_FIELD)
    previous_due_at = previous_doc.get(APPROVAL_DUE_AT_FIELD)
    if _same_datetime(current_due_at, previous_due_at):
        return
    frappe.throw(
        _("The payment approval deadline is managed by the system and cannot be changed."),
        title=_("Payment approval deadline cannot be changed"),
    )


def _same_datetime(first: Any, second: Any) -> bool:
    if not first and not second:
        return True
    if not first or not second:
        return False
    return get_datetime(first) == get_datetime(second)


def _validate_non_payment_submitter(doc: Document) -> None:
    if frappe.session.user == "Administrator" or bool(doc.flags.ignore_permissions):
        return
    roles = set(frappe.get_roles())
    if not PAYMENT_APPROVER_ROLES.intersection(roles) or ACCOUNTING_ROLES.intersection(roles):
        return
    frappe.throw(
        _("Only an Accounts User or Accounts Manager can submit a non-outgoing Payment Entry."),
        title=_("Accounts role required"),
    )


def escalate_due_payment_approvals() -> None:
    due_entries = frappe.get_all(
        PAYMENT_ENTRY_DOCTYPE,
        filters={
            "docstatus": 0,
            "payment_type": "Pay",
            WORKFLOW_STATE_FIELD: ["in", PENDING_ESCALATION_STATES],
            APPROVAL_DUE_AT_FIELD: ["<=", now_datetime()],
        },
        pluck="name",
        order_by=f"{APPROVAL_DUE_AT_FIELD} asc, name asc",
        limit=ESCALATION_BATCH_SIZE,
    )

    escalated_count = 0
    failures: list[tuple[str, str]] = []
    for index, payment_entry_name in enumerate(due_entries, start=1):
        savepoint = f"payment_approval_escalation_{index}"
        frappe.db.savepoint(savepoint)
        try:
            if escalate_payment_approval(payment_entry_name):
                escalated_count += 1
        except Exception as exc:
            frappe.db.rollback(save_point=savepoint)
            failures.append((payment_entry_name, f"{type(exc).__name__}: {exc}"))
        finally:
            frappe.db.release_savepoint(savepoint)

    if escalated_count:
        frappe.logger(__name__).info("Escalated %s overdue Payment Entries", escalated_count)
    if failures:
        failure_details = "; ".join(f"{name} ({error})" for name, error in failures)
        frappe.logger(__name__).error(
            "Failed to escalate %s overdue Payment Entries: %s",
            len(failures),
            failure_details,
        )


def escalate_payment_approval(payment_entry_name: str) -> bool:
    locked_entry = frappe.db.get_value(
        PAYMENT_ENTRY_DOCTYPE,
        payment_entry_name,
        ["docstatus", "payment_type", WORKFLOW_STATE_FIELD, APPROVAL_DUE_AT_FIELD],
        as_dict=True,
        for_update=True,
    )
    if not locked_entry or not _is_due_for_escalation(locked_entry):
        return False

    previous_state = cast(str, locked_entry.get(WORKFLOW_STATE_FIELD))
    expected_state = ESCALATED_STATE_BY_PENDING_STATE[previous_state]
    _delete_completed_workflow_actions(payment_entry_name, expected_state)
    frappe.db.set_value(
        PAYMENT_ENTRY_DOCTYPE,
        payment_entry_name,
        WORKFLOW_STATE_FIELD,
        expected_state,
        modified_by="Administrator",
    )
    escalated_entry = cast(Document, frappe.get_doc(PAYMENT_ENTRY_DOCTYPE, payment_entry_name))
    _complete_previous_workflow_action(payment_entry_name, previous_state)
    process_workflow_actions(escalated_entry, "on_update")
    escalated_entry.add_comment(
        "Workflow",
        _("Automatically escalated after the payment approval deadline."),
        comment_email="Administrator",
        comment_by=_("System"),
    )
    escalated_entry.notify_update()

    return True


def _is_due_for_escalation(entry: Any) -> bool:
    if int(entry.get("docstatus") or 0) != 0:
        return False
    if entry.get("payment_type") != "Pay":
        return False
    if entry.get(WORKFLOW_STATE_FIELD) not in PENDING_ESCALATION_STATES:
        return False

    approval_due_at = entry.get(APPROVAL_DUE_AT_FIELD)
    approval_due_datetime = get_datetime(approval_due_at) if approval_due_at else None
    return bool(approval_due_datetime and approval_due_datetime <= now_datetime())


def _complete_previous_workflow_action(payment_entry_name: str, previous_state: str) -> None:
    frappe.db.set_value(
        "Workflow Action",
        {
            "reference_doctype": PAYMENT_ENTRY_DOCTYPE,
            "reference_name": payment_entry_name,
            "workflow_state": previous_state,
            "status": "Open",
        },
        {
            "status": "Completed",
            "completed_by": "Administrator",
            "completed_by_role": ESCALATION_ROLE,
        },
    )


def _delete_completed_workflow_actions(payment_entry_name: str, workflow_state: str) -> None:
    workflow_action_names = frappe.get_all(
        "Workflow Action",
        filters={
            "reference_doctype": PAYMENT_ENTRY_DOCTYPE,
            "reference_name": payment_entry_name,
            "workflow_state": workflow_state,
            "status": "Completed",
        },
        pluck="name",
    )
    for workflow_action_name in workflow_action_names:
        frappe.delete_doc(
            "Workflow Action",
            workflow_action_name,
            force=True,
            ignore_permissions=True,
        )
