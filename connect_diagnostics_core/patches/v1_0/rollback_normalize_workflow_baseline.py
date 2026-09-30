# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Operator-run, fingerprint-guarded recovery for the normalized baseline."""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from connect_diagnostics_core.patches.v1_0.normalize_workflow_baseline import (
    CANONICAL_WORKFLOWS,
    RECOVERY_FILE,
    RETIRED_WORKFLOWS,
    _desired_workflows,
    _has_open_actions,
    workflow_fingerprint,
)
from connect_diagnostics_core.setup.workflow_fields import CUSTOM_FIELDS


def _snapshot() -> dict[str, Any]:
    file_name = frappe.db.exists("File", {"file_name": RECOVERY_FILE, "is_private": 1})
    if not file_name:
        frappe.throw(_("Workflow recovery snapshot does not exist."))
    data = json.loads(frappe.get_doc("File", file_name).get_content())
    if data.get("schema_version") not in {1, 2}:
        frappe.throw(_("Workflow recovery snapshot schema is unsupported."))
    return data


def _post_retirement_fingerprint(record: dict[str, Any]) -> str:
    normalized = dict(record)
    normalized["is_active"] = 0
    return workflow_fingerprint(normalized)


def _preflight(snapshot: dict[str, Any]) -> None:
    desired = _desired_workflows()
    predecessors = {str(record["name"]): record for record in snapshot["workflows"]}
    for name, doctype in CANONICAL_WORKFLOWS.items():
        if _has_open_actions(doctype):
            frappe.throw(_("Workflow {0} has open actions and cannot be rolled back.").format(name))
        if not frappe.db.exists("Workflow", name):
            frappe.throw(_("Canonical Workflow {0} is missing.").format(name))
        if workflow_fingerprint(frappe.get_doc("Workflow", name)) != workflow_fingerprint(desired[name]):
            frappe.throw(_("Canonical Workflow {0} no longer matches the normalized fixture.").format(name))
        predecessor = predecessors.get(name)
        if predecessor and workflow_fingerprint(predecessor) != workflow_fingerprint(desired[name]):
            if frappe.db.has_column(doctype, "workflow_state") and frappe.db.exists(
                doctype, {"workflow_state": ["is", "set"]}
            ):
                frappe.throw(
                    _("Workflow {0} has documents and cannot be restored to its predecessor.").format(name)
                )
        if name in snapshot.get("missing", []) and frappe.db.has_column(doctype, "workflow_state"):
            if frappe.db.exists(doctype, {"workflow_state": ["is", "set"]}):
                frappe.throw(_("Workflow {0} has documents and cannot be removed.").format(name))

    for name, (doctype, _expected_hash) in RETIRED_WORKFLOWS.items():
        if _has_open_actions(doctype):
            frappe.throw(_("Retired Workflow {0} has open actions and cannot be restored.").format(name))
        if name not in predecessors or not frappe.db.exists("Workflow", name):
            continue
        current = frappe.get_doc("Workflow", name)
        if workflow_fingerprint(current) != _post_retirement_fingerprint(predecessors[name]):
            frappe.throw(_("Retired Workflow {0} changed after normalization.").format(name))


def _restore(record: dict[str, Any]) -> None:
    name = str(record["name"])
    if frappe.db.exists("Workflow", name):
        workflow = frappe.get_doc("Workflow", name)
        for key in (
            "document_type",
            "is_active",
            "override_status",
            "send_email_alert",
            "enable_action_confirmation",
        ):
            workflow.set(key, record.get(key))
        workflow.set("states", record.get("states", []))
        workflow.set("transitions", record.get("transitions", []))
        workflow.save(ignore_permissions=True)
        return
    payload = dict(record)
    payload["doctype"] = "Workflow"
    frappe.get_doc(payload).insert(ignore_permissions=True)


def _restore_transition_tasks(snapshot: dict[str, Any]) -> None:
    for record in snapshot.get("transition_tasks", []):
        name = str(record["name"])
        if frappe.db.exists("Workflow Transition Tasks", name):
            task_doc = frappe.get_doc("Workflow Transition Tasks", name)
            if _task_rows(task_doc) == record.get("tasks", []):
                continue
            task_doc.set("tasks", record.get("tasks", []))
            task_doc.save(ignore_permissions=True)
        else:
            frappe.get_doc(
                {
                    "doctype": "Workflow Transition Tasks",
                    "name": name,
                    "tasks": record.get("tasks", []),
                }
            ).insert(ignore_permissions=True)

    for name in snapshot.get("missing_transition_tasks", []):
        if not frappe.db.exists("Workflow Transition Tasks", name):
            continue
        if frappe.db.exists("Workflow Transition", {"transition_tasks": name}):
            frappe.throw(_("Workflow Transition Tasks {0} is still referenced after recovery.").format(name))
        frappe.delete_doc("Workflow Transition Tasks", name, ignore_permissions=True)


