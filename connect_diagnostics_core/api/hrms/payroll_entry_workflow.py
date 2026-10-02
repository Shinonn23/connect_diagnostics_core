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
from frappe.utils import cast as cast_fieldtype
from frappe.utils import getdate

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
from connect_diagnostics_core.api.hrms import payroll_output_review as output

ROUTE = get_route("payroll_entry")
DIGEST_VERSION = "payroll-entry-v1"
ADDITIONAL_SALARY_FIELDS = (
    "name",
    "modified",
    "employee",
    "company",
    "salary_component",
    "type",
    "amount",
    "docstatus",
    "disabled",
    "is_recurring",
    "from_date",
    "to_date",
    "payroll_date",
    "overwrite_salary_structure_amount",
    "deduct_full_tax_on_selected_payroll_date",
    "ref_doctype",
    "ref_docname",
)
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
    input_sources = lock_payroll_input_sources(doc, employee_names)
    if not employee_names:
        return {
            "employees": [],
            "salary_structure_assignments": [],
            "salary_structures": [],
            "income_tax_slabs": [],
            "salary_components": [],
            **input_sources,
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
        **input_sources,
    }


def _lock_employee_scope(employee_names: list[str]) -> list[frappe._dict]:
    """Acquire the payroll/Additonal Salary mutex in the shared stable order."""
    employees: list[frappe._dict] = []
    for name in sorted(set(employee_names)):
        employee = frappe.db.get_value(
            "Employee", name, ["name", "company"], as_dict=True, for_update=True, wait=False
        )
        if not employee:
            frappe.throw(_("Payroll Employee master is missing or locked for update."))
        employees.append(cast(frappe._dict, employee))
    return employees


def _eligible_additional_salary(row: Mapping[str, Any], start_date: Any, end_date: Any) -> bool:
    if int(row.get("docstatus") or 0) != 1 or int(row.get("disabled") or 0):
        return False
    if row.get("type") not in {"Earning", "Deduction"}:
        return False
    period_end = getdate(end_date)
    period_start = getdate(start_date)
    if period_start is None or period_end is None:
        return False
    if int(row.get("is_recurring") or 0):
        from_date = getdate(row.get("from_date"))
        to_date = getdate(row.get("to_date"))
        return (
            from_date is not None
            and to_date is not None
            and from_date <= period_end
            and to_date >= period_end
        )
    payroll_date = getdate(row.get("payroll_date"))
    return payroll_date is not None and period_start <= payroll_date <= period_end


def _locked_payroll_settings() -> list[frappe._dict]:
    rows = frappe.qb.get_query(
        table="Singles",
        filters={"doctype": "Payroll Settings"},
        fields=["field", "value"],
        order_by="field asc",
        for_update=True,
        wait=False,
    ).run(as_dict=True)
    return cast(list[frappe._dict], rows)


def lock_payroll_input_sources(
    doc: Document | Mapping[str, Any], employee_names: list[str] | None = None
) -> dict[str, Any]:
    """Lock current Employee, Additional Salary and Payroll Settings source rows.

    Hooks on Additional Salary writes call ``guard_additional_salary_employee_scope`` so
    inserts, reassignment and eligibility edits serialize on the same Employee rows.
    """
    if employee_names is None:
        employee_names = sorted(
            {str(row.get("employee")) for row in (doc.get("employees") or []) if row.get("employee")}
        )
    employee_names = sorted(set(employee_names))
    employees = _lock_employee_scope(employee_names)
    if len(employees) != len(employee_names):
        frappe.throw(_("Payroll Employee scope could not be locked."))
    salary_rows = (
        frappe.db.get_values(
            "Additional Salary",
            {"employee": ("in", employee_names)},
            list(ADDITIONAL_SALARY_FIELDS),
            as_dict=True,
            order_by="name asc",
            for_update=True,
            wait=False,
        )
        if employee_names
        else []
    )
    eligible = [
        dict(row)
        for row in salary_rows
        if _eligible_additional_salary(row, doc.get("start_date"), doc.get("end_date"))
    ]
    settings = _locked_payroll_settings()
    settings_digest = critical_digest(
        {"settings": [{"field": row.field, "value": row.value} for row in settings]}
    )
    return {
        "additional_salaries": eligible,
        "payroll_settings_digest": settings_digest,
    }


