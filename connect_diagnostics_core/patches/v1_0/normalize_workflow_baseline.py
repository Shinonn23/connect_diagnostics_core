# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Preflight the normalized Workflow baseline and retire exact obsolete routes.

This patch runs before fixture import. It never rewrites business documents or
Workflow Actions. The later fixture sync may update a canonical Workflow only
after this patch proves that the current row is either the desired fixture or
an exact reviewed predecessor with no incompatible in-flight work.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup.workflow_fields import CUSTOM_FIELDS

RECOVERY_FILE = "connect-normalized-workflow-baseline-recovery.json"

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

# Exact local.test predecessors captured before TSK-602 mutation. These hashes
# include ordered states and transitions and therefore do not authorize a
# site-owned variation that merely reuses an app-owned name.
PREDECESSOR_FINGERPRINTS = {
    "Connect Stock Transfer Approval": "e6c93b71a66f5859f20cf2c5d077cbee22a7bc0b972513fd5f46d4a968a7aed6",
    "Connect Stock Reconciliation Blueprint": "4a64451600d4dc3e6077b080cf918e4c30044a2633dc2e35210e209a4be9e4eb",
    "Connect Asset Movement Approval": "bcd76f7c03365e6ce5a638544e3e8e6cfe82876f355bf4a22f918cb0487e9048",
    "Connect Journal Entry Approval": "bd7b53d0f267caa31230d0d3009e54e50832e029c2bbcf01fae508f022c93ad6",
    "Connect Sales Order Blueprint": "dd2d2074c1710ce4a8722061611caabc1d2807f9e2d04d8747d3757dea431a78",
    "Connect Sales Invoice Credit Blueprint": "5ec14155aa5e4d4644e859e6eec77f2b85377fcba8bba0245e215453377f4f1f",
    "Connect Purchase Order Blueprint": "8218346a1c2121f6405612d972ced112e12e9325014f89078ab79f3c897fede3",
    "Connect Purchase Invoice Blueprint": "cf8c9697c3d764f8cb33b167d1cb8035402f84eaf7720141d4552353331f54f1",
    "Connect Payment Entry Approval": "54a81a2dd3aba72a86e1ea5f85d43235ae0d9c3a9d5b87b41758052245f69a54",
    "Connect Payroll Entry Blueprint": "b18f2b8127e4cd5f40cee1defd7c598ceec629d68ab1697db084ffd7942a908f",
}

RETIRED_WORKFLOWS = {
    "Connect Asset Disposal Blueprint": (
        "Asset",
        "8de38ffd6007415e136ad0a1476189e1d543355e137c6990b4a8635584d6e98a",
    ),
    "Connect Material Request Blueprint": (
        "Material Request",
        "5c535b4ee549ecac6753402e145352b2884fe433c2372ee1d77141f0c90e2633",
    ),
}

_PARENT_KEYS = (
    "name",
    "document_type",
    "is_active",
    "override_status",
    "send_email_alert",
    "enable_action_confirmation",
)
_STATE_KEYS = ("state", "doc_status", "allow_edit", "send_email")
_TRANSITION_KEYS = (
    "state",
    "action",
    "next_state",
    "allowed",
    "condition",
    "allow_self_approval",
    "transition_tasks",
)


def _value(record: Any, key: str) -> Any:
    if isinstance(record, dict):
        return record.get(key)
    return getattr(record, key, None)


def workflow_shape(record: Any) -> dict[str, Any]:
    """Return the ordered, security-relevant Workflow configuration."""
    return {
        "name": _value(record, "name"),
        "document_type": _value(record, "document_type"),
        "is_active": int(_value(record, "is_active") or 0),
        "states": [
            {
                "state": _value(row, "state"),
                "doc_status": str(_value(row, "doc_status")),
                "allow_edit": _value(row, "allow_edit"),
                "send_email": int(_value(row, "send_email") or 0),
            }
            for row in (_value(record, "states") or [])
        ],
        "transitions": [
            {
                "state": _value(row, "state"),
                "action": _value(row, "action"),
                "next_state": _value(row, "next_state"),
                "allowed": _value(row, "allowed"),
                "condition": _value(row, "condition") or None,
                "allow_self_approval": int(_value(row, "allow_self_approval") or 0),
                "transition_tasks": _value(row, "transition_tasks") or None,
            }
            for row in (_value(record, "transitions") or [])
        ],
    }


