# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.model.rename_doc import rename_doc
from frappe.utils import now

from connect_diagnostics_core.config.dksh import DKSH_COMPANY

DKSH_ITEM_MAPPING_DOCTYPE = "DKSH Item Mapping"
DKSH_ITEM_COORDINATOR_ROLE = "DKSH Item Coordinator"

CHANNEL_CD = "CD"
CHANNEL_DKSH = "DKSH"
CHANNEL_BOTH = "CD and DKSH"

DRAFT_STATE = "DKSH Item Mapping Draft"
PENDING_COORDINATOR_REVIEW_STATE = "Pending DKSH Coordinator Review"
AWAITING_DKSH_CODE_STATE = "Awaiting DKSH Code"
ACTIVE_STATE = "DKSH Item Mapping Active"
RETURNED_FOR_CORRECTION_STATE = "DKSH Item Mapping Returned for Correction"
REJECTED_STATE = "DKSH Item Mapping Rejected"

PENDING_ITEM_SERIES = "DKSH-PENDING-.#####"

ITEM_MASTER_FIELDS = (
    "item_name",
    "item_group",
    "stock_uom",
    "mat_group_code",
    "mat_group4_code",
    "material_type_code",
    "supplier_product_code",
)
REQUIRED_DKSH_ONLY_FIELDS = {
    "item_name": "Item Name",
    "item_group": "Item Group",
    "stock_uom": "Stock UOM",
    "mat_group_code": "Mat Group Code",
    "mat_group4_code": "Mat Group4 Code",
    "material_type_code": "Material Type Code",
    "supplier_product_code": "Supplier Product Code",
}
MAPPING_IMMUTABLE_FIELDS = ("item", "item_channel", *ITEM_MASTER_FIELDS)


def autoname(doc: Document, method: str | None = None) -> None:
    """Name a mapping after its Item, or reserve a pending DKSH-only Item code."""
    item_code = _text(doc.get("item"))
    doc.name = item_code or make_autoname(PENDING_ITEM_SERIES)


def before_validate(doc: Document, method: str | None = None) -> None:
    """Normalize the managed state before workflow validation."""
    if not _text(doc.get("mapping_state")):
        doc.set("mapping_state", DRAFT_STATE)

    doc.set("item_channel", _text(doc.get("item_channel")) or CHANNEL_BOTH)
    dksh_item_code = _text(doc.get("dksh_item_code"))
    doc.set("dksh_item_code", dksh_item_code or None)
    doc.set("active", int(_text(doc.get("mapping_state")) == ACTIVE_STATE))


def validate(doc: Document, method: str | None = None) -> None:
    """Enforce the DKSH Item Mapping workflow and master-data invariants."""
    state = _text(doc.get("mapping_state"))
    _validate_state(state)

    previous = cast(Document | None, doc.get_doc_before_save())
    previous_state = _text(previous.get("mapping_state")) if previous else ""
    _validate_immutable_mapping_fields(doc, previous, previous_state)
    _validate_dksh_item_code_state(doc, previous, previous_state, state)

    if state == ACTIVE_STATE:
        _validate_active_mapping(doc)

    if not previous_state or previous_state == state:
        return

    if state == PENDING_COORDINATOR_REVIEW_STATE:
        _validate_submission(doc, previous_state)
        doc.set("correction_reason", None)
        doc.set("rejection_reason", None)
    elif state == AWAITING_DKSH_CODE_STATE:
        _send_request_to_dksh(doc)
    elif state == RETURNED_FOR_CORRECTION_STATE:
        _require_text(doc, "correction_reason", "Correction Reason")
    elif state == REJECTED_STATE:
        _require_text(doc, "rejection_reason", "Rejection Reason")
    elif state == ACTIVE_STATE:
        doc.flags.activate_dksh_item_mapping = True


def on_update(doc: Document, method: str | None = None) -> None:
    """Finalize an activation after the workflow state itself is saved."""
    if not doc.flags.get("activate_dksh_item_mapping"):
        return
    _activate_mapping(doc)


def get_dksh_company() -> str:
    """Return the approved fixed Company for the DKSH sales channel."""
    return DKSH_COMPANY


def is_dksh_company(company: str) -> bool:
    """Return whether a transaction Company is the fixed DKSH Company."""
    return bool(company and company == DKSH_COMPANY)


def _validate_state(state: str) -> None:
    valid_states = {
        DRAFT_STATE,
        PENDING_COORDINATOR_REVIEW_STATE,
        AWAITING_DKSH_CODE_STATE,
        ACTIVE_STATE,
        RETURNED_FOR_CORRECTION_STATE,
        REJECTED_STATE,
    }
    if state not in valid_states:
        frappe.throw(_("DKSH Item Mapping has an invalid workflow state."))


