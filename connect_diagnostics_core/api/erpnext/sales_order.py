# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now

from connect_diagnostics_core.api.erpnext import dksh_item_mapping
from connect_diagnostics_core.config.dksh import (
    DKSH_STANDARD_SELLING_PRICE_LIST,
    SAP_KEYED_BY_FIELD,
    SAP_KEYED_ON_FIELD,
    SAP_ORDER_CORRECTION_REASON_FIELD,
    SAP_ORDER_NO_FIELD,
    SAP_ORDER_STATUS_FIELD,
    SAP_ORDER_STATUS_KEYED,
    SAP_ORDER_STATUS_PENDING,
)

DKSH_ITEM_MAPPING_QUERY = "connect_diagnostics_core.api.erpnext.sales_order.get_active_dksh_item_mapping"
SAP_ORDER_FIELDS = (
    SAP_ORDER_STATUS_FIELD,
    SAP_ORDER_NO_FIELD,
    SAP_KEYED_BY_FIELD,
    SAP_KEYED_ON_FIELD,
    SAP_ORDER_CORRECTION_REASON_FIELD,
)
SALES_ORDER_LOCK_FIELDS = ("company", "docstatus", SAP_ORDER_STATUS_FIELD, SAP_ORDER_NO_FIELD)


def before_validate(doc: Document, method: str | None = None) -> None:
    """Resolve the visible DKSH mapping to ERPNext's internal Item Code."""
    company = _text(doc.get("company"))
    if not dksh_item_mapping.is_dksh_company(company):
        if _docstatus(doc) == 0:
            _clear_sap_order_fields(doc)
        for row in doc.get("items", []):
            row.set("dksh_item_mapping", None)
        return

    _apply_dksh_sales_order_defaults(doc)
    for row in doc.get("items", []):
        mapping_name = _text(row.get("dksh_item_mapping"))
        if not mapping_name:
            frappe.throw(_("Item Code must be selected from an active DKSH Item Mapping."))
        row.set(
            "item_code",
            _get_active_mapping_item(mapping_name, company, for_update=True),
        )


def validate(doc: Document, method: str | None = None) -> None:
    """Prevent a Company switch from changing how existing Item rows are interpreted."""
    previous = cast(Document | None, doc.get_doc_before_save())
    _validate_sap_order_fields(doc, previous)
    if not previous:
        return
    if _text(previous.get("company")) == _text(doc.get("company")):
        return
    if doc.get("items", []):
        frappe.throw(_("Delete all Items before changing Company."))


def before_update_after_submit(doc: Document, method: str | None = None) -> None:
    """Protect SAP fields when Frappe saves an already-submitted Sales Order."""
    previous = cast(Document | None, doc.get_doc_before_save())
    _validate_sap_order_fields(doc, previous)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_active_dksh_item_mapping(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict[str, Any] | str | None = None,
    **kwargs: Any,
) -> list[tuple[str, str, str]]:
    """Return active mappings as DKSH code plus Item Name, never as CD Item Code."""
    frappe.has_permission(dksh_item_mapping.DKSH_ITEM_MAPPING_DOCTYPE, "read", throw=True)
    query_filters = _parse_filters(filters)
    if not dksh_item_mapping.is_dksh_company(_text(query_filters.get("company"))):
        return []

    return cast(
        list[tuple[str, str, str]],
        frappe.db.sql(
            """
            SELECT mapping.name, mapping.dksh_item_code, item.item_name
            FROM `tabDKSH Item Mapping` mapping
            INNER JOIN `tabItem` item ON item.name = mapping.item
            WHERE mapping.active = 1
              AND mapping.mapping_state = %(active_state)s
              AND item.disabled = 0
              AND (
                  mapping.dksh_item_code LIKE %(txt)s
                  OR item.item_name LIKE %(txt)s
              )
            ORDER BY mapping.dksh_item_code ASC
            LIMIT %(start)s, %(page_len)s
            """,
            {
                "active_state": dksh_item_mapping.ACTIVE_STATE,
                "txt": f"%{txt}%",
                "start": cint(start),
                "page_len": cint(page_len),
            },
        ),
    )


