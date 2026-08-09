# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Policy-driven medical-device validation and immutable transaction snapshots."""

from __future__ import annotations

from datetime import date
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

from connect_diagnostics_core.api.erpnext import regulatory

SETTINGS_DOCTYPE = "Medical Device Regulatory Settings"
OVERRIDE_DOCTYPE = "Medical Device Regulatory Override"
OUTBOUND_DOCTYPES = frozenset({"Delivery Note", "Sales Invoice"})
SETTINGS_FIELDS = (
    "validate_on_purchase_order",
    "validate_on_purchase_receipt",
    "validate_on_stock_entry",
    "validate_on_sales_order",
    "validate_on_delivery_note",
    "validate_on_sales_invoice",
    "missing_registration_action",
    "expired_registration_action",
    "suspended_registration_action",
    "revoked_registration_action",
    "missing_newcode_action",
    "manufacturer_mismatch_action",
    "expired_registration_existing_stock_policy",
)


def validate_warning_transaction(doc: Document, method: str | None = None) -> None:
    """Surface PO/SO expected-date risk as warnings without blocking document saves."""
    del method
    _validate(doc, warn_only=True)


def validate_transaction(doc: Document, method: str | None = None) -> None:
    """Apply configured block/warning policy before submit for stock-affecting documents."""
    del method
    _validate(doc, warn_only=False)


def capture_transaction_snapshot(doc: Document, method: str | None = None) -> None:
    """Persist the regulatory facts resolved for each row at this transaction date."""
    del method
    override = _get_approved_override(doc)
    for row in doc.get("items", []):
        item_code = cast(str, row.get("item_code") or "")
        if not item_code or not _item_requires_registration(item_code):
            continue
        mapping = regulatory.get_mapping_at_date(item_code, _coverage_date(doc, row))
        row.update(
            {
                "regulatory_registration": mapping.get("registration", "") if mapping else "",
                "regulatory_newcode": mapping.get("newcode", "") if mapping else "",
                "regulatory_identifier": mapping.get("identifier", "") if mapping else "",
                "regulatory_manufacturer": mapping.get("physical_manufacturer", "") if mapping else "",
                "regulatory_manufacturer_country": _manufacturer_country(mapping),
                "regulatory_batch_no": row.get("batch_no") or "",
                "regulatory_serial_no": row.get("serial_no") or "",
                "regulatory_product_expiry_date": _batch_expiry(row.get("batch_no")),
                "regulatory_reporting_uom": row.get("uom") or row.get("stock_uom") or "",
                "regulatory_reporting_qty": row.get("qty") or 0,
                "regulatory_override": override or "",
            }
        )


def _validate(doc: Document, *, warn_only: bool) -> None:
    settings = _settings()
    if not _validation_enabled(doc.doctype, settings):
        return
    override = _get_approved_override(doc)
    messages: list[str] = []
    for row in doc.get("items", []):
        item_code = cast(str, row.get("item_code") or "")
        if not item_code or not _item_requires_registration(item_code):
            continue
        coverage_date = _coverage_date(doc, row)
        mapping = regulatory.get_mapping_at_date(item_code, coverage_date)
        messages.extend(_evaluate_row(doc, row, mapping, coverage_date, settings))
    if not messages:
        return
    if override:
        frappe.msgprint(
            _("Medical-device regulatory policy was overridden by {0}: {1}").format(
                frappe.bold(override), "; ".join(messages)
            ),
            title=_("Regulatory override applied"),
            indicator="orange",
        )
        return
    if warn_only or all(message.startswith("Warning:") for message in messages):
        frappe.msgprint(
            "<br>".join(messages), title=_("Medical-device regulatory warning"), indicator="orange"
        )
        return
    frappe.throw("<br>".join(messages), title=_("Medical-device regulatory requirement not met"))


