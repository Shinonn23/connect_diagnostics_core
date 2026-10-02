# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Guard native Workflow fixtures before install or migration can import them."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core import hooks

RECOVERY_FILE = "connect-normalized-workflow-baseline-recovery-v4.json"
SNAPSHOT_VERSION = 4
HISTORY_PAGE_SIZE = 500
ARCHIVE_FILE = Path(__file__).with_name("workflow_baseline_v4.json")

CANONICAL_WORKFLOWS = {
    "Connect Stock Transfer Approval": "Stock Entry",
    "Connect Stock Reconciliation Blueprint": "Stock Reconciliation",
    "Connect Asset Movement Approval": "Asset Movement",
    "Connect Journal Entry Approval": "Journal Entry",
    "Connect Sales Order Blueprint": "Sales Order",
    "Connect Sales Invoice Credit Blueprint": "Sales Invoice",
    "Connect Purchase Order Blueprint": "Purchase Order",
    "Connect Purchase Invoice Blueprint": "Purchase Invoice",
    "Connect Payment Entry Approval": "Payment Entry",
    "Connect Payroll Entry Blueprint": "Payroll Entry",
}

_WORKFLOW_TEXT = (
    "name",
    "workflow_name",
    "document_type",
    "workflow_state_field",
    "workflow_data",
)
_WORKFLOW_CHECKS = (
    "docstatus",
    "is_active",
    "override_status",
    "send_email_alert",
    "enable_action_confirmation",
)
_STATE_TEXT = (
    "state",
    "doc_status",
    "update_field",
    "update_value",
    "allow_edit",
    "message",
    "next_action_email_template",
)
_STATE_CHECKS = (
    "is_optional_state",
    "avoid_status_override",
    "send_email",
    "evaluate_as_expression",
)
_TRANSITION_TEXT = (
    "state",
    "action",
    "next_state",
    "allowed",
    "condition",
    "transition_tasks",
)
_TRANSITION_CHECKS = ("allow_self_approval", "send_email_to_creator")


def _value(record: Any, key: str) -> Any:
    return record.get(key) if isinstance(record, dict) else getattr(record, key, None)


def _text(record: Any, key: str) -> str | None:
    value = _value(record, key)
    return str(value) if value not in (None, "") else None


def _checks(record: Any, names: tuple[str, ...]) -> dict[str, int]:
    return {key: int(_value(record, key) or 0) for key in names}


def workflow_shape(record: Any) -> dict[str, Any]:
    """Compare all native business and side-effect fields, excluding row metadata."""
    shape: dict[str, Any] = {key: _text(record, key) for key in _WORKFLOW_TEXT}
    shape.update(_checks(record, _WORKFLOW_CHECKS))
    shape["states"] = [
        {
            **{key: _text(row, key) for key in _STATE_TEXT},
            **_checks(row, _STATE_CHECKS),
        }
        for row in (_value(record, "states") or [])
    ]
    shape["transitions"] = [
        {
            **{key: _text(row, key) for key in _TRANSITION_TEXT},
            **_checks(row, _TRANSITION_CHECKS),
        }
        for row in (_value(record, "transitions") or [])
    ]
    return shape