@frappe.whitelist()
def get_sales_order_item_mode(company: str) -> dict[str, Any]:
    """Return the company-specific Item Code mode for the Sales Order grid."""
    frappe.has_permission("Sales Order", "read", throw=True)
    is_dksh = dksh_item_mapping.is_dksh_company(_text(company))
    data: dict[str, Any] = {"is_dksh_company": is_dksh}
    if is_dksh:
        data.update(
            {
                "selling_price_list": DKSH_STANDARD_SELLING_PRICE_LIST,
                "skip_delivery_note": 1,
                "sap_order_statuses": {
                    "pending": SAP_ORDER_STATUS_PENDING,
                    "keyed": SAP_ORDER_STATUS_KEYED,
                },
            }
        )
    return {
        "data": data,
        "message": "DKSH Item Code mode is active." if is_dksh else "Standard Item Code mode is active.",
    }


@frappe.whitelist()
def get_active_dksh_item_mapping_details(mapping: str, company: str) -> dict[str, Any]:
    """Return the hidden internal Item Code for a selected active DKSH mapping."""
    frappe.has_permission("Sales Order", "read", throw=True)
    item_code = _get_active_mapping_item(_text(mapping), _text(company))
    return {
        "data": {"item_code": item_code},
        "message": "Active DKSH Item Mapping resolved.",
    }


@frappe.whitelist()
def mark_as_keyed_in_sap(sales_order: str, sap_order_no: str) -> dict[str, Any]:
    """Record the first SAP order number for a submitted DKSH Sales Order."""
    sales_order_name = _required_text(sales_order, "Sales Order")
    sap_order_number = _required_text(sap_order_no, "SAP Order No.")
    locked_order = _lock_submitted_dksh_sales_order(sales_order_name)
    if _text(locked_order.get(SAP_ORDER_STATUS_FIELD)) != SAP_ORDER_STATUS_PENDING:
        frappe.throw(_("This Sales Order is not pending SAP keying."))

    sap_order = cast(Document, frappe.get_doc("Sales Order", sales_order_name))
    sap_order.set(SAP_ORDER_NO_FIELD, sap_order_number)
    sap_order.set(SAP_ORDER_STATUS_FIELD, SAP_ORDER_STATUS_KEYED)
    sap_order.set(SAP_KEYED_BY_FIELD, frappe.session.user)
    sap_order.set(SAP_KEYED_ON_FIELD, now())
    sap_order.set(SAP_ORDER_CORRECTION_REASON_FIELD, None)
    sap_order.flags.allow_sap_order_update = True
    sap_order.save()

    return _sap_order_response(sap_order, _("Sales Order marked as keyed in SAP."))


@frappe.whitelist()
def correct_sap_order_no(
    sales_order: str,
    sap_order_no: str,
    correction_reason: str,
) -> dict[str, Any]:
    """Correct a keyed SAP order number and retain the change in Version history."""
    sales_order_name = _required_text(sales_order, "Sales Order")
    sap_order_number = _required_text(sap_order_no, "SAP Order No.")
    reason = _required_text(correction_reason, "SAP Order Correction Reason")
    locked_order = _lock_submitted_dksh_sales_order(sales_order_name)
    if _text(locked_order.get(SAP_ORDER_STATUS_FIELD)) != SAP_ORDER_STATUS_KEYED:
        frappe.throw(_("This Sales Order has not been keyed in SAP."))
    if not _text(locked_order.get(SAP_ORDER_NO_FIELD)):
        frappe.throw(_("This Sales Order does not have an SAP Order No. to correct."))

    sap_order = cast(Document, frappe.get_doc("Sales Order", sales_order_name))
    sap_order.set(SAP_ORDER_NO_FIELD, sap_order_number)
    sap_order.set(SAP_ORDER_CORRECTION_REASON_FIELD, reason)
    sap_order.flags.allow_sap_order_update = True
    sap_order.save()

    return _sap_order_response(sap_order, _("SAP Order No. corrected."))


def _get_active_mapping_item(mapping_name: str, company: str, *, for_update: bool = False) -> str:
    if not dksh_item_mapping.is_dksh_company(company):
        frappe.throw(_("DKSH Item Mapping can only be selected for the configured DKSH Company."))

    mapping = cast(
        dict[str, Any] | None,
        frappe.db.get_value(
            dksh_item_mapping.DKSH_ITEM_MAPPING_DOCTYPE,
            mapping_name,
            ["item", "active", "mapping_state"],
            as_dict=True,
            for_update=for_update,
        ),
    )
    if not mapping or not int(mapping.get("active") or 0):
        frappe.throw(_("The selected DKSH Item Mapping is not active."))
    mapping = cast(dict[str, Any], mapping)
    if _text(mapping.get("mapping_state")) != dksh_item_mapping.ACTIVE_STATE:
        frappe.throw(_("The selected DKSH Item Mapping is not in the Active state."))

    item_code = _text(mapping.get("item"))
    item_disabled = frappe.db.get_value("Item", item_code, "disabled") if item_code else 1
    if not item_code or int(item_disabled or 0):
        frappe.throw(_("The Item linked to the selected DKSH Item Mapping is unavailable."))
    return item_code


