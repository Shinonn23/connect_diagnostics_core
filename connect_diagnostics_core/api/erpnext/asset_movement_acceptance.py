# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Receiver declaration and receipt evidence; native ERPNext owns asset effects."""

from __future__ import annotations

from html import escape
from typing import Any
from uuid import uuid4

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from connect_diagnostics_core.api.erpnext import asset_installation
from connect_diagnostics_core.api.erpnext import asset_movement_workflow as workflow

EVIDENCE_FIELDS = ("accepted_by", "accepted_at")


def _receiver(row: Document | frappe._dict, *, lock_identity: bool = False) -> str:
    declared = str(row.get("receiver_user") or "")
    employee = row.get("to_employee")
    if employee:
        identity = frappe.db.get_value(
            "Employee", employee, ["status", "user_id"], as_dict=True, for_update=lock_identity
        )
        if not identity or identity.status != "Active" or not identity.user_id:
            frappe.throw(_("The receiving Employee must be active and linked to a User."))
        resolved = str(identity.user_id)
        if declared and declared != resolved:
            frappe.throw(_("The receiver must match the receiving Employee's User."))
    else:
        resolved = declared
    user = (
        frappe.db.get_value(
            "User", resolved, ["enabled", "user_type"], as_dict=True, for_update=lock_identity
        )
        if resolved
        else None
    )
    if (
        resolved in {"Guest", "Administrator"}
        or not user
        or not user.enabled
        or user.user_type != "System User"
    ):
        frappe.throw(_("Each Asset must have an enabled internal receiving User."))
    return resolved


def validate_receivers(doc: Document) -> None:
    """Resolve each recipient before the maker binds the immutable row digest."""
    rows = doc.get("assets") or []
    if not rows:
        frappe.throw(_("Asset Movement must contain an Asset with a receiver."))
    for row in rows:
        row.set("receiver_user", _receiver(row))


def validate_receipt_evidence(doc: Document, method: str | None = None) -> None:
    """Prevent parent saves from manufacturing or rewriting receipt evidence."""
    del method
    previous = doc.get_doc_before_save()
    old_rows = {row.name: row for row in (previous.get("assets") or [])} if previous else {}
    rows = doc.get("assets") or []
    for row in rows:
        old = old_rows.get(row.name)
        if any(row.get(field) != (old.get(field) if old else None) for field in EVIDENCE_FIELDS):
            frappe.throw(_("Asset receipt evidence can only be recorded by the receiving User."))
        if previous and int(previous.docstatus) == 1:
            if not old or any(
                row.get(field) != old.get(field)
                for field in (
                    *workflow._CRITICAL_ROW_FIELDS,
                    *workflow._INSTALLATION_ROW_FIELDS,
                    *EVIDENCE_FIELDS,
                )
            ):
                frappe.throw(_("Submitted Asset Movement recipients and custody cannot change."))
    if previous and int(previous.docstatus) == 1 and set(old_rows) != {row.name for row in rows}:
        frappe.throw(_("Submitted Asset Movement rows cannot change."))


def deny_standalone_row_mutation(doc: Document, method: str | None = None) -> None:
    """Native parent persistence uses db_insert/db_update, never child save APIs."""
    del doc, method
    frappe.throw(_("Asset Movement rows must be saved through their parent movement."))


