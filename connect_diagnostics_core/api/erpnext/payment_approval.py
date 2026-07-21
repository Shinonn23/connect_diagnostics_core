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
    BASE_GRAND_TOTAL_FIELD,
    CANCELLED_STATE,
    ESCALATED_LOW_VALUE_STATE,
    ESCALATED_PRIMARY_STATE,
    ESCALATION_ROLE,
    LOW_VALUE_APPROVER_ROLE,
    LOW_VALUE_PAYMENT_APPROVAL_LIMIT_FIELD,
    PAYMENT_APPROVAL_LIMIT_FIELD,
    PAYMENT_REQUEST_DOCTYPE,
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
PRIMARY_APPROVAL_STATES = frozenset(
    {
        PENDING_PRIMARY_STATE,
        ESCALATED_PRIMARY_STATE,
    }
)
APPROVAL_EDIT_ROLES_BY_STATE = {
    PENDING_LOW_VALUE_STATE: frozenset({LOW_VALUE_APPROVER_ROLE}),
    PENDING_PRIMARY_STATE: frozenset({PRIMARY_APPROVER_ROLE}),
    ESCALATED_LOW_VALUE_STATE: frozenset({LOW_VALUE_APPROVER_ROLE, SECONDARY_APPROVER_ROLE}),
    ESCALATED_PRIMARY_STATE: frozenset({PRIMARY_APPROVER_ROLE, SECONDARY_APPROVER_ROLE}),
}

PAYMENT_REQUEST_LOCK_FIELDS = (
    "docstatus",
    "payment_request_type",
    "company",
    "party_type",
    "party",
    "reference_doctype",
    "reference_name",
    "outstanding_amount",
    WORKFLOW_STATE_FIELD,
)


def validate_payment_request_before_submit(doc: Document, _method: str) -> None:
    previous_doc = _get_previous_doc(doc)
    _validate_payment_request_fields(doc, previous_doc)

    payment_request_type = cast(str, doc.get("payment_request_type") or "")
    approval_state = cast(str, doc.get(WORKFLOW_STATE_FIELD) or "")
    if payment_request_type != "Outward":
        _validate_inward_submitter()
        return

    if approval_state != APPROVED_STATE:
        frappe.throw(
            _(
                "Outward Payment Request must be approved through the payment approval workflow "
                "before submission."
            ),
            title=_("Payment approval required"),
        )


def validate_payment_request_transition(doc: Document, _method: str) -> None:
    _validate_payment_request_fields(doc, _get_previous_doc(doc))


def validate_payment_entry_before_submit(doc: Document, _method: str) -> None:
    if doc.get("payment_type") != "Pay":
        return

    allocated_rows = _get_allocated_reference_rows(doc)
    if not allocated_rows:
        frappe.throw(
            _("Outgoing Payment Entry must allocate its full amount to at least one reference."),
            title=_("Payment Request required"),
        )

    unallocated_precision = doc.precision("unallocated_amount")
    if flt(doc.get("unallocated_amount"), unallocated_precision) != 0:
        frappe.throw(
            _("Outgoing Payment Entry must have zero unallocated amount before submission."),
            title=_("Full allocation required"),
        )

    allocation_by_request: dict[str, float] = {}
    for row in allocated_rows:
        payment_request_name = cast(str, row.get("payment_request") or "")
        if not payment_request_name:
            frappe.throw(
                _("Row {0}: Every allocated reference must have a Payment Request.").format(row.idx),
                title=_("Payment Request required"),
            )
        allocation_by_request[payment_request_name] = allocation_by_request.get(
            payment_request_name, 0.0
        ) + abs(flt(row.get("allocated_amount"), row.precision("allocated_amount")))

    locked_requests = _lock_payment_requests(tuple(sorted(allocation_by_request)))
    for row in allocated_rows:
        payment_request_name = cast(str, row.get("payment_request"))
        _validate_payment_request_matches_reference(
            doc,
            row,
            payment_request_name,
            locked_requests[payment_request_name],
        )

    outstanding_precision = frappe.get_precision(PAYMENT_REQUEST_DOCTYPE, "outstanding_amount")
    for payment_request_name, allocated_amount in allocation_by_request.items():
        outstanding_amount = flt(
            locked_requests[payment_request_name].get("outstanding_amount"),
            outstanding_precision,
        )
        if outstanding_amount <= 0 or flt(allocated_amount, outstanding_precision) > outstanding_amount:
            frappe.throw(
                _("Allocated amount exceeds the remaining amount of Payment Request {0}.").format(
                    frappe.bold(payment_request_name)
                ),
                title=_("Payment Request amount exceeded"),
            )