def _task_rows(task_doc: Any) -> list[dict[str, Any]]:
    return [
        {
            "task": row.task,
            "link": row.link or None,
            "enabled": int(row.enabled or 0),
            "asynchronous": int(row.asynchronous or 0),
        }
        for row in task_doc.tasks
    ]


def _remove_custom_fields(records: list[dict[str, str]]) -> None:
    for record in records:
        doctype = str(record["dt"])
        fieldname = str(record["fieldname"])
        custom_field = frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname})
        if not custom_field:
            continue
        if frappe.db.has_column(doctype, fieldname) and frappe.db.exists(doctype, {fieldname: ["is", "set"]}):
            frappe.throw(
                _("Custom Field {0}.{1} contains data and cannot be removed.").format(doctype, fieldname)
            )
        frappe.delete_doc("Custom Field", custom_field, ignore_permissions=True)


def _assert_recovered(snapshot: dict[str, Any]) -> None:
    expected = {str(record["name"]): record for record in snapshot["workflows"]}
    for name, record in expected.items():
        if not frappe.db.exists("Workflow", name):
            frappe.throw(_("Recovered Workflow {0} is missing.").format(name))
        if workflow_fingerprint(frappe.get_doc("Workflow", name)) != workflow_fingerprint(record):
            frappe.throw(_("Recovered Workflow {0} does not match its snapshot.").format(name))
    for name in snapshot.get("missing", []):
        if frappe.db.exists("Workflow", name):
            frappe.throw(_("Workflow {0} should be absent after recovery.").format(name))

    expected_tasks = {str(record["name"]): record for record in snapshot.get("transition_tasks", [])}
    for name, record in expected_tasks.items():
        if not frappe.db.exists("Workflow Transition Tasks", name):
            frappe.throw(_("Recovered Workflow Transition Tasks {0} is missing.").format(name))
        actual = frappe.get_doc("Workflow Transition Tasks", name)
        actual_rows = _task_rows(actual)
        if actual_rows != record.get("tasks", []):
            frappe.throw(_("Recovered Workflow Transition Tasks {0} differs from its snapshot.").format(name))
    for name in snapshot.get("missing_transition_tasks", []):
        if frappe.db.exists("Workflow Transition Tasks", name):
            frappe.throw(_("Workflow Transition Tasks {0} should be absent after recovery.").format(name))
    for record in snapshot.get("missing_custom_fields", []):
        if frappe.db.exists(
            "Custom Field",
            {"dt": record["dt"], "fieldname": record["fieldname"]},
        ):
            frappe.throw(
                _("Custom Field {0}.{1} should be absent after recovery.").format(
                    record["dt"], record["fieldname"]
                )
            )


def recover_incomplete_apply() -> None:
    """Recover a failed patch that stopped before Workflow fixture synchronization."""
    file_name = frappe.db.exists("File", {"file_name": RECOVERY_FILE, "is_private": 1})
    if not file_name:
        frappe.throw(_("Workflow recovery snapshot does not exist."))
    if frappe.db.exists(
        "Patch Log",
        {"patch": "connect_diagnostics_core.patches.v1_0.normalize_workflow_baseline"},
    ):
        frappe.throw(_("The normalization patch completed; use the full rollback instead."))
    file_doc = frappe.get_doc("File", file_name)
    snapshot = _snapshot()
    predecessors = {str(record["name"]): record for record in snapshot["workflows"]}
    for name, record in predecessors.items():
        if not frappe.db.exists("Workflow", name) or workflow_fingerprint(
            frappe.get_doc("Workflow", name)
        ) != workflow_fingerprint(record):
            frappe.throw(_("Workflow {0} changed after the incomplete migration attempt.").format(name))
    _restore_transition_tasks(snapshot)
    defined_fields = {
        (doctype, str(definition["fieldname"]))
        for doctype, definitions in CUSTOM_FIELDS.items()
        for definition in definitions
    }
    created_after_snapshot = [
        {"dt": str(row.dt), "fieldname": str(row.fieldname)}
        for row in frappe.get_all(
            "Custom Field",
            filters={"creation": [">=", file_doc.creation]},
            fields=["dt", "fieldname"],
        )
        if (str(row.dt), str(row.fieldname)) in defined_fields
    ]
    _remove_custom_fields(created_after_snapshot)
    _assert_recovered(snapshot)
    frappe.delete_doc("File", file_name, ignore_permissions=True)


def execute() -> None:
    snapshot = _snapshot()
    _preflight(snapshot)
    predecessors = {str(record["name"]): record for record in snapshot["workflows"]}
    for record in predecessors.values():
        _restore(record)

    for name in snapshot.get("missing", []):
        if name not in CANONICAL_WORKFLOWS or not frappe.db.exists("Workflow", name):
            continue
        frappe.delete_doc("Workflow", name, ignore_permissions=True)
    _restore_transition_tasks(snapshot)
    _remove_custom_fields(snapshot.get("missing_custom_fields", []))
    _assert_recovered(snapshot)