def _evaluate_row(
    doc: Document,
    row: Document,
    mapping: dict[str, str] | None,
    coverage_date: date,
    settings: dict[str, Any],
) -> list[str]:
    item_code = cast(str, row.get("item_code") or "")
    prefix = _("Row {0} ({1})").format(row.idx or "?", frappe.bold(item_code))
    if not mapping:
        return [
            _message(
                prefix,
                _("has no registration mapping effective on {0}.").format(coverage_date),
                settings["missing_registration_action"],
            )
        ]
    messages: list[str] = []
    if not mapping.get("newcode"):
        messages.append(
            _message(
                prefix, _("has no NEWCODE in its registration mapping."), settings["missing_newcode_action"]
            )
        )
    official_status = mapping.get("official_status") or ""
    if official_status == "Suspended":
        messages.append(
            _message(
                prefix, _("is mapped to a suspended registration."), settings["suspended_registration_action"]
            )
        )
    elif official_status == "Revoked":
        messages.append(
            _message(
                prefix, _("is mapped to a revoked registration."), settings["revoked_registration_action"]
            )
        )
    elif official_status == "Expired":
        messages.append(
            _message(
                prefix, _("is mapped to an expired registration."), _expired_action(doc.doctype, settings)
            )
        )
    elif official_status != "Active":
        messages.append(
            _message(
                prefix, _("is not mapped to an active registration."), settings["missing_registration_action"]
            )
        )
    expiry_date = getdate(mapping.get("expiry_date") or "")
    if expiry_date and expiry_date < coverage_date:
        action = _expired_action(doc.doctype, settings)
        messages.append(_message(prefix, _("registration expired on {0}.").format(expiry_date), action))
    transaction_manufacturer = cast(str, row.get("manufacturer") or "")
    mapped_manufacturer = mapping.get("physical_manufacturer") or ""
    if transaction_manufacturer and mapped_manufacturer and transaction_manufacturer != mapped_manufacturer:
        messages.append(
            _message(
                prefix,
                _("manufacturer {0} does not match registration manufacturer {1}.").format(
                    frappe.bold(transaction_manufacturer), frappe.bold(mapped_manufacturer)
                ),
                settings["manufacturer_mismatch_action"],
            )
        )
    return [message for message in messages if message]


def _message(prefix: str, detail: str, action: str) -> str:
    if action == "Ignore":
        return ""
    severity = "Warning:" if action == "Warning" else "Block:"
    return f"{severity} {prefix} {detail}"


def _expired_action(doctype: str, settings: dict[str, Any]) -> str:
    if doctype not in OUTBOUND_DOCTYPES:
        return cast(str, settings["expired_registration_action"])
    existing_stock_policy = cast(str, settings["expired_registration_existing_stock_policy"])
    if existing_stock_policy == "Allow Existing Compliant Stock":
        return "Ignore"
    return existing_stock_policy


def _settings() -> dict[str, Any]:
    settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
    return {fieldname: settings.get(fieldname) for fieldname in SETTINGS_FIELDS}


def _validation_enabled(doctype: str, settings: dict[str, Any]) -> bool:
    fieldname = f"validate_on_{doctype.lower().replace(' ', '_')}"
    return bool(settings.get(fieldname))


def _item_requires_registration(item_code: str) -> bool:
    values = frappe.db.get_value(
        "Item",
        item_code,
        ["is_medical_device", "regulatory_registration_requirement"],
        as_dict=True,
    )
    return bool(
        values
        and values.get("is_medical_device")
        and values.get("regulatory_registration_requirement") == "Required"
    )


def _coverage_date(doc: Document, row: Document) -> date:
    if doc.doctype == "Purchase Order":
        return cast(date, getdate(row.get("schedule_date") or doc.get("transaction_date") or today()))
    if doc.doctype == "Sales Order":
        return cast(date, getdate(row.get("delivery_date") or doc.get("transaction_date") or today()))
    return cast(date, getdate(doc.get("posting_date") or doc.get("transaction_date") or today()))


def _get_approved_override(doc: Document) -> str | None:
    override_name = cast(str, doc.get("medical_device_regulatory_override") or "")
    if not override_name:
        return None
    override = frappe.get_cached_doc(OVERRIDE_DOCTYPE, override_name)
    if override.get("status") != "Approved":
        frappe.throw(
            _("Medical Device Regulatory Override {0} is not approved.").format(frappe.bold(override_name))
        )
    if override.get("transaction_doctype") != doc.doctype or override.get("transaction_name") != doc.name:
        frappe.throw(
            _("Medical Device Regulatory Override {0} does not belong to this transaction.").format(
                frappe.bold(override_name)
            )
        )
    return override_name


def _manufacturer_country(mapping: dict[str, str] | None) -> str:
    manufacturer = mapping.get("physical_manufacturer") if mapping else ""
    return (
        cast(str, frappe.db.get_value("Manufacturer", manufacturer, "country") or "") if manufacturer else ""
    )


def _batch_expiry(batch_no: str | None) -> str:
    return cast(str, frappe.db.get_value("Batch", batch_no, "expiry_date") or "") if batch_no else ""
