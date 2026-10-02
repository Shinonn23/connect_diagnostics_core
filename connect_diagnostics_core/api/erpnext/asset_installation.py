# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Customer responsibility for approved, received native Asset Movements."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime

_CAPABILITY = "_connect_diagnostics_asset_installation_capability"
_MAKER_CAPTURE = "_connect_diagnostics_installation_maker_capture"


@dataclass
class _CustomerSave:
    asset: Document
    movement: str
    row: str
    old_customer: str
    new_customer: str
    kind: str
    consumed: bool = False


@dataclass
class _MakerCapture:
    doc: Document
    rows: dict[str, tuple[str, str]]
    consumed: bool = False


@contextmanager
def _customer_save_capability(
    asset: Document, movement: str, row: str, old_customer: str, new_customer: str, kind: str
) -> Iterator[None]:
    if getattr(frappe.local, _CAPABILITY, None) is not None:
        frappe.throw(_("Another Asset installation update is already active."))
    token = _CustomerSave(asset, movement, row, old_customer, new_customer, kind)
    setattr(frappe.local, _CAPABILITY, token)
    try:
        yield
        if not token.consumed:
            frappe.throw(_("Asset installation customer update was not validated."))
    finally:
        if getattr(frappe.local, _CAPABILITY, None) is token:
            delattr(frappe.local, _CAPABILITY)


def validate_customer_update(doc: Document, method: str) -> None:
    """Allow one exact submitted Asset.customer change from receiver/cancel operation."""
    del method
    before = doc.get_doc_before_save()
    if not before or before.get("customer") == doc.get("customer"):
        return
    token = getattr(frappe.local, _CAPABILITY, None)
    if (
        not isinstance(token, _CustomerSave)
        or token.consumed
        or token.asset is not doc
        or str(before.get("customer") or "") != token.old_customer
        or str(doc.get("customer") or "") != token.new_customer
    ):
        frappe.throw(_("Submitted Asset customer can change only through an approved installation receipt."))
    before_values = before.get_valid_dict()
    after_values = doc.get_valid_dict()
    for field in before_values:
        if (
            field not in {"customer", "modified", "modified_by"}
            and before_values[field] != after_values[field]
        ):
            frappe.throw(_("Installation confirmation may change only the Asset customer."))
    bound = cast(_CustomerSave, token)
    movement_state = frappe.db.get_value(
        "Asset Movement", bound.movement, ["docstatus", "workflow_state"], as_dict=True
    )
    row = frappe.db.get_value(
        "Asset Movement Item",
        {
            "name": bound.row,
            "parent": bound.movement,
            "parenttype": "Asset Movement",
            "parentfield": "assets",
            "asset": doc.name,
        },
        ["installation_customer", "accepted_by", "accepted_at"],
        as_dict=True,
    )
    if (
        not row
        or (
            bound.kind == "receipt"
            and (
                not movement_state
                or movement_state.docstatus != 1
                or movement_state.workflow_state != "Asset Movement Submitted"
                or row.installation_customer != bound.new_customer
                or row.accepted_by
                or row.accepted_at
            )
        )
        or (
            bound.kind == "cancel"
            and (
                not movement_state
                or movement_state.docstatus != 2
                or movement_state.workflow_state != "Asset Movement Cancelled"
                or not row.accepted_by
                or not row.accepted_at
            )
        )
        or bound.kind not in {"receipt", "cancel"}
    ):
        frappe.throw(_("Asset installation customer update has no current approved movement row."))
    cast(_CustomerSave, token).consumed = True


def _save_customer(asset: Document, movement: str, row: str, customer: str | None, kind: str) -> None:
    old_customer = str(asset.get("customer") or "")
    new_customer = str(customer or "")
    if old_customer == new_customer:
        return
    prior = bool(asset.flags.get("ignore_permissions"))
    with _customer_save_capability(asset, movement, row, old_customer, new_customer, kind):
        asset.set("customer", customer or None)
        try:
            asset.save(ignore_permissions=True)
        finally:
            asset.flags.ignore_permissions = prior


def _history(asset_name: str) -> list[dict[str, Any]]:
    """Lock current accepted history after the Asset mutex, including canceled rows.

    A concurrent movement may hold its parent while waiting for the Asset. NOWAIT
    makes that conflict retryable rather than reversing the normal lock order.
    """
    return frappe.db.sql(
        """
        SELECT i.name, i.parent, i.installation_customer,
               i.installation_previous_customer, i.accepted_at, m.docstatus
        FROM `tabAsset Movement Item` i
        INNER JOIN `tabAsset Movement` m ON m.name = i.parent
        WHERE i.asset = %s AND i.installation_customer IS NOT NULL
          AND i.installation_customer != '' AND i.accepted_by IS NOT NULL
          AND i.accepted_at IS NOT NULL
        ORDER BY i.accepted_at ASC, i.name ASC
        FOR UPDATE NOWAIT
        """,
        (asset_name,),
        as_dict=True,
    )


def _current_responsibility(history: list[dict[str, Any]]) -> str | None:
    if not history:
        return None
    baseline = history[0]["installation_previous_customer"] or None
    active = [entry for entry in history if int(entry["docstatus"]) == 1]
    return (active[-1]["installation_customer"] or None) if active else baseline


