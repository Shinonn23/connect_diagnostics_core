# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Fingerprint-guarded recovery for the PO approval route."""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from connect_diagnostics_core.patches.v1_0.configure_purchase_order_approval_boundary import (
    INACTIVE_MR_FINGERPRINT,
    MATERIAL_REQUEST_WORKFLOW,
    PURCHASE_ORDER_WORKFLOW,
    RECOVERY_FILE_NAME,
    RECOVERY_SCHEMA_VERSION,
    TARGET_PO_FINGERPRINT,
    TASKS,
    _ensure_no_open_procurement_actions,
    _get_workflow_fingerprint,
)


def _load_recovery_snapshot() -> dict[str, Any]:
    file_name = frappe.db.get_value("File", {"file_name": RECOVERY_FILE_NAME}, "name")
    if not file_name:
        frappe.throw(_("Purchase Order approval recovery snapshot was not found."))
    content = frappe.get_doc("File", file_name).get_content()
    if isinstance(content, bytes):
        content = content.decode()
    snapshot = json.loads(content)
    if snapshot.get("schema_version") != RECOVERY_SCHEMA_VERSION or snapshot.get("site") != frappe.local.site:
        frappe.throw(_("Purchase Order approval recovery snapshot does not belong to this site."))
    if set(snapshot.get("workflows", {})) != {
        PURCHASE_ORDER_WORKFLOW,
        MATERIAL_REQUEST_WORKFLOW,
    } or set(snapshot.get("transition_tasks", {})) != set(TASKS):
        frappe.throw(_("Purchase Order approval recovery snapshot is incomplete."))
    return snapshot


def _restore_configuration(doc: Any, configuration: dict[str, Any]) -> None:
    for fieldname, value in configuration.items():
        doc.set(fieldname, value)
    doc.save(ignore_permissions=True)


def _task_is_referenced(name: str) -> bool:
    return bool(frappe.db.exists("Workflow Transition", {"transition_tasks": name}))


def execute() -> None:
    """Restore the exact captured configuration without deleting audit history."""
    _ensure_no_open_procurement_actions()
    if _get_workflow_fingerprint(PURCHASE_ORDER_WORKFLOW) != TARGET_PO_FINGERPRINT:
        frappe.throw(_("Purchase Order approval recovery fingerprint does not match the reviewed route."))
    if _get_workflow_fingerprint(MATERIAL_REQUEST_WORKFLOW) != INACTIVE_MR_FINGERPRINT:
        frappe.throw(_("Material Request recovery fingerprint does not match the preserved inactive route."))

    snapshot = _load_recovery_snapshot()
    workflows = snapshot["workflows"]
    _restore_configuration(
        frappe.get_doc("Workflow", PURCHASE_ORDER_WORKFLOW),
        workflows[PURCHASE_ORDER_WORKFLOW],
    )
    _restore_configuration(
        frappe.get_doc("Workflow", MATERIAL_REQUEST_WORKFLOW),
        workflows[MATERIAL_REQUEST_WORKFLOW],
    )

    for name, prior_configuration in snapshot["transition_tasks"].items():
        if prior_configuration is None:
            if _task_is_referenced(name):
                frappe.throw(
                    _("Workflow Transition Tasks {0} is still referenced and cannot be recovered.").format(
                        name
                    )
                )
            if frappe.db.exists("Workflow Transition Tasks", name):
                frappe.delete_doc("Workflow Transition Tasks", name, ignore_permissions=True)
            continue
        task = frappe.get_doc("Workflow Transition Tasks", name)
        _restore_configuration(task, prior_configuration)