def guard_additional_salary_employee_scope(doc: Document, method: str | None = None) -> None:
    """Serialize supported Additional Salary writes with each affected payroll roster.

    Register on Additional Salary before_insert, before_update, before_submit and
    before_cancel. On reassignment, both the persisted and proposed Employee mutexes
    are acquired in name order before the native document can be written.
    """
    del method
    proposed = str(doc.get("employee") or "")
    old_employee = None
    if doc.name and frappe.db.exists("Additional Salary", doc.name):
        old_employee = frappe.db.get_value("Additional Salary", doc.name, "employee")
    names = sorted({name for name in (str(old_employee or ""), proposed) if name})
    _lock_employee_scope(names)
    if old_employee:
        persisted = frappe.db.get_value(
            "Additional Salary", doc.name, "employee", for_update=True, wait=False
        )
        if persisted != old_employee:
            frappe.throw(_("Additional Salary Employee changed concurrently; retry the update."))


def verify_native_payroll_input_readers(doc: Document | Mapping[str, Any]) -> None:
    """Require HRMS ordinary readers to match the locked-current payroll sources."""
    sources = lock_payroll_input_sources(doc)
    from hrms.payroll.doctype.additional_salary.additional_salary import get_additional_salaries

    rows = {str(row.get("name")): row for row in sources["additional_salaries"]}
    employee_names = sorted(
        {str(row.get("employee")) for row in (doc.get("employees") or []) if row.get("employee")}
    )
    native_fields = (
        "name",
        "component",
        "type",
        "amount",
        "is_recurring",
        "overwrite",
        "deduct_full_tax_on_selected_payroll_date",
        "ref_doctype",
    )
    for employee in employee_names:
        for component_type in ("earnings", "deductions"):
            expected = [
                {
                    "name": row["name"],
                    "component": row["salary_component"],
                    "type": row["type"],
                    "amount": row["amount"],
                    "is_recurring": row["is_recurring"],
                    "overwrite": row["overwrite_salary_structure_amount"],
                    "deduct_full_tax_on_selected_payroll_date": row[
                        "deduct_full_tax_on_selected_payroll_date"
                    ],
                    "ref_doctype": row["ref_doctype"],
                }
                for row in rows.values()
                if row["employee"] == employee
                and row["type"] == ("Earning" if component_type == "earnings" else "Deduction")
            ]
            native = get_additional_salaries(
                employee, doc.get("start_date"), doc.get("end_date"), component_type
            )
            actual = [
                {field: row.get(field) for field in native_fields}
                for row in sorted(native, key=lambda item: str(item.get("name") or ""))
            ]
            if sorted(expected, key=lambda item: str(item.get("name") or "")) != actual:
                frappe.throw(_("Additional Salary inputs changed in the active transaction; retry payroll."))

    _verify_native_payroll_settings(sources["payroll_settings_digest"])


def _verify_native_payroll_settings(expected_digest: str) -> None:
    """Compare cached HRMS Settings readers with the locked-current Singles digest."""
    frappe.clear_document_cache("Payroll Settings", "Payroll Settings")
    frappe.db.value_cache.pop("Payroll Settings", None)
    settings = frappe.get_cached_doc("Payroll Settings", "Payroll Settings")
    meta = frappe.get_meta("Payroll Settings")
    native_projection = {
        str(field.fieldname): settings.get(field.fieldname) for field in meta.fields if field.fieldname
    }
    current = _locked_payroll_settings()
    current_map = {str(row.field): row.value for row in current}
    source_projection = {
        str(field.fieldname): cast_fieldtype(
            str(field.fieldtype), current_map.get(str(field.fieldname), field.default)
        )
        for field in meta.fields
        if field.fieldname
    }
    if critical_digest(source_projection) != critical_digest(native_projection):
        frappe.throw(_("Payroll Settings changed in the active transaction; retry payroll."))
    if (
        critical_digest({"settings": [{"field": row.field, "value": row.value} for row in current]})
        != expected_digest
    ):
        frappe.throw(_("Payroll Settings changed after Payroll Entry review."))


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
    source = _locked_transition_source(doc, ROUTE.returned_state)
    if source == ROUTE.pending_review_state:
        roles = ROUTE.reviewer_roles
    elif source == ROUTE.reviewed_state:
        roles = ROUTE.final_approver_roles
    else:
        frappe.throw(_("Payroll Entry cannot be returned from its current state."))
    authorize_workflow_field_write(doc, ROUTE.key, ROUTE.return_action, roles)
    _clear_evidence(doc)