def workflow_fingerprint(record: Any) -> str:
    payload = json.dumps(workflow_shape(record), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _master_shape(record: Any, doctype: str) -> dict[str, Any]:
    key = "workflow_state_name" if doctype == "Workflow State" else "workflow_action_name"
    shape = {
        "name": _text(record, "name"),
        key: _text(record, key),
        "docstatus": int(_value(record, "docstatus") or 0),
    }
    if doctype == "Workflow State":
        shape.update({"icon": _text(record, "icon"), "style": _text(record, "style")})
    return shape


def _task_rows(record: Any) -> list[dict[str, Any]]:
    return [
        {
            "task": _text(row, "task"),
            "link": _text(row, "link"),
            **_checks(row, ("enabled", "asynchronous")),
        }
        for row in (_value(record, "tasks") or [])
    ]


def _archive() -> dict[str, Any]:
    archive: dict[str, Any] = json.loads(ARCHIVE_FILE.read_text())
    if archive.get("schema_version") != SNAPSHOT_VERSION:
        frappe.throw(_("Archived Workflow baseline has an invalid schema version."))
    return archive


def _archived_fields() -> dict[str, list[dict[str, Any]]]:
    return _archive()["custom_fields"]


CUSTOM_FIELDS = _archived_fields()


def _fixture_rows(rows: list[dict[str, Any]], doctype: str, semantic: str) -> list[dict[str, Any]]:
    names = [str(row["name"]) for row in rows]
    if len(names) != len(set(names)) or any(
        row.get("doctype") != doctype or row.get(semantic) != row["name"] for row in rows
    ):
        frappe.throw(
            _("Archived Workflow {0} has duplicate or inconsistent record identities.").format(doctype)
        )
    return rows


def _blueprint() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    archive = _archive()
    workflows = _fixture_rows(archive["workflows"], "Workflow", "workflow_name")
    states = _fixture_rows(archive["states"], "Workflow State", "workflow_state_name")
    actions = _fixture_rows(archive["actions"], "Workflow Action Master", "workflow_action_name")
    desired = {str(row["name"]): row for row in workflows}
    state_map = {str(row["name"]): row for row in states}
    action_map = {str(row["name"]): row for row in actions}
    if set(desired) != set(CANONICAL_WORKFLOWS):
        frappe.throw(_("Workflow fixture must contain exactly the ten canonical routes."))
    referenced_states: set[str] = set()
    referenced_actions: set[str] = set()
    for name, doctype in CANONICAL_WORKFLOWS.items():
        record = desired[name]
        if record.get("document_type") != doctype or int(record.get("is_active") or 0) != 1:
            frappe.throw(_("Canonical Workflow {0} has an invalid target or activation state.").format(name))
        state_status: dict[str, str] = {}
        for row in record["states"]:
            state = str(row["state"])
            if state in state_status or str(row["doc_status"]) not in {"0", "1", "2"}:
                frappe.throw(_("Canonical Workflow {0} has duplicate or invalid states.").format(name))
            state_status[state] = str(row["doc_status"])
            referenced_states.add(state)
        transition_keys: set[tuple[str, str, str]] = set()
        for row in record["transitions"]:
            key = (str(row["state"]), str(row["action"]), str(row["allowed"]))
            if (
                key in transition_keys
                or row["state"] not in state_status
                or row["next_state"] not in state_status
            ):
                frappe.throw(_("Canonical Workflow {0} has duplicate or invalid transitions.").format(name))
            transition_keys.add(key)
            referenced_states.add(str(row["next_state"]))
            referenced_actions.add(str(row["action"]))
    if set(state_map) != referenced_states or set(action_map) != referenced_actions:
        frappe.throw(_("Workflow companion fixtures do not match the route references exactly."))
    if archive["desired_hashes"] != {name: workflow_fingerprint(record) for name, record in desired.items()}:
        frappe.throw(_("Archived Workflow hashes differ from the approved v4 baseline."))
    return desired, state_map, action_map


def _desired_workflows() -> dict[str, dict[str, Any]]:
    return _blueprint()[0]


def _business_rows(doctype: str) -> Iterator[dict[str, Any]]:
    if not frappe.db.has_column(doctype, "workflow_state"):
        if frappe.db.count(doctype):
            frappe.throw(_("Existing {0} records lack a workflow state column.").format(doctype))
        return
    last_name = ""
    while True:
        filters = {"name": [">", last_name]} if last_name else {}
        rows = frappe.get_all(
            doctype,
            filters=filters,
            fields=["name", "docstatus", "workflow_state"],
            order_by="name asc",
            limit_page_length=HISTORY_PAGE_SIZE,
        )
        if not rows:
            return
        page_names = [str(row.name) for row in rows]
        if len(page_names) != len(set(page_names)) or page_names[-1] == last_name:
            frappe.throw(_("Business history pagination did not advance for {0}.").format(doctype))
        for row in rows:
            name = str(row.name)
            yield {
                "name": name,
                "docstatus": int(row.docstatus),
                "workflow_state": str(row.workflow_state or ""),
            }
        last_name = page_names[-1]
        if len(rows) < HISTORY_PAGE_SIZE:
            return


def _action_rows(doctype: str) -> Iterator[dict[str, Any]]:
    last_name = ""
    while True:
        filters: dict[str, Any] = {"reference_doctype": doctype}
        if last_name:
            filters["name"] = [">", last_name]
        rows = frappe.get_all(
            "Workflow Action",
            filters=filters,
            fields=["name", "reference_name", "status", "workflow_state"],
            order_by="name asc",
            limit_page_length=HISTORY_PAGE_SIZE,
        )
        if not rows:
            return
        page_names = [str(row.name) for row in rows]
        if len(page_names) != len(set(page_names)) or page_names[-1] == last_name:
            frappe.throw(_("Workflow Action pagination did not advance for {0}.").format(doctype))
        for row in rows:
            name = str(row.name)
            yield {
                "name": name,
                "reference_name": str(row.reference_name or ""),
                "status": str(row.status or ""),
                "workflow_state": str(row.workflow_state or ""),
            }
        last_name = page_names[-1]
        if len(rows) < HISTORY_PAGE_SIZE:
            return


def _history_fingerprint(
    rows: Iterator[dict[str, Any]], valid_states: dict[str, int] | None = None
) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    for row in rows:
        if valid_states is not None and valid_states.get(row["workflow_state"]) != row["docstatus"]:
            frappe.throw(_("A business document has an invalid Workflow state or docstatus."))
        digest.update(json.dumps(row, sort_keys=True, separators=(",", ":")).encode())
        digest.update(b"\n")
        count += 1
    return {"count": count, "sha256": digest.hexdigest()}


def _task_blueprints(desired: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups = {
        str(row["transition_tasks"])
        for workflow in desired.values()
        for row in workflow["transitions"]
        if row.get("transition_tasks")
    }
    methods = {str(row["name"]): str(row["method"]) for row in hooks.workflow_methods}
    if len(methods) != len(hooks.workflow_methods):
        frappe.throw(_("Workflow callback registrations contain duplicate names."))
    archive = _archive()
    blueprints: dict[str, list[dict[str, Any]]] = archive["task_groups"]
    if set(blueprints) != groups:
        frappe.throw(_("Archived Workflow callback groups differ from route references."))
    for rows in blueprints.values():
        for row in rows:
            callback = row["task"]
            if (
                callback not in archive["callback_methods"]
                or methods.get(callback) != archive["callback_methods"][callback]
                or not callable(frappe.get_attr(methods[callback]))
            ):
                frappe.throw(_("Workflow callback {0} is not registered or callable.").format(callback))
    states, actions = _blueprint()[1:]
    if _companion_hash(states, actions, blueprints) != archive["companion_hash"]:
        frappe.throw(_("Archived Workflow companion hash differs from the approved v4 baseline."))
    return blueprints


def _preflight_site(
    desired: dict[str, dict[str, Any]],
    states: dict[str, dict[str, Any]],
    actions: dict[str, dict[str, Any]],
    groups: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    business_history: dict[str, dict[str, Any]] = {}
    action_history: dict[str, dict[str, Any]] = {}
    for name, doctype in CANONICAL_WORKFLOWS.items():
        active = set(
            frappe.get_all("Workflow", filters={"document_type": doctype, "is_active": 1}, pluck="name")
        )
        if active - {name}:
            frappe.throw(_("An active Workflow collision exists for {0}.").format(doctype))
        exists = frappe.db.exists("Workflow", name)
        if exists and workflow_shape(frappe.get_doc("Workflow", name)) != workflow_shape(desired[name]):
            frappe.throw(_("Workflow {0} differs from the reviewed fixture.").format(name))
        valid_states = (
            {str(row["state"]): int(row["doc_status"]) for row in desired[name]["states"]} if exists else None
        )
        business_history[doctype] = _history_fingerprint(_business_rows(doctype), valid_states)
        action_history[doctype] = _history_fingerprint(_action_rows(doctype))
        if not exists:
            if business_history[doctype]["count"] or action_history[doctype]["count"]:
                frappe.throw(_("Workflow {0} is missing but business history or actions exist.").format(name))
    for doctype, records in (("Workflow State", states), ("Workflow Action Master", actions)):
        for name, record in records.items():
            if frappe.db.exists(doctype, name) and _master_shape(
                frappe.get_doc(doctype, name), doctype
            ) != _master_shape(record, doctype):
                frappe.throw(_("Workflow companion record {0} differs from the fixture.").format(name))
    for name, blueprint in groups.items():
        if frappe.db.exists(
            "Workflow Transition", {"transition_tasks": name, "parent": ["not in", list(CANONICAL_WORKFLOWS)]}
        ):
            frappe.throw(_("Workflow task group {0} has a foreign reference.").format(name))
        if (
            frappe.db.exists("Workflow Transition Tasks", name)
            and _task_rows(frappe.get_doc("Workflow Transition Tasks", name)) != blueprint
        ):
            frappe.throw(_("Workflow task group {0} differs from the reviewed callbacks.").format(name))
    for doctype, definitions in CUSTOM_FIELDS.items():
        for definition in definitions:
            fieldname = str(definition["fieldname"])
            existing = frappe.db.get_value(
                "Custom Field",
                {"dt": doctype, "fieldname": fieldname},
                list(definition),
                as_dict=True,
            )
            if existing and any(
                (existing.get(key) or None) != (value or None) for key, value in definition.items()
            ):
                frappe.throw(
                    _("Custom Field {0}.{1} differs from the source definition.").format(doctype, fieldname)
                )
    return business_history, action_history


def preflight() -> None:
    """Read-only guard, safe before app registration and before every fixture sync."""
    desired, states, actions = _blueprint()
    groups = _task_blueprints(desired)
    _assert_snapshot_revision(desired, states, actions, groups)
    _preflight_site(desired, states, actions, groups)


def _snapshot_payload(
    desired: dict[str, dict[str, Any]],
    states: dict[str, dict[str, Any]],
    actions: dict[str, dict[str, Any]],
    groups: dict[str, list[dict[str, Any]]],
    histories: tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "schema_version": SNAPSHOT_VERSION,
        "desired_hashes": {name: workflow_fingerprint(record) for name, record in desired.items()},
        "companion_hash": _companion_hash(states, actions, groups),
        "missing_workflows": sorted(name for name in desired if not frappe.db.exists("Workflow", name)),
        "missing_states": sorted(name for name in states if not frappe.db.exists("Workflow State", name)),
        "missing_actions": sorted(
            name for name in actions if not frappe.db.exists("Workflow Action Master", name)
        ),
        "missing_groups": sorted(
            name for name in groups if not frappe.db.exists("Workflow Transition Tasks", name)
        ),
        "business_history": histories[0],
        "action_history": histories[1],
    }


def _companion_hash(
    states: dict[str, dict[str, Any]],
    actions: dict[str, dict[str, Any]],
    groups: dict[str, list[dict[str, Any]]],
) -> str:
    payload = {
        "states": {name: _master_shape(record, "Workflow State") for name, record in states.items()},
        "actions": {
            name: _master_shape(record, "Workflow Action Master") for name, record in actions.items()
        },
        "groups": groups,
        "callback_methods": {
            str(row["name"]): str(row["method"])
            for row in hooks.workflow_methods
            if row["name"] in {task["task"] for tasks in groups.values() for task in tasks}
        },
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _assert_snapshot_revision(
    desired: dict[str, dict[str, Any]],
    states: dict[str, dict[str, Any]],
    actions: dict[str, dict[str, Any]],
    groups: dict[str, list[dict[str, Any]]],
) -> None:
    existing = frappe.db.exists("File", {"file_name": RECOVERY_FILE, "is_private": 1})
    if not existing:
        return
    saved = json.loads(frappe.get_doc("File", existing).get_content())
    if (
        saved.get("schema_version") != SNAPSHOT_VERSION
        or saved.get("desired_hashes")
        != {name: workflow_fingerprint(record) for name, record in desired.items()}
        or saved.get("companion_hash") != _companion_hash(states, actions, groups)
    ):
        frappe.throw(_("Workflow recovery snapshot differs from the approved revision."))


def _save_snapshot(payload: dict[str, Any]) -> None:
    existing = frappe.db.exists("File", {"file_name": RECOVERY_FILE, "is_private": 1})
    if existing:
        saved = json.loads(frappe.get_doc("File", existing).get_content())
        if (
            saved.get("schema_version") != SNAPSHOT_VERSION
            or saved.get("desired_hashes") != payload["desired_hashes"]
            or saved.get("companion_hash") != payload["companion_hash"]
        ):
            frappe.throw(_("Workflow recovery snapshot differs from the approved revision."))
        return
    frappe.get_doc(
        {
            "doctype": "File",
            "file_name": RECOVERY_FILE,
            "is_private": 1,
            "content": json.dumps(payload, sort_keys=True),
        }
    ).insert(ignore_permissions=True)


def execute() -> None:
    """Prepare only absent fields and exact callback groups after read-only checks."""
    desired, states, actions = _blueprint()
    groups = _task_blueprints(desired)
    histories = _preflight_site(desired, states, actions, groups)
    _save_snapshot(_snapshot_payload(desired, states, actions, groups, histories))
    missing_fields: dict[str, list[dict[str, Any]]] = {}
    for doctype, definitions in CUSTOM_FIELDS.items():
        missing = [
            definition
            for definition in definitions
            if not frappe.db.exists(
                "Custom Field", {"dt": doctype, "fieldname": str(definition["fieldname"])}
            )
        ]
        if missing:
            missing_fields[doctype] = missing
    if missing_fields:
        create_custom_fields(missing_fields, ignore_validate=True)
    for name, rows in groups.items():
        if not frappe.db.exists("Workflow Transition Tasks", name):
            frappe.get_doc({"doctype": "Workflow Transition Tasks", "name": name, "tasks": rows}).insert(
                ignore_permissions=True
            )
