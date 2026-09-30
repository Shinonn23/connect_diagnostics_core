# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Install the approved Payroll Entry Workflow after a fail-closed preflight."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import setup_custom_perms

from connect_diagnostics_core.setup.print_action_fields import CUSTOM_FIELDS as PRINT_FIELDS
from connect_diagnostics_core.setup.workflow_fields import CUSTOM_FIELDS as WORKFLOW_FIELDS

WORKFLOW = "Connect Payroll Entry Blueprint"
DOCTYPE = "Payroll Entry"
TASKS = {
    "Connect Payroll Entry Maker Snapshot": "Capture Payroll Entry Maker",
    "Connect Payroll Entry Review Snapshot": "Capture Payroll Entry Review",
    "Connect Payroll Entry Approval Snapshot": "Capture Payroll Entry Approval",
    "Connect Payroll Entry Return Reset": "Reset Payroll Entry Review",
    "Connect Payroll Entry Reject Reset": "Reset Payroll Entry Approval",
    "Connect Payroll Entry Submit Authorization": "Authorize Payroll Entry Submit Transition",
}
PAYROLL_JOB_NAMES = (
    "hrms.payroll.doctype.payroll_entry.payroll_entry.create_salary_slips_for_employees",
    "hrms.payroll.doctype.payroll_entry.payroll_entry.submit_salary_slips_for_employees",
)
PERMISSION_FIELDS = (
    "read",
    "write",
    "create",
    "delete",
    "submit",
    "cancel",
    "amend",
    "report",
    "export",
    "share",
    "print",
    "email",
)
PAYROLL_ENTRY_PERMISSIONS = {
    "HR User": {"read": 1, "write": 1, "create": 1},
    "Accounts Manager": {"read": 1, "write": 1},
}

_STATE_KEYS = ("allow_edit", "doc_status", "state")
_TRANSITION_KEYS = (
    "action",
    "allow_self_approval",
    "allowed",
    "condition",
    "next_state",
    "state",
    "transition_tasks",
)
_WORKFLOW_KEYS = (
    "workflow_name",
    "document_type",
    "is_active",
    "workflow_state_field",
    "enable_action_confirmation",
    "override_status",
    "send_email_alert",
    "workflow_data",
    "states",
    "transitions",
)
_FIELD_VALUE_KEYS = ("fieldname", "label", "fieldtype", "options")
_FIELD_FLAG_KEYS = (
    "hidden",
    "read_only",
    "allow_on_submit",
    "no_copy",
    "ignore_user_permissions",
    "is_system_generated",
)

LEGACY_WORKFLOW: dict[str, Any] = {
    "doctype": "Workflow",
    "name": WORKFLOW,
    "workflow_name": WORKFLOW,
    "document_type": DOCTYPE,
    "is_active": 1,
    "workflow_state_field": "workflow_state",
    "enable_action_confirmation": 0,
    "override_status": 0,
    "send_email_alert": 0,
    "workflow_data": None,
    "states": [
        {"allow_edit": "HR User", "doc_status": "0", "state": "Payroll Entry Draft"},
        {"allow_edit": "HR User", "doc_status": "0", "state": "Payroll Entry Pending Review"},
        {"allow_edit": "HR Manager", "doc_status": "0", "state": "Payroll Entry Approved"},
        {"allow_edit": "HR User", "doc_status": "0", "state": "Payroll Entry Rejected"},
        {"allow_edit": "HR Manager", "doc_status": "1", "state": "Payroll Entry Submitted"},
        {"allow_edit": "HR Manager", "doc_status": "2", "state": "Payroll Entry Cancelled"},
    ],
    "transitions": [
        {
            "action": "Submit Payroll Entry for Review",
            "allow_self_approval": 0,
            "allowed": "HR User",
            "condition": None,
            "state": "Payroll Entry Draft",
            "next_state": "Payroll Entry Pending Review",
            "transition_tasks": None,
        },
        {
            "action": "Approve Payroll Entry",
            "allow_self_approval": 0,
            "allowed": "HR Manager",
            "condition": None,
            "state": "Payroll Entry Pending Review",
            "next_state": "Payroll Entry Approved",
            "transition_tasks": None,
        },
        {
            "action": "Reject Payroll Entry",
            "allow_self_approval": 0,
            "allowed": "HR Manager",
            "condition": None,
            "state": "Payroll Entry Pending Review",
            "next_state": "Payroll Entry Rejected",
            "transition_tasks": None,
        },
        {
            "action": "Post Payroll Entry",
            "allow_self_approval": 0,
            "allowed": "HR Manager",
            "condition": None,
            "state": "Payroll Entry Approved",
            "next_state": "Payroll Entry Submitted",
            "transition_tasks": None,
        },
        {
            "action": "Cancel Payroll Entry",
            "allow_self_approval": 0,
            "allowed": "HR Manager",
            "condition": None,
            "state": "Payroll Entry Submitted",
            "next_state": "Payroll Entry Cancelled",
            "transition_tasks": None,
        },
    ],
}