@frappe.whitelist(methods=["POST"])
def confirm_receipt(movement: str, row_name: str) -> dict[str, Any]:
    user = str(frappe.session.user or "")
    if user in {"", "Guest", "Administrator"} or getattr(frappe.local, "request", None) is None:
        frappe.throw(_("Receipt confirmation requires an interactive business User request."))
    if not isinstance(movement, str) or not movement or not isinstance(row_name, str) or not row_name:
        frappe.throw(_("A movement and its Asset row are required."))
    # Fail closed on read/scope before loading row identities or evidence.
    if not frappe.has_permission("Asset Movement", "read", doc=movement):
        frappe.throw(_("You do not have permission to read this Asset Movement."), frappe.PermissionError)
    locked_movement = frappe.db.get_value(
        "Asset Movement",
        movement,
        ["name", "docstatus", "workflow_state", "company", "modified"],
        as_dict=True,
        for_update=True,
    )
    if not locked_movement:
        frappe.throw(_("Asset Movement was not found."))
    doc = frappe.get_doc("Asset Movement", movement)
    if any(
        str(doc.get(field) or "") != str(locked_movement.get(field) or "")
        for field in ("docstatus", "workflow_state", "company", "modified")
    ):
        frappe.throw(_("Asset Movement changed during receipt confirmation; retry."))
    doc.check_permission("read")
    if int(doc.docstatus) != 1 or doc.get("workflow_state") != workflow.STATE_SUBMITTED:
        frappe.throw(_("Only a submitted Asset Movement can be received."))
    asset_name = frappe.db.get_value(
        "Asset Movement Item",
        {"name": row_name, "parent": movement, "parenttype": "Asset Movement", "parentfield": "assets"},
        "asset",
    )
    if not asset_name:
        frappe.throw(_("The Asset row does not belong to this movement."))
    locked_asset = frappe.db.get_value(
        "Asset",
        asset_name,
        ["name", "company", "location", "custodian", "customer", "modified"],
        as_dict=True,
        for_update=True,
    )
    if not locked_asset:
        frappe.throw(_("The Asset was not found."))
    asset = frappe.get_doc("Asset", asset_name)
    if any(
        str(asset.get(field) or "") != str(locked_asset.get(field) or "")
        for field in ("company", "location", "custodian", "customer", "modified")
    ):
        frappe.throw(_("Asset changed during receipt confirmation; retry."))
    row = frappe.db.get_value(
        "Asset Movement Item",
        {"name": row_name, "parent": movement, "parenttype": "Asset Movement", "parentfield": "assets"},
        [
            "name",
            "asset",
            "target_location",
            "to_employee",
            "receiver_user",
            "installation_customer",
            "installation_previous_customer",
            *EVIDENCE_FIELDS,
        ],
        as_dict=True,
        for_update=True,
    )
    if (
        not row
        or row.asset != asset_name
        or not row.receiver_user
        or _receiver(row, lock_identity=True) != user
        or row.receiver_user != user
    ):
        frappe.throw(_("Only the declared receiving User can confirm this Asset."))
    if row.accepted_by or row.accepted_at:
        if row.accepted_by != user or not row.accepted_at:
            frappe.throw(_("Asset receipt evidence is inconsistent."))
        return {
            "data": {"row_name": row.name, "accepted_by": row.accepted_by, "accepted_at": row.accepted_at},
            "message": _("Asset receipt is already confirmed."),
        }
    if row.installation_customer:
        employee = frappe.db.get_value(
            "Employee", row.to_employee, ["company", "status", "user_id"], as_dict=True, for_update=True
        )
        if (
            not employee
            or employee.company != doc.company
            or employee.status != "Active"
            or employee.user_id != user
        ):
            frappe.throw(_("Installation receiving Employee is no longer valid."))
        disabled = frappe.db.get_value("Customer", row.installation_customer, "disabled")
        if disabled is None or int(disabled):
            frappe.throw(_("Installation Customer is no longer active."))
        latest = frappe.db.sql(
            """
            SELECT DISTINCT m.name, m.transaction_date FROM `tabAsset Movement Item` i
            JOIN `tabAsset Movement` m ON m.name = i.parent
            WHERE i.asset = %s AND m.company = %s AND m.docstatus = 1
            ORDER BY m.transaction_date DESC LIMIT 2
            """,
            (asset_name, doc.company),
            as_list=True,
        )
        if not latest or latest[0][0] != movement or (len(latest) > 1 and latest[1][1] == latest[0][1]):
            frappe.throw(_("Installation movement is not the current Asset movement."))
        if asset.get("location") != row.target_location or asset.get("custodian") != row.to_employee:
            frappe.throw(_("Asset Location or custodian changed after installation approval."))
    acted_at = now_datetime()
    savepoint = f"asset_receipt_{uuid4().hex}"
    frappe.db.savepoint(savepoint)
    try:
        asset_installation.confirm_customer(doc, row, asset, acted_at)
        frappe.db.set_value("Asset Movement Item", row.name, {"accepted_by": user, "accepted_at": acted_at})
        doc.add_comment(
            "Info",
            _("Asset {0} received by {1} (row {2}).").format(
                escape(str(row.asset)), escape(user), escape(str(row.name))
            ),
        )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return {
        "data": {"row_name": row.name, "accepted_by": user, "accepted_at": acted_at},
        "message": _("Asset receipt confirmed."),
    }