def _apply_dksh_sales_order_defaults(doc: Document) -> None:
    """Set values DKSH owns before ERPNext resolves prices and validates the Order."""
    doc.set("selling_price_list", DKSH_STANDARD_SELLING_PRICE_LIST)
    doc.set("skip_delivery_note", 1)

    previous = cast(Document | None, doc.get_doc_before_save())
    if not _is_new_or_draft_sales_order(doc, previous):
        return

    doc.set(SAP_ORDER_STATUS_FIELD, SAP_ORDER_STATUS_PENDING)
    for fieldname in SAP_ORDER_FIELDS:
        if fieldname != SAP_ORDER_STATUS_FIELD:
            doc.set(fieldname, None)


def _clear_sap_order_fields(doc: Document) -> None:
    for fieldname in SAP_ORDER_FIELDS:
        doc.set(fieldname, None)


def _is_new_or_draft_sales_order(doc: Document, previous: Document | None) -> bool:
    return not previous or _docstatus(doc) == 0 or _docstatus(previous) == 0


def _validate_sap_order_fields(doc: Document, previous: Document | None) -> None:
    if (
        not previous
        or _docstatus(doc) != 1
        or _docstatus(previous) == 0
        or not _sap_order_fields_changed(doc, previous)
        or doc.flags.get("allow_sap_order_update")
    ):
        return
    frappe.throw(_("SAP order fields can only be updated through the SAP keying actions."))


def _sap_order_fields_changed(doc: Document, previous: Document) -> bool:
    return any(_text(doc.get(fieldname)) != _text(previous.get(fieldname)) for fieldname in SAP_ORDER_FIELDS)


def _lock_submitted_dksh_sales_order(sales_order: str) -> dict[str, Any]:
    frappe.has_permission("Sales Order", "write", sales_order, throw=True)
    locked_order = cast(
        dict[str, Any] | None,
        frappe.db.get_value(
            "Sales Order",
            sales_order,
            list(SALES_ORDER_LOCK_FIELDS),
            as_dict=True,
            for_update=True,
        ),
    )
    if not locked_order:
        frappe.throw(_("Sales Order {0} does not exist.").format(frappe.bold(sales_order)))
    locked_order = cast(dict[str, Any], locked_order)
    if not dksh_item_mapping.is_dksh_company(_text(locked_order.get("company"))):
        frappe.throw(_("SAP keying is only available for DKSH Sales Orders."))
    if int(locked_order.get("docstatus") or 0) != 1:
        frappe.throw(_("Only submitted Sales Orders can be keyed in SAP."))

    return locked_order


def _sap_order_response(sales_order: Document, message: str) -> dict[str, Any]:
    return {
        "data": {
            "sales_order": sales_order.name,
            "sap_order_status": sales_order.get(SAP_ORDER_STATUS_FIELD),
            "sap_order_no": sales_order.get(SAP_ORDER_NO_FIELD),
            "sap_keyed_by": sales_order.get(SAP_KEYED_BY_FIELD),
            "sap_keyed_on": sales_order.get(SAP_KEYED_ON_FIELD),
            "sap_order_correction_reason": sales_order.get(SAP_ORDER_CORRECTION_REASON_FIELD),
        },
        "message": message,
    }


def _required_text(value: object, label: str) -> str:
    text = _text(value)
    if not text:
        frappe.throw(_("{0} is required.").format(label))
    return text


def _parse_filters(filters: dict[str, Any] | str | None) -> dict[str, Any]:
    if not filters:
        return {}
    if isinstance(filters, str):
        return cast(dict[str, Any], json.loads(filters))
    return filters


def _text(value: object) -> str:
    return str(value or "").strip()


def _docstatus(doc: Document) -> int:
    return int(doc.get("docstatus") or 0)