def set_cancelled_workflow_state(doc: Document, _method: str) -> None:
    doc.set(WORKFLOW_STATE_FIELD, CANCELLED_STATE)


def validate_before_discard(doc: Document, _method: str) -> None:
    approval_state = cast(str, doc.get(WORKFLOW_STATE_FIELD) or "")
    if doc.get("payment_request_type") != "Outward" or approval_state not in ACTIONABLE_WORKFLOW_STATES:
        return
    frappe.throw(
        _(
            "An Outward Payment Request in the approval workflow cannot be discarded. "
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
    payment_request_name = cast(str, doc.get("name") or "")
    if (
        not payment_request_name
        or previous_state == next_state
        or next_state not in ACTIONABLE_WORKFLOW_STATES
    ):
        return

    _delete_completed_workflow_actions(payment_request_name, next_state)


def _validate_payment_request_fields(doc: Document, previous_doc: Document | None) -> None:
    if doc.get("payment_request_type") != "Outward":
        previous_state = cast(str, previous_doc.get(WORKFLOW_STATE_FIELD) or "") if previous_doc else ""
        if previous_state in APPROVAL_DECISION_STATES:
            frappe.throw(
                _("Payment Request type cannot change while payment approval is pending."),
                title=_("Payment Request type cannot be changed"),
            )
        return

    _validate_creator_unchanged(doc, previous_doc)
    _maintain_base_grand_total(doc, previous_doc)
    _validate_workflow_state_write_access(doc, previous_doc)
    _maintain_approval_snapshot(doc, previous_doc)
    _maintain_approval_deadline(doc, previous_doc)
    _validate_approval_route(doc)
    _validate_approval_decision(doc, previous_doc)


def _get_previous_doc(doc: Document) -> Document | None:
    get_doc_before_save = getattr(doc, "get_doc_before_save", None)
    if not callable(get_doc_before_save):
        return None
    return cast(Document | None, get_doc_before_save())


def _maintain_base_grand_total(doc: Document, previous_doc: Document | None) -> None:
    expected_base_grand_total = _calculate_base_grand_total(doc)
    previous_state = cast(str, previous_doc.get(WORKFLOW_STATE_FIELD) or "") if previous_doc else ""

    if previous_doc and previous_state in APPROVAL_DECISION_STATES:
        previous_base_grand_total = flt(
            previous_doc.get(BASE_GRAND_TOTAL_FIELD),
            doc.precision(BASE_GRAND_TOTAL_FIELD),
        )
        current_base_grand_total = flt(
            doc.get(BASE_GRAND_TOTAL_FIELD),
            doc.precision(BASE_GRAND_TOTAL_FIELD),
        )
        if (
            current_base_grand_total != previous_base_grand_total
            or expected_base_grand_total != previous_base_grand_total
        ):
            frappe.throw(
                _(
                    "The company-currency amount of a Payment Request cannot change while approval "
                    "is pending."
                ),
                title=_("Payment approval amount cannot be changed"),
            )

    doc.set(BASE_GRAND_TOTAL_FIELD, expected_base_grand_total)


def _calculate_base_grand_total(doc: Document) -> float:
    company = cast(str, doc.get("company") or "")
    currency = cast(str, doc.get("currency") or "")
    reference_doctype = cast(str, doc.get("reference_doctype") or "")
    reference_name = cast(str, doc.get("reference_name") or "")
    if not company or not currency or not reference_doctype or not reference_name:
        frappe.throw(
            _("Company, currency, and reference document are required for payment approval."),
            title=_("Payment approval amount unavailable"),
        )

    company_currency = cast(
        str,
        frappe.get_cached_value("Company", company, "default_currency") or "",
    )
    if not company_currency:
        frappe.throw(
            _("Company {0} must have a default currency.").format(frappe.bold(company)),
            title=_("Company currency required"),
        )

    reference_meta = frappe.get_meta(reference_doctype)
    reference_fields = [
        fieldname
        for fieldname in ("company", "currency", "conversion_rate")
        if reference_meta.has_field(fieldname)
    ]
    reference = frappe.db.get_value(
        reference_doctype,
        reference_name,
        reference_fields,
        as_dict=True,
    )
    if not reference:
        frappe.throw(
            _("Reference document {0} {1} does not exist.").format(
                frappe.bold(reference_doctype), frappe.bold(reference_name)
            ),
            title=_("Invalid payment reference"),
        )

    reference_company = cast(str, reference.get("company") or "")
    if reference_company and reference_company != company:
        frappe.throw(
            _("Payment Request company must match its reference document."),
            title=_("Company mismatch"),
        )
    reference_currency = cast(str, reference.get("currency") or "")
    if reference_currency and reference_currency != currency:
        frappe.throw(
            _("Payment Request currency must match its reference document."),
            title=_("Currency mismatch"),
        )

    conversion_rate = 1.0
    if currency != company_currency:
        conversion_rate = flt(reference.get("conversion_rate"))
        if conversion_rate <= 0:
            frappe.throw(
                _(
                    "Reference document {0} {1} must have a positive conversion rate for payment approval."
                ).format(frappe.bold(reference_doctype), frappe.bold(reference_name)),
                title=_("Conversion rate required"),
            )

    precision = doc.precision(BASE_GRAND_TOTAL_FIELD)
    return flt(flt(doc.get("grand_total")) * conversion_rate, precision)


def _maintain_approval_snapshot(doc: Document, previous_doc: Document | None) -> None:
    next_state = cast(str, doc.get(WORKFLOW_STATE_FIELD) or "")
    previous_state = cast(str, previous_doc.get(WORKFLOW_STATE_FIELD) or "") if previous_doc else ""

    if next_state in PENDING_ESCALATION_STATES and previous_state != next_state:
        limit = frappe.db.get_value(
            "Company",
            doc.get("company"),
            LOW_VALUE_PAYMENT_APPROVAL_LIMIT_FIELD,
        )
        doc.set(
            PAYMENT_APPROVAL_LIMIT_FIELD,
            flt(limit, doc.precision(PAYMENT_APPROVAL_LIMIT_FIELD)),
        )
        return

    if not previous_doc:
        doc.set(PAYMENT_APPROVAL_LIMIT_FIELD, None)
        return

    current_limit = doc.get(PAYMENT_APPROVAL_LIMIT_FIELD)
    previous_limit = previous_doc.get(PAYMENT_APPROVAL_LIMIT_FIELD)
    if _same_currency(current_limit, previous_limit, doc.precision(PAYMENT_APPROVAL_LIMIT_FIELD)):
        return
    frappe.throw(
        _("The payment approval limit snapshot is managed by the system and cannot be changed."),
        title=_("Payment approval limit cannot be changed"),
    )


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
    if not _state_matches_snapshot(doc, previous_state):
        frappe.throw(
            _("Payment Request amount does not match its approval limit snapshot."),
            title=_("Invalid payment approval route"),
        )

    if frappe.session.user != "Administrator" and doc.get("owner") == frappe.session.user:
        frappe.throw(
            _("You cannot approve or reject a Payment Request that you created."),
            title=_("Self approval is not allowed"),
        )

    if doc.get("payment_request_type") != "Outward":
        frappe.throw(
            _("Only Outward Payment Requests can use the payment approval states."),
            title=_("Invalid payment approval transition"),
        )


def _validate_creator_unchanged(doc: Document, previous_doc: Document | None) -> None:
    if not previous_doc or doc.get("owner") == previous_doc.get("owner"):
        return
    frappe.throw(
        _("The creator of a Payment Request cannot be changed."),
        title=_("Payment Request creator cannot be changed"),
    )


def _validate_workflow_state_write_access(doc: Document, previous_doc: Document | None) -> None:
    if not previous_doc or frappe.session.user == "Administrator" or bool(doc.flags.ignore_permissions):
        return

    roles = set(frappe.get_roles())
    previous_state = cast(str, previous_doc.get(WORKFLOW_STATE_FIELD) or "")
    allowed_roles = set(APPROVAL_EDIT_ROLES_BY_STATE.get(previous_state, ()))

    if previous_state in APPROVAL_DECISION_STATES:
        if doc.get("payment_request_type") != "Outward" or not _state_matches_snapshot(doc, previous_state):
            allowed_roles.clear()

        if allowed_roles.intersection(roles):
            return
        frappe.throw(
            _("You cannot edit this Payment Request in its current payment approval state."),
            title=_("Payment approval role required"),
        )

    if PAYMENT_APPROVER_ROLES.intersection(roles) and not ACCOUNTING_ROLES.intersection(roles):
        frappe.throw(
            _("Payment approver roles do not grant general Payment Request editing access."),
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


def _validate_approval_route(doc: Document) -> None:
    state = cast(str, doc.get(WORKFLOW_STATE_FIELD) or "")
    if state not in APPROVAL_DECISION_STATES:
        return
    if doc.get("payment_request_type") != "Outward" or not _state_matches_snapshot(doc, state):
        frappe.throw(
            _("Payment Request approval state does not match its approval limit snapshot."),
            title=_("Invalid payment approval route"),
        )


def _state_matches_snapshot(doc: Document, state: str) -> bool:
    precision = doc.precision(BASE_GRAND_TOTAL_FIELD)
    base_grand_total = flt(doc.get(BASE_GRAND_TOTAL_FIELD), precision)
    payment_approval_limit = flt(doc.get(PAYMENT_APPROVAL_LIMIT_FIELD), precision)
    is_low_value = payment_approval_limit > 0 and base_grand_total < payment_approval_limit
    return (state in LOW_VALUE_APPROVAL_STATES and is_low_value) or (
        state in PRIMARY_APPROVAL_STATES and not is_low_value
    )


def _same_datetime(first: Any, second: Any) -> bool:
    if not first and not second:
        return True
    if not first or not second:
        return False
    return get_datetime(first) == get_datetime(second)


def _same_currency(first: Any, second: Any, precision: int | None) -> bool:
    if not first and not second:
        return True
    return flt(first, precision) == flt(second, precision)


def _validate_inward_submitter() -> None:
    if frappe.session.user == "Administrator":
        return
    roles = set(frappe.get_roles())
    if not PAYMENT_APPROVER_ROLES.intersection(roles) or "Accounts Manager" in roles:
        return
    frappe.throw(
        _("Payment approver roles do not grant permission to submit an Inward Payment Request."),
        title=_("Accounts Manager role required"),
    )


def _get_allocated_reference_rows(doc: Document) -> list[Document]:
    allocated_rows: list[Document] = []
    for row in cast(list[Document], doc.get("references") or []):
        precision = row.precision("allocated_amount")
        if flt(row.get("allocated_amount"), precision) != 0:
            allocated_rows.append(row)
    return allocated_rows


def _lock_payment_requests(payment_request_names: tuple[str, ...]) -> dict[str, Any]:
    locked_requests: dict[str, Any] = {}
    for payment_request_name in payment_request_names:
        payment_request = frappe.db.get_value(
            PAYMENT_REQUEST_DOCTYPE,
            payment_request_name,
            list(PAYMENT_REQUEST_LOCK_FIELDS),
            as_dict=True,
            for_update=True,
        )
        if not payment_request:
            frappe.throw(
                _("Payment Request {0} does not exist.").format(frappe.bold(payment_request_name)),
                title=_("Invalid Payment Request"),
            )
        locked_requests[payment_request_name] = payment_request
    return locked_requests


def _validate_payment_request_matches_reference(
    payment_entry: Document,
    reference_row: Document,
    payment_request_name: str,
    payment_request: Any,
) -> None:
    if payment_request.get("payment_request_type") != "Outward":
        _throw_reference_mismatch(reference_row, payment_request_name, "must be Outward")
    if int(payment_request.get("docstatus") or 0) != 1:
        _throw_reference_mismatch(reference_row, payment_request_name, "must be submitted")
    if payment_request.get(WORKFLOW_STATE_FIELD) != APPROVED_STATE:
        _throw_reference_mismatch(reference_row, payment_request_name, "must be approved")

    expected_values = {
        "company": payment_entry.get("company"),
        "party_type": payment_entry.get("party_type"),
        "party": payment_entry.get("party"),
        "reference_doctype": reference_row.get("reference_doctype"),
        "reference_name": reference_row.get("reference_name"),
    }
    for fieldname, expected_value in expected_values.items():
        if payment_request.get(fieldname) != expected_value:
            _throw_reference_mismatch(
                reference_row,
                payment_request_name,
                _("has a different {0}").format(fieldname.replace("_", " ")),
            )


def _throw_reference_mismatch(
    reference_row: Document,
    payment_request_name: str,
    reason: str,
) -> None:
    frappe.throw(
        _("Row {0}: Payment Request {1} {2}.").format(
            reference_row.idx,
            frappe.bold(payment_request_name),
            reason,
        ),
        title=_("Invalid Payment Request"),
    )


def escalate_due_payment_approvals() -> None:
    due_requests = frappe.get_all(
        PAYMENT_REQUEST_DOCTYPE,
        filters={
            "docstatus": 0,
            "payment_request_type": "Outward",
            WORKFLOW_STATE_FIELD: ["in", PENDING_ESCALATION_STATES],
            APPROVAL_DUE_AT_FIELD: ["<=", now_datetime()],
        },
        pluck="name",
        order_by=f"{APPROVAL_DUE_AT_FIELD} asc, name asc",
        limit=ESCALATION_BATCH_SIZE,
    )

    escalated_count = 0
    failures: list[tuple[str, str]] = []
    for index, payment_request_name in enumerate(due_requests, start=1):
        savepoint = f"payment_approval_escalation_{index}"
        frappe.db.savepoint(savepoint)
        try:
            if escalate_payment_approval(payment_request_name):
                escalated_count += 1
        except Exception as exc:
            frappe.db.rollback(save_point=savepoint)
            failures.append((payment_request_name, f"{type(exc).__name__}: {exc}"))
        finally:
            frappe.db.release_savepoint(savepoint)

    if escalated_count:
        frappe.logger(__name__).info("Escalated %s overdue Payment Requests", escalated_count)
    if failures:
        failure_details = "; ".join(f"{name} ({error})" for name, error in failures)
        frappe.logger(__name__).error(
            "Failed to escalate %s overdue Payment Requests: %s",
            len(failures),
            failure_details,
        )


def escalate_payment_approval(payment_request_name: str) -> bool:
    locked_request = frappe.db.get_value(
        PAYMENT_REQUEST_DOCTYPE,
        payment_request_name,
        ["docstatus", "payment_request_type", WORKFLOW_STATE_FIELD, APPROVAL_DUE_AT_FIELD],
        as_dict=True,
        for_update=True,
    )
    if not locked_request or not _is_due_for_escalation(locked_request):
        return False

    previous_state = cast(str, locked_request.get(WORKFLOW_STATE_FIELD))
    expected_state = ESCALATED_STATE_BY_PENDING_STATE[previous_state]
    _delete_completed_workflow_actions(payment_request_name, expected_state)
    frappe.db.set_value(
        PAYMENT_REQUEST_DOCTYPE,
        payment_request_name,
        WORKFLOW_STATE_FIELD,
        expected_state,
        modified_by="Administrator",
    )
    escalated_request = cast(Document, frappe.get_doc(PAYMENT_REQUEST_DOCTYPE, payment_request_name))
    _complete_previous_workflow_action(payment_request_name, previous_state)
    process_workflow_actions(escalated_request, "on_update")
    escalated_request.add_comment(
        "Workflow",
        _("Automatically escalated after the payment approval deadline."),
        comment_email="Administrator",
        comment_by=_("System"),
    )
    escalated_request.notify_update()

    return True


def _is_due_for_escalation(payment_request: Any) -> bool:
    if int(payment_request.get("docstatus") or 0) != 0:
        return False
    if payment_request.get("payment_request_type") != "Outward":
        return False
    if payment_request.get(WORKFLOW_STATE_FIELD) not in PENDING_ESCALATION_STATES:
        return False

    approval_due_at = payment_request.get(APPROVAL_DUE_AT_FIELD)
    approval_due_datetime = get_datetime(approval_due_at) if approval_due_at else None
    return bool(approval_due_datetime and approval_due_datetime <= now_datetime())


def _complete_previous_workflow_action(payment_request_name: str, previous_state: str) -> None:
    frappe.db.set_value(
        "Workflow Action",
        {
            "reference_doctype": PAYMENT_REQUEST_DOCTYPE,
            "reference_name": payment_request_name,
            "workflow_state": previous_state,
            "status": "Open",
        },
        {
            "status": "Completed",
            "completed_by": "Administrator",
            "completed_by_role": ESCALATION_ROLE,
        },
    )


def _delete_completed_workflow_actions(payment_request_name: str, workflow_state: str) -> None:
    workflow_action_names = frappe.get_all(
        "Workflow Action",
        filters={
            "reference_doctype": PAYMENT_REQUEST_DOCTYPE,
            "reference_name": payment_request_name,
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
