# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Strict recovery for the fresh-only native Workflow fixture preparation."""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from connect_diagnostics_core.patches.v1_0.normalize_workflow_baseline import (
    CANONICAL_WORKFLOWS,
    RECOVERY_FILE,
    SNAPSHOT_VERSION,
    _action_rows,
    _blueprint,
    _business_rows,
    _companion_hash,
    _history_fingerprint,
    _master_shape,
    _task_blueprints,
    _task_rows,
    workflow_fingerprint,
    workflow_shape,
)


def _snapshot() -> dict[str, Any]:
    file_name = frappe.db.exists("File", {"file_name": RECOVERY_FILE, "is_private": 1})
    if not file_name:
        frappe.throw(_("Workflow recovery snapshot does not exist."))
    data: dict[str, Any] = json.loads(frappe.get_doc("File", file_name).get_content())
    if data.get("schema_version") != SNAPSHOT_VERSION:
        frappe.throw(_("Workflow recovery snapshot schema is unsupported."))
    return data


def _check_histories(snapshot: dict[str, Any]) -> None:
    for doctype in CANONICAL_WORKFLOWS.values():
        if _history_fingerprint(_business_rows(doctype)) != snapshot["business_history"][doctype]:
            frappe.throw(_("Business history for {0} changed after the Workflow snapshot.").format(doctype))
        if _history_fingerprint(_action_rows(doctype)) != snapshot["action_history"][doctype]:
            frappe.throw(_("Workflow Actions for {0} changed after the Workflow snapshot.").format(doctype))


def _check_removal_references(snapshot: dict[str, Any]) -> None:
    missing_workflows = snapshot["missing_workflows"]

    def foreign_reference(doctype: str, filters: dict[str, Any]) -> bool:
        if missing_workflows:
            filters["parent"] = ["not in", missing_workflows]
        return bool(frappe.db.exists(doctype, filters))

    for name in snapshot["missing_groups"]:
        if foreign_reference("Workflow Transition", {"transition_tasks": name}):
            frappe.throw(_("Workflow task group {0} has another reference.").format(name))
    for name in snapshot["missing_states"]:
        for child, field in (
            ("Workflow Document State", "state"),
            ("Workflow Transition", "state"),
            ("Workflow Transition", "next_state"),
        ):
            if foreign_reference(child, {field: name}):
                frappe.throw(_("Workflow State {0} has another reference.").format(name))
    for name in snapshot["missing_actions"]:
        if foreign_reference("Workflow Transition", {"action": name}):
            frappe.throw(_("Workflow Action Master {0} has another reference.").format(name))


def _preflight(snapshot: dict[str, Any], *, incomplete: bool) -> None:
    desired, states, actions = _blueprint()
    groups = _task_blueprints(desired)
    if snapshot["desired_hashes"] != {name: workflow_fingerprint(record) for name, record in desired.items()}:
        frappe.throw(_("Workflow fixture changed after the recovery snapshot."))
    if snapshot["companion_hash"] != _companion_hash(states, actions, groups):
        frappe.throw(_("Workflow companion fixtures changed after the recovery snapshot."))
    _check_histories(snapshot)
    for name, record in desired.items():
        exists = frappe.db.exists("Workflow", name)
        if incomplete and name in snapshot["missing_workflows"] and exists:
            frappe.throw(_("Workflow {0} appeared after incomplete preparation.").format(name))
        if not exists:
            if not incomplete or name not in snapshot["missing_workflows"]:
                frappe.throw(_("Workflow {0} is missing after preparation.").format(name))
            continue
        if workflow_shape(frappe.get_doc("Workflow", name)) != workflow_shape(record):
            frappe.throw(_("Workflow {0} changed after preparation.").format(name))
    for doctype, records, missing in (
        ("Workflow State", states, snapshot["missing_states"]),
        ("Workflow Action Master", actions, snapshot["missing_actions"]),
    ):
        for name, record in records.items():
            exists = frappe.db.exists(doctype, name)
            if incomplete and name in missing and exists:
                frappe.throw(_("Workflow companion {0} appeared after incomplete preparation.").format(name))
            if not exists:
                if not incomplete or name not in missing:
                    frappe.throw(_("Workflow companion {0} is missing after preparation.").format(name))
                continue
            if _master_shape(frappe.get_doc(doctype, name), doctype) != _master_shape(record, doctype):
                frappe.throw(_("Workflow companion {0} changed after preparation.").format(name))
    for name, rows in groups.items():
        exists = frappe.db.exists("Workflow Transition Tasks", name)
        if not exists:
            if not incomplete or name not in snapshot["missing_groups"]:
                frappe.throw(_("Workflow task group {0} is missing after preparation.").format(name))
            continue
        if _task_rows(frappe.get_doc("Workflow Transition Tasks", name)) != rows:
            frappe.throw(_("Workflow task group {0} changed after preparation.").format(name))
    _check_removal_references(snapshot)


