# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Approval boundary for native HRMS Payroll Entry processing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

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
)
from connect_diagnostics_core.api.frappe.approval_routes import get_route

ROUTE = get_route("payroll_entry")
DIGEST_VERSION = "payroll-entry-v1"
EVIDENCE_FIELDS = (
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
)

# These values are intentionally explicit: changing this schema invalidates prior approvals.
CRITICAL_FIELDS: tuple[str, ...] = (
    "company",
    "posting_date",
    "start_date",
    "end_date",
    "payroll_frequency",
    "branch",
    "department",
    "designation",
    "project",
    "currency",
    "exchange_rate",
    "cost_center",
    "bank_account",
    "payment_account",
    "payroll_payable_account",
    "validate_attendance",
    "number_of_employees",
    "grade",
    "deduct_tax_for_unsubmitted_tax_exemption_proof",
    "salary_slip_based_on_timesheet",
    "amended_from",
)


def _payroll_source_revisions(doc: Document | Mapping[str, Any]) -> dict[str, Any]:
    """Fingerprint mutable native sources without persisting private payroll values."""
    employee_names = sorted(
        {str(row.get("employee")) for row in (doc.get("employees") or []) if row.get("employee")}
    )
    if not employee_names:
        return {
            "employees": [],
            "salary_structure_assignments": [],
            "salary_structures": [],
            "income_tax_slabs": [],
            "salary_components": [],
            "payroll_settings_modified": frappe.db.get_single_value("Payroll Settings", "modified"),
        }

    employees = frappe.get_all(
        "Employee",
        filters={"name": ("in", employee_names)},
        fields=["name", "modified", "status", "company", "date_of_joining", "relieving_date"],
        order_by="name asc",
    )
    assignments = frappe.get_all(
        "Salary Structure Assignment",
        filters={
            "employee": ("in", employee_names),
            "docstatus": 1,
            "from_date": ("<=", doc.get("end_date")),
        },
        fields=[
            "name",
            "modified",
            "employee",
            "salary_structure",
            "from_date",
            "company",
            "currency",
            "payroll_payable_account",
            "income_tax_slab",
            "grade",
        ],
        order_by="employee asc, from_date asc, name asc",
    )
    structure_names = sorted(
        {str(row.get("salary_structure")) for row in assignments if row.get("salary_structure")}
    )
    tax_slab_names = sorted(
        {str(row.get("income_tax_slab")) for row in assignments if row.get("income_tax_slab")}
    )
    structures = (
        frappe.get_all(
            "Salary Structure",
            filters={"name": ("in", structure_names)},
            fields=[
                "name",
                "modified",
                "docstatus",
                "is_active",
                "company",
                "currency",
                "payroll_frequency",
                "salary_slip_based_on_timesheet",
            ],
            order_by="name asc",
        )
        if structure_names
        else []
    )
    salary_details = (
        frappe.get_all(
            "Salary Detail",
            filters={"parenttype": "Salary Structure", "parent": ("in", structure_names)},
            fields=["parent", "salary_component"],
            order_by="parent asc, idx asc",
        )
        if structure_names
        else []
    )
    component_names = sorted(
        {str(row.get("salary_component")) for row in salary_details if row.get("salary_component")}
    )
    components = (
        frappe.get_all(
            "Salary Component",
            filters={"name": ("in", component_names)},
            fields=["name", "modified", "disabled", "type"],
            order_by="name asc",
        )
        if component_names
        else []
    )
    tax_slabs = (
        frappe.get_all(
            "Income Tax Slab",
            filters={"name": ("in", tax_slab_names)},
            fields=["name", "modified", "docstatus", "disabled", "currency"],
            order_by="name asc",
        )
        if tax_slab_names
        else []
    )
    return {
        "employees": employees,
        "salary_structure_assignments": assignments,
        "salary_structures": structures,
        "income_tax_slabs": tax_slabs,
        "salary_components": components,
        "payroll_settings_modified": frappe.db.get_single_value("Payroll Settings", "modified"),
    }


def approval_payload(doc: Document | Mapping[str, Any]) -> dict[str, Any]:
    """Build a privacy-preserving, server-read digest payload for the payroll batch."""
    get = doc.get
    payload = {
        "digest_version": DIGEST_VERSION,
        **{field: get(field) for field in CRITICAL_FIELDS},
    }
    for field in sorted(get_accounting_dimensions()):
        payload[field] = get(field)
    employees = get("employees") or []
    payload["employees"] = [
        {
            "name": row.get("name"),
            "employee": row.get("employee"),
            "department": row.get("department"),
            "designation": row.get("designation"),
            "is_salary_withheld": row.get("is_salary_withheld"),
        }
        for row in employees
    ]
    payload["source_revisions"] = _payroll_source_revisions(doc)
    return payload