def _fixture(filename: str) -> list[dict[str, Any]]:
    path = Path(frappe.get_app_path("connect_diagnostics_core", "fixtures", filename))
    return json.loads(path.read_text(encoding="utf-8"))


def _desired_workflow() -> dict[str, Any]:
    return next(row for row in _fixture("workflow.json") if row["name"] == WORKFLOW)


def _value(record: Any, fieldname: str) -> Any:
    if isinstance(record, dict):
        return record.get(fieldname)
    getter = getattr(record, "get", None)
    return getter(fieldname) if callable(getter) else getattr(record, fieldname, None)


def _flag(record: Any, fieldname: str) -> int:
    return int(_value(record, fieldname) or 0)


def _workflow_shape(record: Any) -> dict[str, Any]:
    return {
        "workflow_name": _value(record, "workflow_name"),
        "document_type": _value(record, "document_type"),
        "is_active": _flag(record, "is_active"),
        "workflow_state_field": _value(record, "workflow_state_field"),
        "enable_action_confirmation": _flag(record, "enable_action_confirmation"),
        "override_status": _flag(record, "override_status"),
        "send_email_alert": _flag(record, "send_email_alert"),
        "workflow_data": _value(record, "workflow_data"),
        "states": [
            tuple(_value(row, key) for key in _STATE_KEYS) for row in (_value(record, "states") or [])
        ],
        "transitions": [
            tuple(
                _flag(row, key) if key == "allow_self_approval" else _value(row, key)
                for key in _TRANSITION_KEYS
            )
            for row in (_value(record, "transitions") or [])
        ],
    }


def _desired_masters(filename: str, names: set[str]) -> dict[str, dict[str, Any]]:
    return {row["name"]: row for row in _fixture(filename) if row["name"] in names}


def _state_records() -> dict[str, dict[str, Any]]:
    return _desired_masters("workflow_state.json", {row["state"] for row in _desired_workflow()["states"]})


def _action_records() -> dict[str, dict[str, Any]]:
    return _desired_masters(
        "workflow_action_master.json",
        {row["action"] for row in _desired_workflow()["transitions"]},
    )


def _master_shape(doctype: str, record: Any) -> tuple[Any, ...]:
    if doctype == "Workflow State":
        return (
            _value(record, "workflow_state_name"),
            _value(record, "style"),
            _value(record, "icon") or None,
            _flag(record, "docstatus"),
        )
    return (_value(record, "workflow_action_name"), _flag(record, "docstatus"))


def _task_shape(record: Any) -> list[tuple[str | None, int, int]]:
    return [
        (_value(row, "task"), _flag(row, "enabled"), _flag(row, "asynchronous"))
        for row in (_value(record, "tasks") or [])
    ]


def _fields() -> list[dict[str, Any]]:
    return [*WORKFLOW_FIELDS[DOCTYPE], *PRINT_FIELDS[DOCTYPE]]


def _field_shape(record: Any) -> tuple[Any, ...]:
    return tuple(_value(record, key) for key in _FIELD_VALUE_KEYS) + tuple(
        _flag(record, key) for key in _FIELD_FLAG_KEYS
    )


