# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Disposable, fail-closed Payment Entry approval proof of concept for local.test."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any, NoReturn, cast

import frappe
from frappe import _
from frappe.model.document import Document

ENABLED_SITE = "local.test"
ENABLED_FLAG = "connect_diagnostics_payment_entry_poc_enabled"
PAYMENT_TYPE = "Pay"
MAKER_ROLE = "Accounts User"
CHECKER_ROLE = "Accounts Manager"
APPROVER_ROLE = "C-Level Approver"

DRAFT = "Payment Entry Draft"
PENDING_CHECK = "Payment Entry Pending Check"
PENDING_APPROVAL = "Payment Entry Pending Approval"
APPROVED = "Payment Entry Approved"
REJECTED = "Payment Entry Rejected"
SUBMITTED = "Payment Entry Submitted"

CHECK_TOKEN_PREFIX = "[PAYMENT_ENTRY_POC_CHECK_V1] "
APPROVAL_TOKEN_PREFIX = "[PAYMENT_ENTRY_POC_APPROVAL_V1] "

CRITICAL_FIELDS = (
    "payment_type",
    "company",
    "party_type",
    "party",
    "posting_date",
    "paid_from",
    "paid_to",
    "paid_from_account_currency",
    "paid_to_account_currency",
    "paid_amount",
    "received_amount",
    "source_exchange_rate",
    "target_exchange_rate",
    "reference_no",
    "reference_date",
    "cost_center",
    "project",
    "references",
    "deductions",
    "taxes",
)
VOLATILE_CHILD_KEYS = frozenset(
    {
        "name",
        "idx",
        "creation",
        "modified",
        "owner",
        "modified_by",
        "parent",
        "parentfield",
        "parenttype",
        "doctype",
        "docstatus",
    }
)
ROLE_FIELDS = {
    "maker": ("submit_by", "submit_at", "submit_signature"),
    "checker": ("checked_by", "checked_at", "checked_signature"),
    "approver": ("authorized_by", "authorized_at", "authorized_signature"),
}
ROLE_REQUIREMENTS = {
    "maker": MAKER_ROLE,
    "checker": CHECKER_ROLE,
    "approver": APPROVER_ROLE,
}
TRANSITIONS = {
    (DRAFT, PENDING_CHECK): "maker",
    (PENDING_CHECK, PENDING_APPROVAL): "checker",
    (PENDING_APPROVAL, APPROVED): "approver",
    (APPROVED, SUBMITTED): "submit",
    (PENDING_CHECK, DRAFT): "checker_return",
    (PENDING_APPROVAL, REJECTED): "approver_reject",
    (REJECTED, PENDING_CHECK): "maker",
}
SNAPSHOT_FIELDS = tuple(field for fields in ROLE_FIELDS.values() for field in fields)


def enabled() -> bool:
    """Return whether this disposable adapter is enabled for the current site."""
    if getattr(frappe.local, "site", None) != ENABLED_SITE:
        return False
    try:
        configured = frappe.conf[ENABLED_FLAG]
    except (KeyError, TypeError):
        return False
    return type(configured) is int and configured == 1


def _value(doc: Document | dict[str, Any], fieldname: str) -> Any:
    return doc.get(fieldname)


def _canonical(value: Any) -> Any:
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value) if key not in VOLATILE_CHILD_KEYS}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float, Decimal)):
        return format(Decimal(str(value)).normalize(), "f")
    return str(value)


def canonical_payload(doc: Document | dict[str, Any]) -> dict[str, Any]:
    """Return deterministic posting-critical Payment Entry data."""
    fieldnames = list(CRITICAL_FIELDS)
    if isinstance(doc, Document):
        from connect_diagnostics_core.api.erpnext.payment_entry import (
            get_active_accounting_dimension_fieldnames,
        )

        fieldnames.extend(get_active_accounting_dimension_fieldnames())
    return {fieldname: _canonical(_value(doc, fieldname)) for fieldname in dict.fromkeys(fieldnames)}