def get_approval_digest(doc: Document | Mapping[str, Any]) -> str:
    return critical_digest(approval_payload(doc))


def capture_maker_snapshot(doc: Document, method: str | None = None) -> None:
    """Capture the maker when the native Send/Resubmit action begins a review cycle."""
    del method
    action = ROUTE.resubmit_action if doc.get("approval_maker_user") else ROUTE.send_action
    user = authorize_workflow_field_write(doc, ROUTE.key, action, ROUTE.maker_roles)
    if action == ROUTE.send_action:
        doc.set("approval_maker_user", user)


def capture_review_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    snapshot = authorize_approval_field_write(
        doc, ROUTE.key, ROUTE.review_action, ROUTE.reviewer_roles, str(doc.get("approval_maker_user") or "")
    )
    doc.set("approval_reviewer_user", frappe.session.user)
    doc.set("approval_critical_digest", get_approval_digest(doc))
    doc.set("checked_by", snapshot.employee)
    doc.set("checked_at", snapshot.acted_at)
    doc.set("checked_signature", snapshot.signature)


def capture_authorization_snapshot(doc: Document, method: str | None = None) -> None:
    del method
    maker = str(doc.get("approval_maker_user") or "")
    reviewer = str(doc.get("approval_reviewer_user") or "")
    if not reviewer or doc.get("approval_critical_digest") != get_approval_digest(doc):
        frappe.throw(_("Payroll Entry approval is stale; return it for review again."))
    snapshot = authorize_approval_field_write(
        doc, ROUTE.key, ROUTE.approve_action, ROUTE.final_approver_roles, maker, (reviewer,)
    )
    require_distinct_actors(maker, frappe.session.user, (reviewer,))
    doc.set("approval_authorized_user", frappe.session.user)
    doc.set("authorized_by", snapshot.employee)
    doc.set("authorized_at", snapshot.acted_at)
    doc.set("authorized_signature", snapshot.signature)


def _clear_evidence(doc: Document) -> None:
    for field in (
        "approval_reviewer_user",
        "approval_authorized_user",
        "approval_critical_digest",
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    ):
        if doc.meta.has_field(field):
            doc.set(field, None)


def clear_on_return(doc: Document, method: str | None = None) -> None:
    del method
    authorize_workflow_field_write(doc, ROUTE.key, ROUTE.return_action, ROUTE.reviewer_roles)
    _clear_evidence(doc)


def clear_on_reject(doc: Document, method: str | None = None) -> None:
    del method
    authorize_workflow_field_write(doc, ROUTE.key, ROUTE.reject_action, ROUTE.final_approver_roles)
    _clear_evidence(doc)


def clear_approval_snapshots(doc: Document, method: str | None = None) -> None:
    """Backward-compatible alias; transition-specific handlers should be used."""
    del method
    _clear_evidence(doc)


def validate_workflow(doc: Document, method: str | None = None) -> None:
    del method
    previous = doc.get_doc_before_save()
    before = str(previous.get("workflow_state") or "") if previous else ""
    state = str(doc.get("workflow_state") or "")
    transitions = {
        (ROUTE.draft_state, ROUTE.pending_review_state): ROUTE.send_action,
        (ROUTE.returned_state, ROUTE.pending_review_state): ROUTE.resubmit_action,
        (ROUTE.pending_review_state, ROUTE.reviewed_state): ROUTE.review_action,
        (ROUTE.pending_review_state, ROUTE.returned_state): ROUTE.return_action,
        (ROUTE.reviewed_state, ROUTE.returned_state): ROUTE.reject_action,
        (ROUTE.reviewed_state, ROUTE.approved_state): ROUTE.approve_action,
        (ROUTE.approved_state, ROUTE.submitted_state): ROUTE.execute_action,
    }
    action = transitions.get((before, state))
    if action and action != ROUTE.execute_action:
        consume_approval_field_grant(doc, ROUTE.key, action)
    if doc.get("workflow_state") in {ROUTE.reviewed_state, ROUTE.approved_state}:
        if previous and get_approval_digest(previous) != get_approval_digest(doc):
            frappe.throw(_("Payroll Entry critical fields cannot change after review starts."))
    if previous:
        changed = {field for field in EVIDENCE_FIELDS if previous.get(field) != doc.get(field)}
        allowed_by_action: dict[str, set[str]] = {
            ROUTE.send_action: {"approval_maker_user"},
            ROUTE.resubmit_action: set(),
            ROUTE.review_action: {
                "approval_reviewer_user",
                "approval_critical_digest",
                "checked_by",
                "checked_at",
                "checked_signature",
            },
            ROUTE.approve_action: {
                "approval_authorized_user",
                "authorized_by",
                "authorized_at",
                "authorized_signature",
            },
            ROUTE.return_action: set(EVIDENCE_FIELDS) - {"approval_maker_user"},
            ROUTE.reject_action: set(EVIDENCE_FIELDS) - {"approval_maker_user"},
            ROUTE.execute_action: set(),
        }
        allowed = allowed_by_action.get(action or "", set())
        if changed - allowed:
            frappe.throw(_("Payroll Entry approval evidence cannot be changed by this transition."))
        if action in {ROUTE.review_action, ROUTE.approve_action} and get_approval_digest(doc) != doc.get(
            "approval_critical_digest"
        ):
            frappe.throw(_("Payroll Entry approval digest is invalid."))


