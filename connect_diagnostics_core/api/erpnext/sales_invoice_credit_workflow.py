# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Guards and evidence capture for Sales Invoice credit-note approval."""

from __future__ import annotations

from typing import Any

import frappe
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
    get_accounting_dimensions,
)
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.frappe.approval_controls import (
    authorize_approval_field_write,
    authorize_workflow_field_write,
    consume_approval_field_grant,
    critical_digest,
    require_distinct_actors,
    require_permission,
    resolve_user,
)
from connect_diagnostics_core.api.frappe.approval_routes import get_route

ROUTE = "sales_invoice_credit_note"
DIGEST_VERSION = "sales-invoice-credit-note-v1"
APPROVED_STATE = get_route(ROUTE).approved_state
SUBMITTED_STATE = get_route(ROUTE).submitted_state
APPROVAL_FIELDS = frozenset(
    {
        "approval_maker_user",
        "approval_reviewer_user",
        "approval_authorized_user",
        "approval_critical_digest",
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    }
)


def is_credit_note(doc: Document) -> bool:
    """Identify the protected route without trusting source validity as a bypass."""
    if doc.get("doctype") != "Sales Invoice":
        return False
    identity = doc
    if not doc.is_new():
        identity = (
            frappe.db.get_value(
                "Sales Invoice",
                doc.name,
                ["is_return", "return_against"],
                as_dict=True,
            )
            or {}
        )
    return bool(identity.get("is_return") and str(identity.get("return_against") or "").strip())


def _payload(doc: Document) -> dict[str, Any]:
    fields = (
        "is_return",
        "return_against",
        "company",
        "customer",
        "currency",
        "posting_date",
        "set_posting_time",
        "posting_time",
        "due_date",
        "credit_note_reason",
        "conversion_rate",
        "selling_price_list",
        "update_stock",
        "is_pos",
        "allocate_advances_automatically",
        "payment_terms_template",
        "cash_bank_account",
        "change_amount",
        "account_for_change_amount",
        "write_off_amount",
        "write_off_outstanding_amount_automatically",
        "write_off_account",
        "write_off_cost_center",
        "redeem_loyalty_points",
        "loyalty_points",
        "loyalty_amount",
        "coupon_code",
        "apply_discount_on",
        "discount_amount",
        "additional_discount_percentage",
        "grand_total",
        "total_taxes_and_charges",
        "net_total",
    )
    payload: dict[str, Any] = {
        "digest_version": DIGEST_VERSION,
        **{field: doc.get(field) for field in fields},
    }
    for field in ("posting_date", "due_date"):
        if payload[field] is not None:
            payload[field] = str(payload[field])
    if not payload["set_posting_time"]:
        payload["posting_time"] = None
    elif payload["posting_time"] is not None:
        payload["posting_time"] = str(payload["posting_time"])
    dimensions = sorted(str(value) for value in get_accounting_dimensions() or [])
    payload["dimensions"] = {field: doc.get(field) for field in dimensions}
    item_fields = (
        "item_code",
        "qty",
        "uom",
        "rate",
        "amount",
        "warehouse",
        "income_account",
        "cost_center",
        "project",
        "serial_no",
        "batch_no",
        "dn_detail",
        "so_detail",
    )
    payload["items"] = [
        {**{key: row.get(key) for key in item_fields}, **{field: row.get(field) for field in dimensions}}
        for row in doc.get("items", [])
    ]
    tax_fields = (
        "charge_type",
        "row_id",
        "account_head",
        "cost_center",
        "description",
        "included_in_print_rate",
        "included_in_paid_amount",
        "rate",
        "tax_amount",
        "total",
    )
    payload["taxes"] = [
        {**{key: row.get(key) for key in tax_fields}, **{field: row.get(field) for field in dimensions}}
        for row in doc.get("taxes", [])
    ]
    child_fields = {
        "advances": (
            "reference_type",
            "reference_name",
            "reference_row",
            "advance_amount",
            "allocated_amount",
            "exchange_gain_loss",
            "ref_exchange_rate",
            "difference_posting_date",
        ),
        "payment_schedule": (
            "payment_term",
            "due_date",
            "invoice_portion",
            "payment_amount",
            "mode_of_payment",
            "discount_date",
            "discount_type",
            "discount",
        ),
        "payments": (
            "mode_of_payment",
            "amount",
            "account",
            "type",
            "reference_no",
        ),
    }
    for table, table_fields in child_fields.items():
        payload[table] = [{field: row.get(field) for field in table_fields} for row in doc.get(table, [])]
    original = str(doc.get("return_against") or "")
    payload["original"] = (
        dict(
            frappe.db.get_value(
                "Sales Invoice",
                original,
                ["name", "docstatus", "company", "customer", "currency"],
                as_dict=True,
            )
            or {}
        )
        if original
        else {}
    )
    return payload


def critical_payload(doc: Document) -> dict[str, Any]:
    return _payload(doc)


def critical_payload_digest(doc: Document) -> str:
    return critical_digest(_payload(doc))