def _custom_field(fieldname: str) -> Any | None:
    return frappe.db.get_value(
        "Custom Field",
        {"dt": DOCTYPE, "fieldname": fieldname},
        [*_FIELD_VALUE_KEYS, *_FIELD_FLAG_KEYS],
        as_dict=True,
    )


def _workflow_mode() -> str:
    if not frappe.db.exists("Workflow", WORKFLOW):
        return "absent"
    current = _workflow_shape(frappe.get_doc("Workflow", WORKFLOW))
    legacy_signed = deepcopy(LEGACY_WORKFLOW)
    legacy_signed["transitions"][1]["transition_tasks"] = "Connect Signed Approval Snapshot"
    if current in (_workflow_shape(LEGACY_WORKFLOW), _workflow_shape(legacy_signed)):
        return "legacy"
    if current == _workflow_shape(_desired_workflow()):
        return "desired"
    frappe.throw(_("Payroll Entry approval Workflow conflicts with the approved configuration."))
    raise AssertionError("frappe.throw must raise")


def _validate_masters(doctype: str, records: dict[str, dict[str, Any]]) -> None:
    for name, expected in records.items():
        if not frappe.db.exists(doctype, name):
            continue
        if _master_shape(doctype, frappe.get_doc(doctype, name)) != _master_shape(doctype, expected):
            frappe.throw(_("{0} {1} conflicts with the Payroll Entry route.").format(doctype, name))


def _validate_tasks() -> None:
    for name, task in TASKS.items():
        if not frappe.db.exists("Workflow Transition Tasks", name):
            continue
        if _task_shape(frappe.get_doc("Workflow Transition Tasks", name)) != [(task, 1, 0)]:
            frappe.throw(
                _("Workflow Transition Tasks {0} conflicts with the Payroll Entry route.").format(name)
            )


def _validate_fields() -> None:
    for expected in _fields():
        fieldname = str(expected["fieldname"])
        actual = _custom_field(fieldname)
        if not actual:
            continue
        actual_shape = _field_shape(actual)
        expected_shape = _field_shape(expected)
        legacy_shape = (*expected_shape[:-2], 0, expected_shape[-1])
        if actual_shape not in {expected_shape, legacy_shape}:
            frappe.throw(
                _("Custom Field Payroll Entry-{0} conflicts with the approved route.").format(fieldname)
            )


def _permission_values(role: str) -> dict[str, int]:
    desired = PAYROLL_ENTRY_PERMISSIONS[role]
    return {fieldname: desired.get(fieldname, 0) for fieldname in PERMISSION_FIELDS}


def _permission_rows(role: str) -> list[Any]:
    return frappe.get_all(
        "Custom DocPerm",
        filters={"parent": DOCTYPE, "role": role, "permlevel": 0, "if_owner": 0},
        fields=["name", *PERMISSION_FIELDS],
        order_by="creation asc",
    )


def _validate_permissions(mode: str) -> None:
    for role in PAYROLL_ENTRY_PERMISSIONS:
        rows = _permission_rows(role)
        if len(rows) > 1:
            frappe.throw(_("Payroll Entry permission for {0} has duplicate site-owned rows.").format(role))
        if not rows:
            continue
        if any(_flag(rows[0], fieldname) != value for fieldname, value in _permission_values(role).items()):
            frappe.throw(
                _("Payroll Entry permission for {0} conflicts with the approved route.").format(role)
            )
        if mode != "desired":
            frappe.throw(
                _("Payroll Entry permission for {0} requires owner disposition before migration.").format(
                    role
                )
            )


