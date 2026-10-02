# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Guarded operator recovery for an unchanged v5 Purchase Order Workflow."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from connect_diagnostics_core.patches.v1_0 import normalize_workflow_baseline as v4
from connect_diagnostics_core.patches.v1_0 import upgrade_workflow_baseline_v5 as v5


def _audit() -> dict[str, Any]:
    saved = v5._artifact(v5.AUDIT_FILE, "audit")
    if saved is None:
        frappe.throw(_("Verified v5 Workflow configuration audit is missing; use site backup recovery."))
    assert saved is not None
    return saved


def _preflight() -> dict[str, Any]:
    v5._locked_config()
    v5.preflight()
    saved = v5._snapshot()
    if not saved or saved["predecessor"] != "v4":
        frappe.throw(_("The v5 Workflow has no recoverable v4 predecessor."))
    assert saved is not None
    if v5._site_shape(v5._current_blueprint()) != "v5":
        frappe.throw(_("The installed Workflow no longer has the exact reviewed v5 shape."))
    if saved["history"] != v5._history():
        frappe.throw(_("Business or Workflow Action history changed; use site backup recovery."))
    if _audit()["config_versions"] != v5._configuration_versions():
        frappe.throw(
            _("Workflow configuration audit changed after v5 verification; use site backup recovery.")
        )
    return saved


def execute() -> None:
    """Restore archived v4 configuration only inside a quiescent operator window."""
    _preflight()
    po = frappe.get_doc("Workflow", v5.PURCHASE_ORDER_WORKFLOW)
    matching = [
        row
        for row in po.transitions
        if all(row.get(key) == value for key, value in v5.RETURN_TRANSITION.items())
    ]
    if len(matching) != 1:
        frappe.throw(_("The v5 Purchase Order Return transition is missing or duplicated."))
    po.remove(matching[0])
    for index, row in enumerate(po.transitions, 1):
        row.idx = index
    po.save(ignore_permissions=True)
    archived = v4._blueprint()[0][v5.PURCHASE_ORDER_WORKFLOW]
    if v4.workflow_shape(po) != v4.workflow_shape(archived):
        frappe.throw(_("The Purchase Order Workflow did not return to the archived v4 shape."))
    v5._write_artifact(
        v5.CONSUMED_FILE,
        "consumed",
        {"schema_version": v5.SNAPSHOT_VERSION, "status": "rolled_back"},
    )