def _validate_immutable_mapping_fields(
    doc: Document,
    previous: Document | None,
    previous_state: str,
) -> None:
    if not previous or previous_state in {DRAFT_STATE, RETURNED_FOR_CORRECTION_STATE}:
        return

    for fieldname in MAPPING_IMMUTABLE_FIELDS:
        if _text(doc.get(fieldname)) != _text(previous.get(fieldname)):
            frappe.throw(_("{0} cannot be changed after coordinator review begins.").format(fieldname))


def _validate_dksh_item_code_state(
    doc: Document,
    previous: Document | None,
    previous_state: str,
    state: str,
) -> None:
    dksh_item_code = _text(doc.get("dksh_item_code"))
    if state not in {AWAITING_DKSH_CODE_STATE, ACTIVE_STATE} and dksh_item_code:
        frappe.throw(_("DKSH Item Code can only be recorded after the request is sent to DKSH."))
    if (
        previous
        and previous_state == ACTIVE_STATE
        and dksh_item_code != _text(previous.get("dksh_item_code"))
    ):
        frappe.throw(_("DKSH Item Code cannot be changed after activation."))


def _validate_submission(doc: Document, previous_state: str = "") -> None:
    item_channel = _text(doc.get("item_channel"))
    item_code = _text(doc.get("item"))
    if item_channel == CHANNEL_BOTH:
        if not item_code:
            frappe.throw(_("An existing CD Item is required for a CD and DKSH mapping request."))
        _prepare_existing_cd_item(doc, item_code)
        return

    if item_channel == CHANNEL_DKSH:
        if item_code and not _is_returned_pending_dksh_item(doc, item_code, previous_state):
            frappe.throw(_("A DKSH-only mapping request must not select an existing Item."))
        _validate_dksh_only_item_fields(doc)
        return

    frappe.throw(_("Item Channel must be CD and DKSH or DKSH for a DKSH Item Mapping."))


def _is_returned_pending_dksh_item(doc: Document, item_code: str, previous_state: str) -> bool:
    """Allow only the disabled Item created by this mapping to be resubmitted."""
    if (
        previous_state != RETURNED_FOR_CORRECTION_STATE
        or item_code != doc.name
        or not _text(doc.get("request_sent_on"))
    ):
        return False

    pending_item = cast(
        dict[str, Any] | None,
        frappe.db.get_value("Item", item_code, ["item_channel", "disabled"], as_dict=True),
    )
    return bool(
        pending_item
        and _text(pending_item.get("item_channel")) == CHANNEL_DKSH
        and int(pending_item.get("disabled") or 0)
    )


def _prepare_existing_cd_item(doc: Document, item_code: str) -> None:
    item_doc = cast(Document, frappe.get_doc("Item", item_code))
    item_channel = _text(item_doc.get("item_channel"))
    if item_channel not in {CHANNEL_CD, CHANNEL_BOTH}:
        frappe.throw(_("Only a CD Item can be submitted for a CD and DKSH mapping request."))
    if int(item_doc.get("disabled") or 0):
        frappe.throw(_("The selected CD Item must be enabled before it is submitted to DKSH."))

    if item_channel == CHANNEL_CD:
        item_doc.set("item_channel", CHANNEL_BOTH)
        item_doc.save(ignore_permissions=True)


def _validate_dksh_only_item_fields(doc: Document) -> None:
    for fieldname, label in REQUIRED_DKSH_ONLY_FIELDS.items():
        _require_text(doc, fieldname, label)


def _send_request_to_dksh(doc: Document) -> None:
    item_doc = _ensure_item_master(doc)
    if _text(doc.get("item_channel")) != CHANNEL_DKSH:
        _copy_item_snapshot(doc, item_doc)
    doc.set("request_sent_on", now())
    doc.set("request_sent_by", frappe.session.user)


