# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Install the approved Asset Movement Workflow after a fail-closed preflight."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup.workflow_fields import CUSTOM_FIELDS

WORKFLOW = "Connect Asset Movement Approval"
PROTECTED_DRAFT_STATES = (
    "Asset Movement Pending Review",
    "Asset Movement Pending Approval",
    "Asset Movement Approved",
    "Asset Movement Rejected",
)
TASKS = {
    "Connect Asset Movement Maker Snapshot": "Capture Asset Movement Maker",
    "Connect Asset Movement Review Snapshot": "Capture Asset Movement Review",
    "Connect Asset Movement Approval Snapshot": "Capture Asset Movement Approval",
    "Connect Asset Movement Approval Reset": "Reset Asset Movement Approval",
    "Connect Asset Movement Submit Authorization": "Authorize Asset Movement Submit Transition",
    "Connect Asset Movement Cancel Authorization": "Authorize Asset Movement Cancel Transition",
}

_STATE_KEYS = (
    "allow_edit",
    "avoid_status_override",
    "doc_status",
    "evaluate_as_expression",
    "is_optional_state",
    "message",
    "next_action_email_template",
    "send_email",
    "state",
    "update_field",
    "update_value",
    "workflow_builder_id",
)
_TRANSITION_KEYS = (
    "action",
    "allow_self_approval",
    "allowed",
    "condition",
    "next_state",
    "send_email_to_creator",
    "state",
    "transition_tasks",
    "workflow_builder_id",
)
_CUSTOM_FIELD_VALUE_KEYS = ("fieldname", "label", "fieldtype", "options")
_CUSTOM_FIELD_FLAG_KEYS = (
    "hidden",
    "read_only",
    "allow_on_submit",
    "no_copy",
    "ignore_user_permissions",
    "is_system_generated",
)
_WORKFLOW_UPDATE_KEYS = (
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

# Exact semantic baseline shipped before D-ASSET-2026-09-26. Framework-owned
# row names, timestamps, owners, and indexes are intentionally excluded.
LEGACY_WORKFLOW = {
    "name": WORKFLOW,
    "document_type": "Asset Movement",
    "is_active": 1,
    "workflow_state_field": "workflow_state",
    "enable_action_confirmation": 1,
    "override_status": 0,
    "send_email_alert": 1,
    "workflow_data": None,
    "workflow_name": WORKFLOW,
    "states": [
        ("Stock Manager", 0, "0", 0, 0, None, None, 0, "Asset Movement Draft", None, None, None),
        ("Stock Manager", 0, "0", 0, 0, None, None, 1, "Asset Movement Pending Approval", None, None, None),
        ("Stock Manager", 0, "0", 0, 0, None, None, 1, "Asset Movement Approved", None, None, None),
        ("System Manager", 0, "0", 0, 0, None, None, 0, "Asset Movement Rejected", None, None, None),
        ("Stock Manager", 0, "1", 0, 0, None, None, 0, "Asset Movement Submitted", None, None, None),
        ("Stock Manager", 0, "2", 0, 0, None, None, 0, "Asset Movement Cancelled", None, None, None),
    ],
    "transitions": [
        (
            "Submit Asset Movement for Approval",
            0,
            "Stock Manager",
            None,
            "Asset Movement Pending Approval",
            0,
            "Asset Movement Draft",
            None,
            None,
        ),
        (
            "Approve Asset Movement",
            0,
            "C-Level Approver",
            None,
            "Asset Movement Approved",
            0,
            "Asset Movement Pending Approval",
            None,
            None,
        ),
        (
            "Approve Asset Movement",
            0,
            "Stock Manager",
            None,
            "Asset Movement Approved",
            0,
            "Asset Movement Pending Approval",
            None,
            None,
        ),
        (
            "Reject Asset Movement",
            0,
            "C-Level Approver",
            None,
            "Asset Movement Rejected",
            0,
            "Asset Movement Pending Approval",
            None,
            None,
        ),
        (
            "Reject Asset Movement",
            0,
            "Stock Manager",
            None,
            "Asset Movement Rejected",
            0,
            "Asset Movement Pending Approval",
            None,
            None,
        ),
        (
            "Post Asset Movement",
            0,
            "Accounts Manager",
            None,
            "Asset Movement Submitted",
            0,
            "Asset Movement Approved",
            None,
            None,
        ),
        (
            "Cancel Asset Movement",
            0,
            "Accounts Manager",
            None,
            "Asset Movement Cancelled",
            0,
            "Asset Movement Submitted",
            None,
            None,
        ),
    ],
}


def _fixture(filename: str) -> list[dict[str, Any]]:
    path = Path(frappe.get_app_path("connect_diagnostics_core", "fixtures", filename))
    return json.loads(path.read_text(encoding="utf-8"))


def _value(record: Any, fieldname: str) -> Any:
    if isinstance(record, dict):
        return record.get(fieldname)
    getter = getattr(record, "get", None)
    if callable(getter):
        return getter(fieldname)
    return getattr(record, fieldname, None)


def _flag(record: Any, fieldname: str) -> int:
    return int(_value(record, fieldname) or 0)


def _desired_workflow() -> dict[str, Any]:
    return next(row for row in _fixture("workflow.json") if row["name"] == WORKFLOW)


def _workflow_shape(record: Any) -> dict[str, Any]:
    return {
        "name": _value(record, "name"),
        "document_type": _value(record, "document_type"),
        "is_active": _flag(record, "is_active"),
        "workflow_state_field": _value(record, "workflow_state_field"),
        "enable_action_confirmation": _flag(record, "enable_action_confirmation"),
        "override_status": _flag(record, "override_status"),
        "send_email_alert": _flag(record, "send_email_alert"),
        "workflow_data": _value(record, "workflow_data"),
        "workflow_name": _value(record, "workflow_name"),
        "states": [
            tuple(
                _flag(row, key)
                if key
                in {
                    "avoid_status_override",
                    "evaluate_as_expression",
                    "is_optional_state",
                    "send_email",
                }
                else _value(row, key)
                for key in _STATE_KEYS
            )
            for row in (_value(record, "states") or [])
        ],
        "transitions": [
            tuple(
                _flag(row, key)
                if key in {"allow_self_approval", "send_email_to_creator"}
                else _value(row, key)
                for key in _TRANSITION_KEYS
            )
            for row in (_value(record, "transitions") or [])
        ],
    }


def _desired_state_records() -> dict[str, dict[str, Any]]:
    names = {row["state"] for row in _desired_workflow()["states"]}
    return {row["name"]: row for row in _fixture("workflow_state.json") if row["name"] in names}


def _desired_action_records() -> dict[str, dict[str, Any]]:
    names = {row["action"] for row in _desired_workflow()["transitions"]}
    return {row["name"]: row for row in _fixture("workflow_action_master.json") if row["name"] in names}


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


def _custom_field_shape(record: Any) -> tuple[Any, ...]:
    return tuple(_value(record, key) for key in _CUSTOM_FIELD_VALUE_KEYS) + tuple(
        _flag(record, key) for key in _CUSTOM_FIELD_FLAG_KEYS
    )


def _custom_field(name: str) -> Any | None:
    return frappe.db.get_value(
        "Custom Field",
        {"dt": "Asset Movement", "fieldname": name},
        [*_CUSTOM_FIELD_VALUE_KEYS, *_CUSTOM_FIELD_FLAG_KEYS],
        as_dict=True,
    )


def _workflow_mode() -> str:
    if not frappe.db.exists("Workflow", WORKFLOW):
        return "absent"
    current = _workflow_shape(frappe.get_doc("Workflow", WORKFLOW))
    if current == LEGACY_WORKFLOW:
        return "legacy"
    if current == _workflow_shape(_desired_workflow()):
        return "desired"
    frappe.throw(_("Asset Movement approval workflow conflicts with the approved configuration."))
    raise AssertionError("frappe.throw must raise")


def _validate_masters(doctype: str, expected_records: dict[str, dict[str, Any]]) -> None:
    for name, expected in expected_records.items():
        if not frappe.db.exists(doctype, name):
            continue
        actual = frappe.get_doc(doctype, name)
        if _master_shape(doctype, actual) != _master_shape(doctype, expected):
            frappe.throw(f"{doctype} {name} conflicts with the approved configuration.")


def _validate_tasks() -> None:
    for name, task in TASKS.items():
        if not frappe.db.exists("Workflow Transition Tasks", name):
            continue
        if _task_shape(frappe.get_doc("Workflow Transition Tasks", name)) != [(task, 1, 0)]:
            frappe.throw(f"Workflow Transition Tasks {name} conflicts with the approved configuration.")


def _validate_custom_fields() -> None:
    for expected in CUSTOM_FIELDS["Asset Movement"]:
        actual = _custom_field(str(expected["fieldname"]))
        if actual and _custom_field_shape(actual) != _custom_field_shape(expected):
            frappe.throw(
                f"Custom Field Asset Movement-{expected['fieldname']} conflicts with the approved configuration."
            )


def _preflight() -> str:
    active = frappe.get_all(
        "Workflow", filters={"document_type": "Asset Movement", "is_active": 1}, pluck="name"
    )
    if any(name != WORKFLOW for name in active):
        frappe.throw(_("Asset Movement approval migration found another active workflow."))
    mode = _workflow_mode()
    _validate_masters("Workflow State", _desired_state_records())
    _validate_masters("Workflow Action Master", _desired_action_records())
    _validate_tasks()
    _validate_custom_fields()
    if frappe.get_all(
        "Workflow Action", filters={"reference_doctype": "Asset Movement", "status": "Open"}, limit=1
    ):
        frappe.throw(_("Asset Movement approval migration cannot run while open workflow actions exist."))
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


def _ensure_custom_fields() -> None:
    missing = [
        field for field in CUSTOM_FIELDS["Asset Movement"] if not _custom_field(str(field["fieldname"]))
    ]
    if missing:
        create_custom_fields({"Asset Movement": missing}, ignore_validate=True)


def _replace_workflow(record: dict[str, Any]) -> None:
    workflow = frappe.get_doc("Workflow", WORKFLOW)
    workflow.update({key: record.get(key) for key in _WORKFLOW_UPDATE_KEYS})
    workflow.save(ignore_permissions=True)


def execute() -> None:
    mode = _preflight()
    _ensure_masters("Workflow State", _desired_state_records())
    _ensure_masters("Workflow Action Master", _desired_action_records())
    _ensure_tasks()
    _ensure_custom_fields()
    if mode == "absent":
        frappe.get_doc(_desired_workflow()).insert(ignore_permissions=True)
    elif mode == "legacy":
        _replace_workflow(_desired_workflow())


def rollback() -> None:
    """Restore only the exact legacy Workflow; preserve fields, masters, tasks, and history."""
    if _preflight() != "desired":
        frappe.throw(_("Asset Movement approval rollback requires the exact desired workflow."))
    if frappe.get_all(
        "Asset Movement", filters={"docstatus": 0, "workflow_state": ["in", PROTECTED_DRAFT_STATES]}, limit=1
    ):
        frappe.throw(_("Asset Movement approval rollback cannot run while protected drafts exist."))

    legacy = {
        "doctype": "Workflow",
        "name": WORKFLOW,
        "workflow_name": WORKFLOW,
        **LEGACY_WORKFLOW,
        "states": [
            dict(zip(_STATE_KEYS, row, strict=True))
            for row in cast(list[tuple[Any, ...]], LEGACY_WORKFLOW["states"])
        ],
        "transitions": [
            dict(zip(_TRANSITION_KEYS, row, strict=True))
            for row in cast(list[tuple[Any, ...]], LEGACY_WORKFLOW["transitions"])
        ],
    }
    _replace_workflow(legacy)