def _remove_created(snapshot: dict[str, Any], *, incomplete: bool) -> None:
    if not incomplete:
        for name in snapshot["missing_workflows"]:
            frappe.delete_doc("Workflow", name, ignore_permissions=True)
        for name in snapshot["missing_states"]:
            frappe.delete_doc("Workflow State", name, ignore_permissions=True)
        for name in snapshot["missing_actions"]:
            frappe.delete_doc("Workflow Action Master", name, ignore_permissions=True)
    for name in snapshot["missing_groups"]:
        if frappe.db.exists("Workflow Transition Tasks", name):
            frappe.delete_doc("Workflow Transition Tasks", name, ignore_permissions=True)


def _assert_recovered(snapshot: dict[str, Any], *, incomplete: bool) -> None:
    _check_histories(snapshot)
    desired, states, actions = _blueprint()
    groups = _task_blueprints(desired)
    for name, record in desired.items():
        if name not in snapshot["missing_workflows"] and workflow_shape(
            frappe.get_doc("Workflow", name)
        ) != workflow_shape(record):
            frappe.throw(_("Existing Workflow {0} changed during recovery.").format(name))
    for doctype, records, missing in (
        ("Workflow State", states, snapshot["missing_states"]),
        ("Workflow Action Master", actions, snapshot["missing_actions"]),
    ):
        for name, record in records.items():
            if name not in missing and _master_shape(frappe.get_doc(doctype, name), doctype) != _master_shape(
                record, doctype
            ):
                frappe.throw(_("Existing Workflow companion {0} changed during recovery.").format(name))
    for name, rows in groups.items():
        if (
            name not in snapshot["missing_groups"]
            and _task_rows(frappe.get_doc("Workflow Transition Tasks", name)) != rows
        ):
            frappe.throw(_("Existing Workflow task group {0} changed during recovery.").format(name))
    for doctype, names in (
        ("Workflow", snapshot["missing_workflows"]),
        ("Workflow State", snapshot["missing_states"]),
        ("Workflow Action Master", snapshot["missing_actions"]),
        ("Workflow Transition Tasks", snapshot["missing_groups"]),
    ):
        for name in names:
            if frappe.db.exists(doctype, name):
                frappe.throw(_("Recovered configuration {0} should be absent.").format(name))


def recover_incomplete_apply() -> None:
    """Remove only groups created by a failed prepare before fixture sync."""
    snapshot = _snapshot()
    _preflight(snapshot, incomplete=True)
    _remove_created(snapshot, incomplete=True)
    _assert_recovered(snapshot, incomplete=True)


def execute() -> None:
    """Rollback only exact fresh additions with unchanged business history."""
    snapshot = _snapshot()
    _preflight(snapshot, incomplete=False)
    _remove_created(snapshot, incomplete=False)
    _assert_recovered(snapshot, incomplete=False)