def workflow_fingerprint(record: Any) -> str:
    payload = json.dumps(workflow_shape(record), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _desired_workflows() -> dict[str, dict[str, Any]]:
    fixture_path = Path(frappe.get_app_path("connect_diagnostics_core", "fixtures", "workflow.json"))
    records = json.loads(fixture_path.read_text())
    return {str(record["name"]): record for record in records}


def _has_open_actions(doctype: str) -> bool:
    return bool(
        frappe.db.exists(
            "Workflow Action",
            {"reference_doctype": doctype, "status": "Open"},
        )
    )


def _incompatible_drafts(doctype: str, desired_states: set[str]) -> list[str]:
    if not frappe.db.has_column(doctype, "workflow_state"):
        return []
    rows = frappe.get_all(
        doctype,
        filters={"docstatus": 0, "workflow_state": ["is", "set"]},
        fields=["name", "workflow_state"],
        limit=20,
    )
    return [str(row.name) for row in rows if str(row.workflow_state) not in desired_states]


def _preflight_canonical(desired: dict[str, dict[str, Any]]) -> None:
    if set(desired) != set(CANONICAL_WORKFLOWS):
        frappe.throw(_("Workflow fixture must contain exactly the ten approved canonical routes."))

    for name, doctype in CANONICAL_WORKFLOWS.items():
        record = desired[name]
        if record.get("document_type") != doctype or int(record.get("is_active") or 0) != 1:
            frappe.throw(_("Canonical Workflow {0} has an invalid target or activation state.").format(name))

        active = set(
            frappe.get_all(
                "Workflow",
                filters={"document_type": doctype, "is_active": 1},
                pluck="name",
            )
        )
        unexpected = active - {name}
        if unexpected:
            frappe.throw(_("Workflow collision for {0}: {1}").format(doctype, ", ".join(sorted(unexpected))))

        if not frappe.db.exists("Workflow", name):
            continue
        current = frappe.get_doc("Workflow", name)
        current_hash = workflow_fingerprint(current)
        desired_hash = workflow_fingerprint(record)
        if current_hash == desired_hash:
            continue
        if current_hash != PREDECESSOR_FINGERPRINTS[name]:
            frappe.throw(_("Workflow {0} differs from every reviewed predecessor.").format(name))
        if _has_open_actions(doctype):
            frappe.throw(_("Workflow {0} has open actions and cannot be normalized.").format(name))
        desired_states = {str(row["state"]) for row in record.get("states", [])}
        if drafts := _incompatible_drafts(doctype, desired_states):
            frappe.throw(_("Workflow {0} has drafts in legacy states: {1}").format(name, ", ".join(drafts)))


def _safe_to_retire(name: str, doctype: str, expected_hash: str) -> bool:
    if not frappe.db.exists("Workflow", name):
        return False
    workflow = frappe.get_doc("Workflow", name)
    if not int(workflow.is_active or 0):
        return False
    if workflow_fingerprint(workflow) != expected_hash:
        frappe.throw(_("Retired Workflow {0} differs from the reviewed predecessor.").format(name))
    if _has_open_actions(doctype):
        frappe.throw(_("Retired Workflow {0} has open actions and requires owner disposition.").format(name))
    if frappe.db.has_column(doctype, "workflow_state") and frappe.db.exists(
        doctype,
        {"docstatus": 0, "workflow_state": ["is", "set"]},
    ):
        frappe.throw(
            _("Retired Workflow {0} has non-terminal documents and requires owner disposition.").format(name)
        )
    return True


def _configuration(record: Any) -> dict[str, Any]:
    data = {key: _value(record, key) for key in _PARENT_KEYS}
    data["states"] = [
        {key: _value(row, key) for key in _STATE_KEYS} for row in (_value(record, "states") or [])
    ]
    data["transitions"] = [
        {key: _value(row, key) for key in _TRANSITION_KEYS} for row in (_value(record, "transitions") or [])
    ]
    return data


def _save_recovery_snapshot() -> None:
    task_names = sorted(
        {
            str(transition.get("transition_tasks"))
            for workflow in _desired_workflows().values()
            for transition in workflow.get("transitions", [])
            if transition.get("transition_tasks")
        }
    )
    snapshot = {
        "schema_version": 2,
        "missing": [
            name
            for name in (*CANONICAL_WORKFLOWS, *RETIRED_WORKFLOWS)
            if not frappe.db.exists("Workflow", name)
        ],
        "workflows": [
            _configuration(frappe.get_doc("Workflow", name))
            for name in (*CANONICAL_WORKFLOWS, *RETIRED_WORKFLOWS)
            if frappe.db.exists("Workflow", name)
        ],
        "missing_transition_tasks": [
            name for name in task_names if not frappe.db.exists("Workflow Transition Tasks", name)
        ],
        "transition_tasks": [
            {
                "name": name,
                "tasks": [
                    {
                        "task": row.task,
                        "link": row.link,
                        "enabled": int(row.enabled or 0),
                        "asynchronous": int(row.asynchronous or 0),
                    }
                    for row in frappe.get_doc("Workflow Transition Tasks", name).tasks
                ],
            }
            for name in task_names
            if frappe.db.exists("Workflow Transition Tasks", name)
        ],
        "missing_custom_fields": [
            {"dt": doctype, "fieldname": str(definition["fieldname"])}
            for doctype, definitions in CUSTOM_FIELDS.items()
            for definition in definitions
            if not frappe.db.exists(
                "Custom Field",
                {"dt": doctype, "fieldname": str(definition["fieldname"])},
            )
        ],
    }
    content = json.dumps(snapshot, indent=2, sort_keys=True)
    existing = frappe.db.exists("File", {"file_name": RECOVERY_FILE, "is_private": 1})
    if existing:
        if frappe.get_doc("File", existing).get_content() != content:
            frappe.throw(_("Workflow recovery snapshot already exists with different content."))
        return
    frappe.get_doc(
        {
            "doctype": "File",
            "file_name": RECOVERY_FILE,
            "is_private": 1,
            "content": content,
        }
    ).insert(ignore_permissions=True)


def _ensure_custom_fields() -> None:
    for doctype, definitions in CUSTOM_FIELDS.items():
        for definition in definitions:
            fieldname = str(definition["fieldname"])
            existing = frappe.db.get_value(
                "Custom Field",
                {"dt": doctype, "fieldname": fieldname},
                ["fieldtype", "options"],
                as_dict=True,
            )
            if not existing:
                continue
            if existing.fieldtype != definition["fieldtype"] or (existing.options or None) != (
                definition.get("options") or None
            ):
                frappe.throw(_("Custom Field collision for {0}.{1}.").format(doctype, fieldname))
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)