def authorize_submit_transition(doc: Document, method: str | None = None) -> None:
    del method
    if doc.get("workflow_state") != ROUTE.submitted_state:
        frappe.throw(_("Payroll Entry submission requires the native Workflow action."))
    authorize_workflow_field_write(doc, ROUTE.key, ROUTE.execute_action, ROUTE.execution_roles, "submit")


def _persisted_approval(doc: Document) -> Mapping[str, Any]:
    row = frappe.db.get_value(
        "Payroll Entry",
        doc.name,
        [
            "docstatus",
            "workflow_state",
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
        ],
        as_dict=True,
        for_update=True,
    )
    if not row:
        frappe.throw(_("Payroll Entry approval could not be verified."))
    return cast(Mapping[str, Any], row)


def validate_downstream_operation(
    payroll_entry: str | Document, *, require_current_digest: bool = True
) -> Document:
    """Require durable approval before any native payroll side effect continues."""
    doc = (
        frappe.get_doc("Payroll Entry", payroll_entry, for_update=True)
        if isinstance(payroll_entry, str)
        else payroll_entry
    )
    persisted = _persisted_approval(doc)
    if int(persisted.get("docstatus") or 0) != 1 or persisted.get("workflow_state") != ROUTE.submitted_state:
        frappe.throw(_("Payroll processing requires an approved and submitted Payroll Entry."))
    required = (
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
    )
    if any(not persisted.get(field) for field in required):
        frappe.throw(_("Payroll processing requires complete review and approval evidence."))
    if require_current_digest and persisted.get("approval_critical_digest") != get_approval_digest(doc):
        frappe.throw(_("Payroll Entry approval is stale; return it for review again."))
    return doc


class PayrollEntryApprovalMixin:
    """Guard native HRMS payroll operations without replacing their implementation."""

    def create_salary_slips(self: Any, *args: Any, **kwargs: Any) -> Any:
        validate_downstream_operation(cast(Document, self))
        return super().create_salary_slips(*args, **kwargs)

    def submit_salary_slips(self: Any, *args: Any, **kwargs: Any) -> Any:
        validate_downstream_operation(cast(Document, self))
        return super().submit_salary_slips(*args, **kwargs)

    def make_accrual_jv_entry(self: Any, *args: Any, **kwargs: Any) -> Any:
        validate_downstream_operation(cast(Document, self), require_current_digest=False)
        return super().make_accrual_jv_entry(*args, **kwargs)

    def make_bank_entry(self: Any, *args: Any, **kwargs: Any) -> Any:
        validate_downstream_operation(cast(Document, self), require_current_digest=False)
        return super().make_bank_entry(*args, **kwargs)


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    del method
    consume_approval_field_grant(doc, ROUTE.key, ROUTE.execute_action)
    if doc.get("workflow_state") != ROUTE.submitted_state:
        frappe.throw(_("Payroll Entry must be submitted through its approved Workflow action."))
    require_permission(doc, "submit")
    persisted = _persisted_approval(doc)
    if (
        persisted.get("workflow_state") != ROUTE.approved_state
        or doc.get("workflow_state") != ROUTE.submitted_state
    ):
        frappe.throw(_("Payroll Entry must be approved through the native Workflow before submission."))
    digest = get_approval_digest(doc)
    if persisted.get("approval_critical_digest") != digest or doc.get("approval_critical_digest") != digest:
        frappe.throw(_("Payroll Entry approval is stale; return it for review again."))
    maker = str(persisted.get("approval_maker_user") or "")
    reviewer = str(persisted.get("approval_reviewer_user") or "")
    approver = str(persisted.get("approval_authorized_user") or "")
    require_distinct_actors(maker, reviewer, ())
    require_distinct_actors(maker, approver, (reviewer,))
    for field in (
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    ):
        if not persisted.get(field) or not doc.get(field) or persisted.get(field) != doc.get(field):
            frappe.throw(_("Payroll Entry requires matching signed review and authorization evidence."))
    if any(
        persisted.get(field) != doc.get(field)
        for field in ("approval_maker_user", "approval_reviewer_user", "approval_authorized_user")
    ):
        frappe.throw(_("Payroll Entry approval actors cannot be changed during submission."))