def _capture(
    doc: Document,
    action: str,
    *,
    protected: bool,
    roles: tuple[str, ...],
    maker: str = "",
    previous: tuple[str, ...] = (),
) -> None:
    route = get_route(ROUTE)
    if protected:
        snapshot = authorize_approval_field_write(doc, ROUTE, action, roles, maker, previous)
        field = "approval_reviewer_user" if action == route.review_action else "approval_authorized_user"
        doc.set(field, snapshot.user)
        prefix = "checked" if action == route.review_action else "authorized"
        doc.set(f"{prefix}_by", snapshot.employee)
        doc.set(f"{prefix}_at", snapshot.acted_at)
        doc.set(f"{prefix}_signature", snapshot.signature)
    else:
        user = authorize_workflow_field_write(doc, ROUTE, action, roles)
        if action == route.send_action:
            doc.set("approval_maker_user", user)
    if action != route.approve_action:
        doc.set("approval_critical_digest", critical_payload_digest(doc))


def capture_maker(doc: Document, method: str | None = None) -> None:
    del method
    if is_credit_note(doc):
        route = get_route(ROUTE)
        _capture(
            doc,
            route.resubmit_action if doc.get("approval_maker_user") else route.send_action,
            protected=False,
            roles=route.maker_roles,
        )


def capture_review(doc: Document, method: str | None = None) -> None:
    del method
    if is_credit_note(doc):
        route = get_route(ROUTE)
        _capture(
            doc,
            route.review_action,
            protected=True,
            roles=route.reviewer_roles,
            maker=str(doc.get("approval_maker_user") or ""),
        )


def capture_approval(doc: Document, method: str | None = None) -> None:
    del method
    if is_credit_note(doc):
        route = get_route(ROUTE)
        if not str(doc.get("approval_critical_digest") or "").strip() or str(
            doc.get("approval_critical_digest")
        ) != critical_payload_digest(doc):
            frappe.throw(_("Credit Note changed after review; resubmit it for review."))
        previous = (str(doc.get("approval_reviewer_user") or ""),)
        _capture(
            doc,
            route.approve_action,
            protected=True,
            roles=route.final_approver_roles,
            maker=str(doc.get("approval_maker_user") or ""),
            previous=previous,
        )


def clear_on_return(doc: Document, method: str | None = None) -> None:
    del method
    if is_credit_note(doc):
        route = get_route(ROUTE)
        authorize_workflow_field_write(doc, ROUTE, route.return_action, route.reviewer_roles)
        for field in APPROVAL_FIELDS - {"approval_maker_user"}:
            doc.set(field, None)


def clear_on_reject(doc: Document, method: str | None = None) -> None:
    del method
    if is_credit_note(doc):
        route = get_route(ROUTE)
        authorize_workflow_field_write(doc, ROUTE, route.reject_action, route.final_approver_roles)
        for field in APPROVAL_FIELDS - {"approval_maker_user"}:
            doc.set(field, None)