def _preflight() -> str:
    active = frappe.get_all("Workflow", filters={"document_type": DOCTYPE, "is_active": 1}, pluck="name")
    if any(name != WORKFLOW for name in active):
        frappe.throw(_("Payroll Entry approval migration found another active Workflow."))
    mode = _workflow_mode()
    _validate_masters("Workflow State", _state_records())
    _validate_masters("Workflow Action Master", _action_records())
    _validate_tasks()
    _validate_fields()
    _validate_permissions(mode)
    if frappe.get_all("Workflow Action", filters={"reference_doctype": DOCTYPE, "status": "Open"}, limit=1):
        frappe.throw(_("Payroll Entry approval migration cannot run with open Workflow Actions."))
    if frappe.get_all(DOCTYPE, filters={"docstatus": ("<", 2)}, fields=["name", "docstatus"], limit=1):
        frappe.throw(
            _("Payroll Entry approval migration requires owner disposition for active payroll records.")
        )
    if frappe.get_all(
        "RQ Job",
        filters={
            "status": ("in", ("queued", "started", "deferred")),
            "job_name": ("in", PAYROLL_JOB_NAMES),
        },
        limit=1,
    ):
        frappe.throw(_("Payroll Entry approval migration cannot run while payroll jobs are active."))
    return mode


def _ensure_masters(doctype: str, records: dict[str, dict[str, Any]]) -> None:
    for name, record in records.items():
        if not frappe.db.exists(doctype, name):
            frappe.get_doc(record).insert(ignore_permissions=True)


def _ensure_tasks() -> None:
    for name, task in TASKS.items():
        if not frappe.db.exists("Workflow Transition Tasks", name):
            frappe.get_doc(
                {
                    "doctype": "Workflow Transition Tasks",
                    "name": name,
                    "tasks": [{"task": task, "enabled": 1, "asynchronous": 0}],
                }
            ).insert(ignore_permissions=True)


def _ensure_fields() -> None:
    create_custom_fields({DOCTYPE: _fields()}, update=True, ignore_validate=True)


def _ensure_permissions() -> None:
    setup_custom_perms(DOCTYPE)
    for role in PAYROLL_ENTRY_PERMISSIONS:
        if _permission_rows(role):
            continue
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": DOCTYPE,
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role,
                "permlevel": 0,
                "if_owner": 0,
                **_permission_values(role),
            }
        ).insert(ignore_permissions=True)
    frappe.clear_cache(doctype=DOCTYPE)


def _remove_permissions() -> None:
    managed: list[str] = []
    for role in PAYROLL_ENTRY_PERMISSIONS:
        rows = _permission_rows(role)
        if len(rows) != 1 or any(
            _flag(rows[0], fieldname) != value for fieldname, value in _permission_values(role).items()
        ):
            frappe.throw(_("Payroll Entry permission for {0} cannot be rolled back safely.").format(role))
        managed.append(str(_value(rows[0], "name")))
    for name in managed:
        frappe.delete_doc("Custom DocPerm", name, force=True, ignore_permissions=True)
    frappe.clear_cache(doctype=DOCTYPE)


def _replace_workflow(record: dict[str, Any]) -> None:
    if frappe.db.exists("Workflow", WORKFLOW):
        workflow = frappe.get_doc("Workflow", WORKFLOW)
        workflow.update({key: record.get(key) for key in _WORKFLOW_KEYS})
        workflow.save(ignore_permissions=True)
        return
    frappe.get_doc(record).insert(ignore_permissions=True)


def execute() -> None:
    """Install the desired route only after every collision and in-flight check passes."""
    mode = _preflight()
    _ensure_masters("Workflow State", _state_records())
    _ensure_masters("Workflow Action Master", _action_records())
    _ensure_tasks()
    _ensure_fields()
    _ensure_permissions()
    if mode != "desired":
        _replace_workflow(_desired_workflow())


def rollback() -> None:
    """Restore the known legacy route only before the new route has durable history."""
    if _workflow_mode() != "desired":
        frappe.throw(_("Payroll Entry approval rollback requires the exact installed route."))
    if frappe.get_all("Workflow Action", filters={"reference_doctype": DOCTYPE}, limit=1):
        frappe.throw(_("Payroll Entry approval rollback stopped because Workflow Action history exists."))
    desired_states = [row["state"] for row in _desired_workflow()["states"]]
    if frappe.get_all(DOCTYPE, filters={"workflow_state": ("in", desired_states)}, limit=1):
        frappe.throw(_("Payroll Entry approval rollback stopped because the route has been used."))
    _remove_permissions()
    _replace_workflow(LEGACY_WORKFLOW)