def _ensure_transition_tasks(desired: dict[str, dict[str, Any]]) -> None:
    task_names = sorted(
        {
            str(transition["transition_tasks"])
            for workflow in desired.values()
            for transition in workflow.get("transitions", [])
            if transition.get("transition_tasks")
        }
    )
    hook_names = {str(item["name"]) for item in frappe.get_hooks("workflow_methods")}
    missing_hooks = set(task_names) - hook_names
    if missing_hooks:
        frappe.throw(
            _("Workflow transition methods are missing: {0}").format(", ".join(sorted(missing_hooks)))
        )
    for name in task_names:
        foreign = frappe.db.exists(
            "Workflow Transition",
            {"transition_tasks": name, "parent": ["not in", list(CANONICAL_WORKFLOWS)]},
        )
        if foreign:
            frappe.throw(_("Workflow Transition Tasks {0} is referenced outside the baseline.").format(name))
        if frappe.db.exists("Workflow Transition Tasks", name):
            task_doc = frappe.get_doc("Workflow Transition Tasks", name)
            task_doc.set(
                "tasks",
                [{"task": name, "enabled": 1, "asynchronous": 0}],
            )
            task_doc.save(ignore_permissions=True)
            continue
        frappe.get_doc(
            {
                "doctype": "Workflow Transition Tasks",
                "name": name,
                "tasks": [{"task": name, "enabled": 1, "asynchronous": 0}],
            }
        ).insert(ignore_permissions=True)


def execute() -> None:
    desired = _desired_workflows()
    _preflight_canonical(desired)
    retirements = [
        name
        for name, (doctype, expected_hash) in RETIRED_WORKFLOWS.items()
        if _safe_to_retire(name, doctype, expected_hash)
    ]
    _save_recovery_snapshot()
    _ensure_custom_fields()
    _ensure_transition_tasks(desired)
    for name in retirements:
        frappe.db.set_value("Workflow", name, "is_active", 0, update_modified=False)