def validate_current_installation(
    doc: Document, *, capture: bool = False, lock_current: bool = False
) -> None:
    """Check installation shape and bind prior customer to approval evidence."""
    rows = [row for row in (doc.get("assets") or []) if row.get("installation_customer")]
    for row in rows:
        if doc.get("purpose") not in {"Issue", "Transfer"}:
            frappe.throw(_("Installation requires an Issue or Transfer Asset Movement."))
        asset_name = str(row.get("asset") or "")
        asset = frappe.db.get_value(
            "Asset",
            asset_name,
            ["company", "location", "custodian", "customer", "docstatus"],
            as_dict=True,
            for_update=lock_current,
        )
        if not asset or int(asset.docstatus) != 1 or asset.company != doc.get("company"):
            frappe.throw(_("Installation Asset must be submitted in the movement Company."))
        if not row.get("target_location") or not frappe.db.exists("Location", row.get("target_location")):
            frappe.throw(_("Installation requires an existing target Location."))
        employee = (
            frappe.db.get_value(
                "Employee",
                row.get("to_employee"),
                ["company", "status", "user_id"],
                as_dict=True,
                for_update=lock_current,
            )
            if row.get("to_employee")
            else None
        )
        if (
            not employee
            or employee.company != doc.get("company")
            or employee.status != "Active"
            or not employee.user_id
        ):
            frappe.throw(_("Installation requires an active Company Employee with a User."))
        assert employee is not None
        declared_receiver = str(row.get("receiver_user") or "")
        if declared_receiver != str(employee.user_id):
            frappe.throw(_("Installation receiver must match the receiving Employee's User."))
        user = frappe.db.get_value(
            "User",
            declared_receiver,
            ["enabled", "user_type"],
            as_dict=True,
            for_update=lock_current,
        )
        if not user or not user.enabled or user.user_type != "System User":
            frappe.throw(_("Installation requires an enabled internal receiving User."))
        disabled = frappe.db.get_value("Customer", row.get("installation_customer"), "disabled")
        if disabled is None or int(disabled):
            frappe.throw(_("Installation requires an active Customer."))
        if doc.get("purpose") == "Issue" and row.get("target_location") != asset.location:
            frappe.throw(_("Issue installation Location must equal the Asset's current Location."))
        if doc.get("purpose") == "Transfer" and str(row.get("from_employee") or "") != str(
            asset.custodian or ""
        ):
            frappe.throw(_("Transfer installation must declare the current Asset custodian."))
        previous = str(asset.customer or "")
        if capture:
            row.set("installation_previous_customer", previous or None)
        elif str(row.get("installation_previous_customer") or "") != previous:
            frappe.throw(_("Asset installation customer changed; restart approval."))


def capture_maker_customer(doc: Document) -> None:
    """Bind server-read previous Customers to this exact Maker transition object."""
    validate_current_installation(doc, capture=True)
    rows = {
        str(row.name): (
            str(row.get("installation_previous_customer") or ""),
            str(row.get("installation_customer") or ""),
        )
        for row in doc.get("assets") or []
        if row.get("installation_customer")
    }
    setattr(doc, _MAKER_CAPTURE, _MakerCapture(doc, rows))


def validate_draft_evidence(doc: Document, method: str) -> None:
    """Reject independently supplied prior-customer evidence on new drafts."""
    del method
    previous = doc.get_doc_before_save()
    old_rows = {row.name: row for row in (previous.get("assets") or [])} if previous else {}
    token = getattr(doc, _MAKER_CAPTURE, None)
    for row in doc.get("assets") or []:
        old = old_rows.get(row.name)
        old_customer = str(old.get("installation_previous_customer") or "") if old else ""
        new_customer = str(row.get("installation_previous_customer") or "")
        if old_customer == new_customer:
            continue
        if (
            not isinstance(token, _MakerCapture)
            or token.consumed
            or token.doc is not doc
            or doc.get("workflow_state") != "Asset Movement Pending Review"
            or token.rows.get(str(row.name)) != (new_customer, str(row.get("installation_customer") or ""))
        ):
            frappe.throw(_("Installation previous customer is server-controlled approval evidence."))
    if isinstance(token, _MakerCapture) and token.doc is doc:
        token.consumed = True


def confirm_customer(doc: Document, row: Any, asset: Document, acted_at: Any) -> None:
    """Apply one approved installation under the locked Asset row."""
    customer = str(row.installation_customer or "")
    if not customer:
        return
    history = _history(str(row.asset))
    if history:
        current_time = get_datetime(acted_at)
        previous_time = get_datetime(history[-1]["accepted_at"])
        if not current_time or not previous_time or current_time <= previous_time:
            frappe.throw(_("Asset installation receipt time is ambiguous; retry confirmation."))
    if str(asset.get("customer") or "") != str(row.installation_previous_customer or ""):
        frappe.throw(_("Asset installation customer changed; restart approval."))
    _save_customer(asset, str(doc.name), str(row.name), customer, "receipt")


def restore_after_cancel(doc: Document, method: str) -> None:
    """Recompute customer from remaining submitted accepted history after native cancel."""
    del method
    for row in doc.get("assets") or []:
        if not row.get("installation_customer") or not row.get("accepted_at"):
            continue
        frappe.db.get_value("Asset", row.asset, "name", for_update=True)
        asset = frappe.get_doc("Asset", row.asset)
        expected = _current_responsibility(_history(str(row.asset)))
        _save_customer(asset, str(doc.name), str(row.name), expected, "cancel")


def prevent_history_deletion(doc: Document, method: str) -> None:
    del method
    if frappe.db.exists(
        "Asset Movement Item",
        {"parent": doc.name, "installation_customer": ["is", "set"], "accepted_by": ["is", "set"]},
    ):
        frappe.throw(_("Accepted Asset installation history cannot be deleted."))