def clear_on_reject(doc: Document, method: str | None = None) -> None:
    del method
    if _locked_transition_source(doc, "Payroll Entry Rejected") != ROUTE.reviewed_state:
        frappe.throw(_("Payroll Entry rejection requires the Reviewed state."))
    authorize_workflow_field_write(doc, ROUTE.key, ROUTE.reject_action, ROUTE.final_approver_roles)
    _clear_evidence(doc)


def _locked_transition_source(doc: Document, target: str) -> str:
    if not doc.name or doc.get("workflow_state") != target:
        frappe.throw(_("Payroll Entry has an invalid Return or Reject target."))
    persisted = frappe.db.get_value(
        "Payroll Entry", doc.name, ["docstatus", "workflow_state"], as_dict=True, for_update=True
    )
    if not persisted or persisted.get("docstatus") != 0:
        frappe.throw(_("Payroll Entry Return or Reject requires a saved draft."))
    return str(persisted.get("workflow_state") or "")


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
        (ROUTE.reviewed_state, ROUTE.returned_state): ROUTE.return_action,
        (ROUTE.reviewed_state, "Payroll Entry Rejected"): ROUTE.reject_action,
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
    if int(persisted.get("docstatus") or 0) != 1 or persisted.get("workflow_state") not in {
        ROUTE.submitted_state,
        output.REVIEWED,
        output.CLOSED,
    }:
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
    maker = resolve_user(str(persisted.get("approval_maker_user") or ""))
    reviewer = resolve_user(str(persisted.get("approval_reviewer_user") or ""))
    approver = resolve_user(str(persisted.get("approval_authorized_user") or ""))
    if len({maker, reviewer, approver}) != 3:
        frappe.throw(_("Payroll approval actors must be independent Users."))
    if require_current_digest and persisted.get("approval_critical_digest") != get_approval_digest(doc):
        frappe.throw(_("Payroll Entry approval is stale; return it for review again."))
    return doc


class PayrollEntryApprovalMixin:
    """Guard native HRMS payroll operations without replacing their implementation."""

    @frappe.whitelist()
    def create_salary_slips(self: Any, *args: Any, **kwargs: Any) -> Any:
        return output.create_salary_slips(cast(Document, self), *args, **kwargs)

    @frappe.whitelist()
    def submit_salary_slips(self: Any, *args: Any, **kwargs: Any) -> Any:
        return output.submit_salary_slips(cast(Document, self), *args, **kwargs)

    def make_accrual_jv_entry(self: Any, *args: Any, **kwargs: Any) -> Any:
        validate_downstream_operation(cast(Document, self), require_current_digest=False)
        current = output.locked_payroll_entry(str(self.name))
        output.require_current_payroll_fields(cast(Document, self), current)
        output.require_output_review(
            current, allow_queued=output.native_operation_kind(str(self.name)) == "submit"
        )
        if output.native_operation_kind(str(self.name)) != "submit":
            raise frappe.PermissionError(_("Payroll accrual requires the reviewed native Salary Slip batch."))
        result = super().make_accrual_jv_entry(*args, **kwargs)
        output.require_output_review(
            output.locked_payroll_entry(str(self.name)),
            allow_queued=output.native_operation_kind(str(self.name)) == "submit",
        )
        return result

    @frappe.whitelist()
    def make_bank_entry(self: Any, *args: Any, **kwargs: Any) -> Any:
        validate_downstream_operation(cast(Document, self), require_current_digest=False)
        for_withheld = bool(args[0]) if args else bool(kwargs.get("for_withheld_salaries", False))
        current = output.locked_payroll_entry(str(self.name))
        output.require_current_payroll_fields(cast(Document, self), current)
        _slips, expected = output.preflight_bank(current, for_withheld)
        with output.native_operation(str(self.name), "bank_withheld" if for_withheld else "bank_regular"):
            result = super().make_bank_entry(*args, **kwargs)
        output.validate_bank_candidate(current, result, for_withheld, expected)
        return result

    def cancel(self: Any) -> None:
        # Native HRMS queues >50 Slips, which loses apply_workflow's object-bound grant.
        self._cancel()


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