def validate_approval_fields(doc: Document, method: str | None = None) -> None:
    del method
    if (
        doc.get("doctype") == "Sales Invoice"
        and doc.get("is_return")
        and not str(doc.get("return_against") or "").strip()
    ):
        frappe.throw(_("Credit Note must reference a submitted Sales Invoice."))
    if not is_credit_note(doc):
        return
    route = get_route(ROUTE)
    if doc.is_new():
        if doc.get("amended_from"):
            doc.set("workflow_state", route.draft_state)
            for field in APPROVAL_FIELDS:
                doc.set(field, None)
        elif any(doc.get(field) for field in APPROVAL_FIELDS):
            frappe.throw(_("New Credit Notes cannot contain pre-existing approval evidence."))
        return
    previous = doc.get_doc_before_save()
    if previous:
        before, after = previous.get("workflow_state"), doc.get("workflow_state")
        action = next(
            (
                a
                for a, old, new in (
                    (route.send_action, route.draft_state, route.pending_review_state),
                    (route.resubmit_action, route.returned_state, route.pending_review_state),
                    (route.review_action, route.pending_review_state, route.reviewed_state),
                    (route.approve_action, route.reviewed_state, route.approved_state),
                    (route.return_action, route.pending_review_state, route.returned_state),
                    (route.reject_action, route.reviewed_state, route.returned_state),
                    (route.execute_action, route.approved_state, route.submitted_state),
                )
                if before == old and after == new
            ),
            None,
        )
        if action:
            changed = {field for field in APPROVAL_FIELDS if doc.get(field) != previous.get(field)}
            allowed = {
                route.send_action: {"approval_maker_user", "approval_critical_digest"},
                route.resubmit_action: {"approval_critical_digest"},
                route.review_action: {
                    "approval_reviewer_user",
                    "approval_critical_digest",
                    "checked_by",
                    "checked_at",
                    "checked_signature",
                },
                route.approve_action: {
                    "approval_authorized_user",
                    "authorized_by",
                    "authorized_at",
                    "authorized_signature",
                },
                route.return_action: APPROVAL_FIELDS - {"approval_maker_user"},
                route.reject_action: APPROVAL_FIELDS - {"approval_maker_user"},
                route.execute_action: set(),
            }[action]
            if not changed.issubset(allowed):
                frappe.throw(_("Approval evidence changed outside the native Workflow action."))
            if action != route.execute_action:
                consume_approval_field_grant(doc, ROUTE, action)
        elif any(doc.get(field) != previous.get(field) for field in APPROVAL_FIELDS):
            frappe.throw(_("Approval evidence may only be changed by a native Workflow action."))


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    del method
    if not is_credit_note(doc):
        return
    route = get_route(ROUTE)
    if doc.get("workflow_state") != SUBMITTED_STATE:
        frappe.throw(_("Credit Notes must be approved through the Sales Invoice Credit Workflow."))
    source_name = str(doc.get("return_against") or "").strip()
    if not source_name:
        frappe.throw(_("Credit Note must reference a submitted Sales Invoice."))
    source = frappe.db.get_value(
        "Sales Invoice",
        source_name,
        ["docstatus", "company", "customer", "currency"],
        as_dict=True,
        for_update=True,
    )
    persisted = frappe.db.get_value(
        "Sales Invoice",
        doc.name,
        [
            "workflow_state",
            "approval_critical_digest",
            "approval_maker_user",
            "approval_reviewer_user",
            "approval_authorized_user",
            "checked_by",
            "checked_at",
            "checked_signature",
            "authorized_by",
            "authorized_at",
            "authorized_signature",
        ],
        as_dict=True,
        for_update=True,
    )
    # Native ERPNext validation remains authoritative for quantities, taxes, and
    # stock. Run it under both locks before comparing approval-critical values
    # because validation may normalize them.
    doc.validate()  # ty: ignore[unresolved-attribute] - ERPNext Sales Invoice controller method
    if not persisted or persisted.workflow_state != APPROVED_STATE:
        frappe.throw(_("Credit Note approval is stale; resubmit the document for review."))
    if (
        not source
        or source.docstatus != 1
        or source.company != doc.get("company")
        or source.customer != doc.get("customer")
        or source.currency != doc.get("currency")
    ):
        frappe.throw(
            _("Credit Note reference must be a submitted Sales Invoice for the same customer and company.")
        )
    for field in (
        "approval_maker_user",
        "approval_reviewer_user",
        "approval_authorized_user",
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    ):
        if not str(doc.get(field) or "").strip() or str(persisted.get(field) or "") != str(
            doc.get(field) or ""
        ):
            frappe.throw(_("Credit Note approval evidence is incomplete or stale."))
    if str(persisted.approval_critical_digest or "") != str(doc.get("approval_critical_digest") or ""):
        frappe.throw(_("Credit Note approval is stale; resubmit the document for review."))
    if str(doc.get("approval_critical_digest") or "") != critical_payload_digest(doc):
        frappe.throw(_("Credit Note approval is stale; resubmit the document for review."))
    maker = resolve_user(str(doc.get("approval_maker_user") or ""))
    reviewer = resolve_user(str(doc.get("approval_reviewer_user") or ""))
    approver = resolve_user(str(doc.get("approval_authorized_user") or ""))
    require_distinct_actors(maker, reviewer, (approver,))
    current_user = resolve_user(str(frappe.session.user or ""))
    if not set(frappe.get_roles(current_user)).intersection(route.execution_roles):
        frappe.throw(_("Only an authorized Sales Manager may post this Credit Note."))
    require_permission(doc, "submit")
    consume_approval_field_grant(doc, ROUTE, route.execute_action)


def authorize_submit_transition(doc: Document, method: str | None = None) -> None:
    del method
    if is_credit_note(doc):
        route = get_route(ROUTE)
        authorize_workflow_field_write(
            doc, ROUTE, route.execute_action, route.execution_roles, permission="submit"
        )


def authorize_cancel_transition(doc: Document, method: str | None = None) -> None:
    del method
    if is_credit_note(doc):
        route = get_route(ROUTE)
        authorize_workflow_field_write(
            doc, ROUTE, route.cancel_action, route.execution_roles, permission="cancel"
        )


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    del method
    if not is_credit_note(doc):
        return
    route = get_route(ROUTE)
    if doc.get("workflow_state") != route.cancelled_state:
        frappe.throw(_("Credit Notes must be cancelled through the Sales Invoice Credit Workflow."))
    persisted_state = frappe.db.get_value("Sales Invoice", doc.name, "workflow_state", for_update=True)
    if persisted_state != route.submitted_state:
        frappe.throw(_("Credit Note cancellation state is stale; reload the document and try again."))
    current_user = resolve_user(str(frappe.session.user or ""))
    if not set(frappe.get_roles(current_user)).intersection(route.execution_roles):
        frappe.throw(_("Only an authorized Sales Manager may cancel this Credit Note."))
    require_permission(doc, "cancel")
    consume_approval_field_grant(doc, ROUTE, route.cancel_action)
