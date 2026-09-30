# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Restore the inventoried local.test PI Workflow without deleting audit evidence."""

from __future__ import annotations

import json

import frappe
from frappe import _

from connect_diagnostics_core.patches.v1_0.add_purchase_invoice_approval_controls import (
    TRIAL_FINGERPRINT,
    _workflow_fingerprint,
)

_BASELINE_STATES = (
    ("Purchase Invoice Draft", "0", "Accounts User"),
    ("Purchase Invoice Pending Review", "0", "Accounts User"),
    ("Purchase Invoice Approved", "0", "Accounts Manager"),
    ("Purchase Invoice Rejected", "0", "Accounts User"),
    ("Purchase Invoice Submitted", "1", "Accounts Manager"),
    ("Purchase Invoice Cancelled", "2", "Accounts Manager"),
)
_BASELINE_TRANSITIONS = (
    (
        "Purchase Invoice Draft",
        "Submit Purchase Invoice for Review",
        "Purchase Invoice Pending Review",
        "Accounts User",
    ),
    (
        "Purchase Invoice Pending Review",
        "Approve Purchase Invoice",
        "Purchase Invoice Approved",
        "Accounts Manager",
    ),
    (
        "Purchase Invoice Pending Review",
        "Reject Purchase Invoice",
        "Purchase Invoice Rejected",
        "Accounts Manager",
    ),
    ("Purchase Invoice Approved", "Post Purchase Invoice", "Purchase Invoice Submitted", "Accounts Manager"),
    (
        "Purchase Invoice Submitted",
        "Cancel Purchase Invoice",
        "Purchase Invoice Cancelled",
        "Accounts Manager",
    ),
)


def execute() -> None:
    """Restore only a matching empty trial route; keep additive fields/tasks/history."""
    if frappe.local.site != "local.test":
        frappe.throw(_("Purchase Invoice trial recovery is authorized only on local.test."))
    if frappe.db.count("Purchase Invoice") or frappe.db.count(
        "Workflow Action", {"reference_doctype": "Purchase Invoice"}
    ):
        frappe.throw(_("Purchase Invoice trial recovery requires no PI documents or Workflow Actions."))
    workflow = frappe.get_doc("Workflow", "Connect Purchase Invoice Blueprint")
    fingerprint = _workflow_fingerprint(json.loads(frappe.as_json(workflow.as_dict())))
    if fingerprint != TRIAL_FINGERPRINT:
        frappe.throw(_("Purchase Invoice trial recovery fingerprint does not match the reviewed route."))
    workflow.set(
        "states",
        [
            {"state": state, "doc_status": doc_status, "allow_edit": allow_edit}
            for state, doc_status, allow_edit in _BASELINE_STATES
        ],
    )
    workflow.set(
        "transitions",
        [
            {
                "state": state,
                "action": action,
                "next_state": next_state,
                "allowed": allowed,
                "allow_self_approval": 0,
            }
            for state, action, next_state, allowed in _BASELINE_TRANSITIONS
        ],
    )
    workflow.save(ignore_permissions=True)