_OUTPUT_ACTIONS: dict[tuple[str, str], str] = {
    (output.SUBMITTED, output.REVIEWED): "Review Calculated Payroll",
    (output.REVIEWED, output.SUBMITTED): "Reopen Payroll Output",
    (output.REVIEWED, output.CLOSED): "Close Payroll",
    (output.CLOSED, output.REVIEWED): "Reopen Payroll Accounting",
}


def _prepare_output_transition(doc: Document, source: str, target: str, action: str) -> Document:
    if not doc.name or doc.get("workflow_state") != target:
        frappe.throw(_("Payroll output Workflow target is invalid."))
    pe = output.locked_payroll_entry(str(doc.name))
    if int(pe.docstatus or 0) != 1 or pe.get("workflow_state") != source:
        frappe.throw(_("Payroll output Workflow source has changed."))
    if action == "Review Calculated Payroll":
        version = pe.get("output_review_version")
        if version in (None, ""):
            # Legacy SHA-256 evidence fingerprints historical inputs; it is not a
            # signature over today's mutable payroll sources.
            validate_downstream_operation(pe, require_current_digest=False)
        elif version == output.VERSION:
            validate_downstream_operation(pe, require_current_digest=True)
        else:
            frappe.throw(_("Payroll calculated output review version is unknown."))
        snapshot = authorize_approval_field_write(
            doc, ROUTE.key, action, ("HR Manager",), str(pe.get("approval_maker_user") or "")
        )
        output.seal_output_review(doc, output.current_roster(pe), snapshot.user)
    else:
        validate_downstream_operation(pe, require_current_digest=False)
        authorize_workflow_field_write(doc, ROUTE.key, action, ("HR Manager",))
        if action == "Reopen Payroll Output":
            output.clear_output_review(doc)
        elif action == "Close Payroll":
            output.require_complete_accounting(pe)
        else:
            output.require_output_review(pe)
    return pe


def prepare_output_review(doc: Document, method: str | None = None) -> None:
    del method
    _prepare_output_transition(doc, output.SUBMITTED, output.REVIEWED, "Review Calculated Payroll")


def prepare_output_reopen(doc: Document, method: str | None = None) -> None:
    del method
    _prepare_output_transition(doc, output.REVIEWED, output.SUBMITTED, "Reopen Payroll Output")


def prepare_payroll_close(doc: Document, method: str | None = None) -> None:
    del method
    _prepare_output_transition(doc, output.REVIEWED, output.CLOSED, "Close Payroll")


def prepare_accounting_reopen(doc: Document, method: str | None = None) -> None:
    del method
    _prepare_output_transition(doc, output.CLOSED, output.REVIEWED, "Reopen Payroll Accounting")


def prepare_payroll_cancel(doc: Document, method: str | None = None) -> None:
    del method
    if doc.get("workflow_state") != output.CANCELLED:
        frappe.throw(_("Payroll cancellation requires the native Workflow target."))
    pe = output.locked_payroll_entry(str(doc.name))
    if int(pe.docstatus or 0) != 1 or pe.get("workflow_state") not in {
        output.SUBMITTED,
        output.REVIEWED,
        output.CLOSED,
    }:
        frappe.throw(_("Payroll cancellation source has changed."))
    validate_downstream_operation(pe, require_current_digest=False)
    output.current_roster(pe, complete=False)
    authorize_workflow_field_write(doc, ROUTE.key, "Cancel Payroll Entry", ("HR Manager",), "cancel")
    output.require_cancellable_accounting(pe)