def _ensure_item_master(doc: Document) -> Document:
    item_code = _text(doc.get("item"))
    if _text(doc.get("item_channel")) == CHANNEL_DKSH and not item_code:
        item_code = doc.name
        item_doc = cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": item_code,
                    "item_channel": CHANNEL_DKSH,
                    "disabled": 1,
                    "is_stock_item": 1,
                    **_item_master_values(doc),
                }
            ),
        )
        item_doc.insert(ignore_permissions=True)
        _persist_dksh_only_item_values(item_doc, doc)
        doc.set("item", item_doc.name)
        return item_doc

    if not item_code:
        frappe.throw(_("An Item must exist before the DKSH request can be sent."))

    item_doc = cast(Document, frappe.get_doc("Item", item_code))
    if _text(doc.get("item_channel")) == CHANNEL_DKSH:
        for fieldname, value in _item_master_values(doc).items():
            item_doc.set(fieldname, value)
        item_doc.set("disabled", 1)
        item_doc.set("item_channel", CHANNEL_DKSH)
        item_doc.save(ignore_permissions=True)
        _persist_dksh_only_item_values(item_doc, doc)
    return item_doc


def _item_master_values(doc: Document) -> dict[str, Any]:
    return {fieldname: doc.get(fieldname) for fieldname in ITEM_MASTER_FIELDS}


def _persist_dksh_only_item_values(item_doc: Document, mapping_doc: Document) -> None:
    """Keep the approved mapping values when Item fetch-from fields are empty."""
    values = _item_master_values(mapping_doc)
    frappe.db.set_value("Item", item_doc.name, values, update_modified=False)
    for fieldname, value in values.items():
        item_doc.set(fieldname, value)


def _copy_item_snapshot(doc: Document, item_doc: Document) -> None:
    for fieldname in ITEM_MASTER_FIELDS:
        doc.set(fieldname, item_doc.get(fieldname))


def _validate_active_mapping(doc: Document) -> None:
    _require_text(doc, "dksh_item_code", "DKSH Item Code")
    item_code = _text(doc.get("item"))
    if not item_code or not frappe.db.exists("Item", item_code):
        frappe.throw(_("An Item must exist before a DKSH Item Mapping can be activated."))

    duplicate_mapping = frappe.db.get_value(
        DKSH_ITEM_MAPPING_DOCTYPE,
        {"dksh_item_code": _text(doc.get("dksh_item_code")), "name": ["!=", doc.name]},
        "name",
    )
    if duplicate_mapping:
        frappe.throw(
            _("DKSH Item Code {0} is already assigned to DKSH Item Mapping {1}.").format(
                frappe.bold(_text(doc.get("dksh_item_code"))),
                frappe.bold(_text(duplicate_mapping)),
            )
        )


def _activate_mapping(doc: Document) -> None:
    item_code = _text(doc.get("item"))
    dksh_item_code = _text(doc.get("dksh_item_code"))
    if _text(doc.get("item_channel")) == CHANNEL_DKSH and item_code == doc.name:
        _rename_pending_item_and_mapping(doc, dksh_item_code)
        item_code = dksh_item_code

    item_doc = cast(Document, frappe.get_doc("Item", item_code))
    item_doc.set("item_channel", _text(doc.get("item_channel")))
    item_doc.set("disabled", 0)
    item_doc.set("has_dksh_code", 1)
    item_doc.set("item_code_is_dksh_code", int(_text(doc.get("item_channel")) == CHANNEL_DKSH))
    item_doc.set("dksh_item_code", dksh_item_code)
    item_doc.save(ignore_permissions=True)
    if _text(doc.get("item_channel")) == CHANNEL_DKSH:
        _persist_dksh_only_item_values(item_doc, doc)


def _rename_pending_item_and_mapping(doc: Document, dksh_item_code: str) -> None:
    old_mapping_name = doc.name
    old_item_code = _text(doc.get("item"))
    if dksh_item_code == old_item_code:
        return
    if frappe.db.exists("Item", dksh_item_code):
        frappe.throw(_("DKSH Item Code {0} already exists as an Item.").format(frappe.bold(dksh_item_code)))
    if frappe.db.exists(DKSH_ITEM_MAPPING_DOCTYPE, dksh_item_code):
        frappe.throw(
            _("DKSH Item Code {0} already exists as a DKSH Item Mapping.").format(frappe.bold(dksh_item_code))
        )

    rename_doc(
        "Item",
        old_item_code,
        dksh_item_code,
        force=True,
        ignore_permissions=True,
        show_alert=False,
        rebuild_search=False,
    )
    new_mapping_name = rename_doc(
        DKSH_ITEM_MAPPING_DOCTYPE,
        old_mapping_name,
        dksh_item_code,
        force=True,
        ignore_permissions=True,
        show_alert=False,
        rebuild_search=False,
    )
    doc.name = new_mapping_name
    doc.set("item", dksh_item_code)


def _require_text(doc: Document, fieldname: str, label: str) -> None:
    if not _text(doc.get(fieldname)):
        frappe.throw(_("{0} is required.").format(label))


def _text(value: object) -> str:
    return str(value or "").strip()