def posting_digest(doc: Document | dict[str, Any]) -> str:
    payload = json.dumps(
        canonical_payload(doc),
        default=str,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _throw(message: str) -> NoReturn:
    frappe.throw(_(message))
    raise AssertionError("frappe.throw returned unexpectedly")


def _site_signing_key() -> bytes:
    try:
        key = frappe.conf["encryption_key"]
    except (KeyError, TypeError):
        key = None
    if not isinstance(key, str) or not key:
        _throw("The site encryption key is required for Payment Entry approval evidence.")
    return cast(str, key).encode()


def _employee_for_user(user: str) -> dict[str, Any] | None:
    rows = frappe.get_all(
        "Employee",
        filters={"user_id": user, "status": "Active"},
        fields=["name", "user_id", "approval_signature"],
        limit=2,
    )
    if len(rows) != 1:
        return None
    return cast(dict[str, Any], rows[0])


def _snapshot(doc: Document, role: str) -> dict[str, str]:
    employee_field, at_field, signature_field = ROLE_FIELDS[role]
    employee_name = str(doc.get(employee_field) or "")
    action_at = str(doc.get(at_field) or "")
    signature = str(doc.get(signature_field) or "")
    if not employee_name or not action_at or not signature:
        _throw("Complete Maker, Checker, and Approver snapshots are required.")
    user = frappe.db.get_value(
        "Employee",
        {"name": employee_name, "status": "Active"},
        "user_id",
    )
    if not user:
        _throw("Every approval snapshot must reference an active Employee linked to a User.")
    return {
        "employee": employee_name,
        "user": str(user),
        "at": action_at,
        "signature_sha256": hashlib.sha256(signature.encode()).hexdigest(),
    }


def _token_payload(doc: Document, stage: str) -> dict[str, Any]:
    roles = ("maker", "checker") if stage == "check" else ("maker", "checker", "approver")
    return {
        "version": 1,
        "stage": stage,
        "doctype": doc.doctype,
        "name": doc.name,
        "posting_payload": canonical_payload(doc),
        "posting_digest": posting_digest(doc),
        "actors": {role: _snapshot(doc, role) for role in roles},
    }


def _encode_token(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    encoded = base64.urlsafe_b64encode(serialized).decode()
    signature = hmac.new(_site_signing_key(), serialized, hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _decode_token(token: str) -> dict[str, Any]:
    try:
        encoded, supplied_signature = token.split(".", 1)
        serialized = base64.urlsafe_b64decode(encoded.encode())
        expected_signature = hmac.new(_site_signing_key(), serialized, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError
        payload = json.loads(serialized)
    except (ValueError, TypeError, json.JSONDecodeError):
        _throw("Payment Entry approval evidence is malformed or has been tampered with.")
    if not isinstance(payload, dict):
        _throw("Payment Entry approval evidence is malformed or has been tampered with.")
    return cast(dict[str, Any], payload)


def _token_prefix(stage: str) -> str:
    return CHECK_TOKEN_PREFIX if stage == "check" else APPROVAL_TOKEN_PREFIX


def _store_token(doc: Document, stage: str) -> None:
    doc.add_comment("Info", text=_token_prefix(stage) + _encode_token(_token_payload(doc, stage)))


def _verify_token(doc: Document, stage: str) -> None:
    expected = _token_payload(doc, stage)
    actor_role = "checker" if stage == "check" else "approver"
    expected_owner = expected["actors"][actor_role]["user"]
    prefix = _token_prefix(stage)
    rows = frappe.get_all(
        "Comment",
        filters={
            "reference_doctype": doc.doctype,
            "reference_name": doc.name,
            "comment_type": "Info",
            "content": ["like", f"{prefix}%"],
        },
        fields=["owner", "content"],
        order_by="creation asc",
    )
    matches = 0
    for row in rows:
        content = str(row.get("content") or "")
        if not content.startswith(prefix):
            continue
        payload = _decode_token(content[len(prefix) :].strip())
        if payload == expected:
            if row.get("owner") != expected_owner:
                _throw("Payment Entry approval evidence has the wrong owner.")
            matches += 1
    if matches != 1:
        _throw("Exactly one current Payment Entry approval evidence token is required.")


def _clear_snapshots(doc: Document, roles: tuple[str, ...] = ("maker", "checker", "approver")) -> None:
    for role in roles:
        for fieldname in ROLE_FIELDS[role]:
            doc.set(fieldname, None)


def _capture_actor(doc: Document, role: str) -> None:
    user = frappe.session.user
    required_role = ROLE_REQUIREMENTS[role]
    if required_role not in frappe.get_roles(user):
        _throw(f"Only {required_role} may perform the {role} transition.")
    employee = _employee_for_user(user)
    if not employee or not employee.get("approval_signature"):
        _throw("The acting user must have one active Employee with an approval signature.")

    existing_employees = {
        str(doc.get(ROLE_FIELDS[other][0]))
        for other in ROLE_FIELDS
        if other != role and doc.get(ROLE_FIELDS[other][0])
    }
    existing_users = {
        str(frappe.db.get_value("Employee", employee_name, "user_id") or "")
        for employee_name in existing_employees
    }
    if str(employee["name"]) in existing_employees or user in existing_users:
        _throw("Maker, Checker, and Approver must be different Employees and Users.")

    employee_field, at_field, signature_field = ROLE_FIELDS[role]
    doc.set(employee_field, employee["name"])
    doc.set(at_field, frappe.utils.now())
    doc.set(signature_field, employee["approval_signature"])


def _require_role(role: str) -> None:
    if role not in frappe.get_roles(frappe.session.user):
        _throw(f"Only {role} may perform this Payment Entry transition.")


def _transition(doc: Document, role: str, expected: str, new: str) -> None:
    if not enabled():
        return
    if doc.get("payment_type") != PAYMENT_TYPE:
        _throw("The Payment Entry approval proof of concept supports Pay only.")
    old = frappe.db.get_value("Payment Entry", doc.name, "workflow_state")
    if old != expected or doc.get("workflow_state") != new:
        _throw("The Payment Entry workflow transition is not authoritative.")

    if role == "maker":
        _clear_snapshots(doc)
        _capture_actor(doc, "maker")
    elif role == "checker":
        _clear_snapshots(doc, ("checker", "approver"))
        _capture_actor(doc, "checker")
        _store_token(doc, "check")
    elif role == "approver":
        _verify_token(doc, "check")
        _clear_snapshots(doc, ("approver",))
        _capture_actor(doc, "approver")
        _store_token(doc, "approval")
    elif role == "submit":
        _require_role(CHECKER_ROLE)
    elif role == "checker_return":
        _require_role(CHECKER_ROLE)
        _clear_snapshots(doc, ("checker", "approver"))
    elif role == "approver_reject":
        _require_role(APPROVER_ROLE)
        _clear_snapshots(doc, ("approver",))
    doc.flags.poc_payment_entry_transition = (expected, new, role)


def capture_maker(doc: Document) -> None:
    _transition(doc, "maker", DRAFT, PENDING_CHECK)


def capture_checker(doc: Document) -> None:
    _transition(doc, "checker", PENDING_CHECK, PENDING_APPROVAL)


def capture_approver(doc: Document) -> None:
    _transition(doc, "approver", PENDING_APPROVAL, APPROVED)


def authorize_submit(doc: Document) -> None:
    _transition(doc, "submit", APPROVED, SUBMITTED)


def return_to_draft(doc: Document) -> None:
    _transition(doc, "checker_return", PENDING_CHECK, DRAFT)


def reject(doc: Document) -> None:
    _transition(doc, "approver_reject", PENDING_APPROVAL, REJECTED)


def validate(doc: Document, method: str | None = None) -> None:
    del method
    if not enabled() or doc.doctype != "Payment Entry":
        return
    if doc.get("payment_type") != PAYMENT_TYPE:
        _throw("The Payment Entry approval proof of concept supports Pay only.")

    previous = (
        frappe.db.get_value("Payment Entry", doc.name, ["workflow_state"], as_dict=True) if doc.name else None
    )
    old_state = cast(str | None, previous.get("workflow_state") if previous else None)
    state = cast(str | None, doc.get("workflow_state"))
    if state == old_state:
        if state in {PENDING_APPROVAL, APPROVED}:
            stage = "check" if state == PENDING_APPROVAL else "approval"
            try:
                _verify_token(doc, stage)
            except frappe.ValidationError:
                _clear_snapshots(doc)
                doc.set("workflow_state", DRAFT)
        return
    if (old_state, state) == (None, DRAFT):
        return

    role = TRANSITIONS.get((old_state, state)) if old_state and state else None
    marker = getattr(doc.flags, "poc_payment_entry_transition", None)
    if role is None or marker != (old_state, state, role):
        _throw("Payment Entry state changes must use the approved workflow transition.")


def before_submit(doc: Document, method: str | None = None) -> None:
    del method
    if not enabled() or doc.doctype != "Payment Entry":
        return
    if doc.get("payment_type") != PAYMENT_TYPE:
        _throw("The Payment Entry approval proof of concept supports Pay only.")

    fields = ["workflow_state", "docstatus", *SNAPSHOT_FIELDS]
    row = frappe.db.get_value(
        "Payment Entry",
        doc.name,
        fields,
        as_dict=True,
        for_update=True,
    )
    marker = getattr(doc.flags, "poc_payment_entry_transition", None)
    if (
        not row
        or row.workflow_state != APPROVED
        or row.docstatus != 0
        or doc.get("workflow_state") != SUBMITTED
        or marker != (APPROVED, SUBMITTED, "submit")
    ):
        _throw("Payment Entry must have an approved database workflow state before submission.")

    for fieldname in SNAPSHOT_FIELDS:
        if row.get(fieldname) != doc.get(fieldname):
            _throw("Payment Entry approval snapshots do not match the database record.")
    if len({row.submit_by, row.checked_by, row.authorized_by}) != 3:
        _throw("Maker, Checker, and Approver must be different Employees.")
    if not all((row.submit_signature, row.checked_signature, row.authorized_signature)):
        _throw("Complete Maker, Checker, and Approver signatures are required.")

    checker = _employee_for_user(frappe.session.user)
    if (
        CHECKER_ROLE not in frappe.get_roles(frappe.session.user)
        or not checker
        or checker["name"] != row.checked_by
    ):
        _throw("Only the recorded Checker may submit this Payment Entry.")
    _verify_token(doc, "approval")