def validate_before_update_after_submit(doc: Document, method: str | None = None) -> None:
    del method
    previous = doc.get_doc_before_save()
    if not previous or int(previous.docstatus or 0) != 1 or int(doc.docstatus or 0) != 1:
        frappe.throw(_("Payroll submitted history cannot be verified."))
    before = str(previous.get("workflow_state") or "")
    target = str(doc.get("workflow_state") or "")
    action = _OUTPUT_ACTIONS.get((before, target))
    if before != target and not action:
        frappe.throw(_("Payroll output Workflow transition is invalid."))
    changed = {field for field in output.OUTPUT_FIELDS if previous.get(field) != doc.get(field)}
    if action:
        consume_approval_field_grant(doc, ROUTE.key, action)
        pe = output.locked_payroll_entry(str(doc.name))
        if pe.get("workflow_state") != before:
            frappe.throw(_("Payroll output Workflow source has changed."))
        allowed = {
            "Review Calculated Payroll": set(output.OUTPUT_FIELDS),
            "Reopen Payroll Output": set(output.OUTPUT_FIELDS),
            "Close Payroll": set(),
            "Reopen Payroll Accounting": set(),
        }[action]
        if changed - allowed:
            frappe.throw(_("Payroll output evidence cannot change in this transition."))
        if action == "Review Calculated Payroll":
            if not changed or doc.get("output_review_version") != output.VERSION:
                frappe.throw(_("Payroll calculated output review was not captured."))
            output.require_sealed_candidate(doc, pe)
        elif action == "Reopen Payroll Output":
            cleared_fields = tuple(
                field for field in output.OUTPUT_FIELDS[:-1] if field != "output_review_version"
            )
            if (
                any(doc.get(field) for field in cleared_fields)
                or previous.get("output_review_version") != output.VERSION
                or doc.get("output_review_version") != output.VERSION
            ):
                frappe.throw(_("Payroll calculated output review was not cleared."))
            if (
                int(doc.get("output_review_revision") or 0)
                != int(previous.get("output_review_revision") or 0) + 1
            ):
                frappe.throw(_("Payroll calculated output review revision was not advanced."))
        elif action == "Close Payroll":
            output.require_complete_accounting(pe)
        else:
            output.require_output_review(pe)
    elif changed:
        frappe.throw(_("Payroll output evidence cannot be changed directly."))
    if any(previous.get(field) != doc.get(field) for field in (*CRITICAL_FIELDS, *EVIDENCE_FIELDS)):
        frappe.throw(_("Submitted Payroll Entry approved fields cannot be changed."))


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    del method
    consume_approval_field_grant(doc, ROUTE.key, "Cancel Payroll Entry")
    if doc.get("workflow_state") != output.CANCELLED:
        frappe.throw(_("Payroll Entry must be cancelled through its Workflow action."))
    pe = output.locked_payroll_entry(str(doc.name))
    if int(pe.docstatus or 0) != 1 or pe.get("workflow_state") not in {
        output.SUBMITTED,
        output.REVIEWED,
        output.CLOSED,
    }:
        frappe.throw(_("Payroll Entry cancellation source has changed."))
    output.require_cancellable_accounting(pe)


class PayrollEntryWorkflowMixin:
    """Keep HRMS accrual Journal Entry generation in draft status."""

    def make_journal_entry(self: Any, *args: Any, **kwargs: Any) -> Any:
        # HRMS uses this flag only for its direct submit. Native construction and
        # Salary Slip linking remain in the superclass.
        if len(args) >= 7:
            args = (*args[:6], False, *args[7:])
        else:
            kwargs["submit_journal_entry"] = False
        kind = output.native_operation_kind(str(self.name))
        if kind not in {"submit", "bank_regular", "bank_withheld"}:
            raise frappe.PermissionError(_("Payroll Journal Entry requires a reviewed native operation."))
        result = super().make_journal_entry(*args, **kwargs)
        if kind == "submit":
            submitted = kwargs.get("submitted_salary_slips") or (args[5] if len(args) > 5 else None)
            if not submitted:
                raise frappe.PermissionError(_("Payroll accrual requires submitted Salary Slips."))
            output.validate_accrual_candidate(cast(Document, self), cast(Document, result), submitted)
        return result
