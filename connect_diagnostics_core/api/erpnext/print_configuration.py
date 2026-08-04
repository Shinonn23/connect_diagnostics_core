# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Customer print defaults, Template fetches, and transient print overrides."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from connect_diagnostics_core.setup import quotation as quotation_setup

DOCUMENT_CONFIGURATION = {
    "quotation": "Quotation",
    "tax_invoice": "Tax Invoice",
    "delivery_note": "Delivery Note",
    "invoice": "Invoice",
    "abbreviated_tax_invoice": "Abbreviated Tax Invoice",
    "receipt": "Receipt",
}

PRINT_FORMAT_CONFIGURATION = {
    "Quotation": "quotation",
    "Tax Invoice Delivery Note and Invoice": "tax_invoice",
    "Abbreviated Tax Invoice And Receipt": "abbreviated_tax_invoice",
    "Receipt": "receipt",
}

DOCUMENT_CONFIGURATION_FIELDS = tuple(
    fieldname
    for prefix in DOCUMENT_CONFIGURATION
    for fieldname in (
        f"use_{prefix}",
        f"show_{prefix}_date",
        f"{prefix}_language",
        f"{prefix}_original_count",
        f"{prefix}_copy_count",
    )
)

TAX_INVOICE_SELECTION_FIELDS = (
    "print_tax_invoice_original",
    "print_tax_invoice_customer_copy",
    "print_tax_invoice_accounting_copy",
    "print_tax_invoice_sales_copy",
    "show_tax_invoice_batch_serial",
)

TAX_INVOICE_COPY_DEFINITIONS = (
    (
        "print_tax_invoice_original",
        "original",
        "ต้นฉบับ (สำหรับลูกค้า)",
    ),
    (
        "print_tax_invoice_customer_copy",
        "customer",
        "สำเนา (สำหรับลูกค้า)",
    ),
    (
        "print_tax_invoice_accounting_copy",
        "accounting",
        "สำเนา (สำหรับฝ่ายบัญชี)",
    ),
    (
        "print_tax_invoice_sales_copy",
        "sales",
        "สำเนา (สำหรับฝ่ายขาย)",
    ),
)

QUOTATION_CONFIGURATION_FIELDS = (
    "quotation_signatory_type",
    "override_quotation_validity_text",
    "quotation_custom_validity_text",
    "quotation_delivery_terms",
)

CONFIGURATION_FIELDNAMES = (
    "customer_print_name",
    *DOCUMENT_CONFIGURATION_FIELDS,
    *TAX_INVOICE_SELECTION_FIELDS,
    *QUOTATION_CONFIGURATION_FIELDS,
    "use_customer_po",
    "purchase_order_copy_count",
)


def get_default_configuration() -> dict[str, Any]:
    """Return the site-independent defaults for a Customer print configuration."""
    defaults: dict[str, Any] = {
        "customer_print_name": "",
        "use_customer_po": 1,
        "purchase_order_copy_count": 1,
        "quotation_signatory_type": quotation_setup.SIGNATORY_SALES_REPRESENTATIVE,
        "override_quotation_validity_text": 0,
        "quotation_custom_validity_text": "",
        "quotation_delivery_terms": "",
    }
    for prefix in DOCUMENT_CONFIGURATION:
        defaults.update(
            {
                f"use_{prefix}": 1,
                f"show_{prefix}_date": 1,
                f"{prefix}_language": "Thai",
                f"{prefix}_original_count": 1,
                f"{prefix}_copy_count": 0,
            }
        )
    defaults.update(
        {
            "print_tax_invoice_original": 1,
            "print_tax_invoice_customer_copy": 1,
            "print_tax_invoice_accounting_copy": 1,
            "print_tax_invoice_sales_copy": 1,
            "show_tax_invoice_batch_serial": 1,
        }
    )
    return defaults


@frappe.whitelist()
def fetch_template_defaults(customer: str) -> dict[str, Any]:
    """Return the selected Template values for a Customer form without saving it."""
    frappe.has_permission("Customer", "write", customer, throw=True)
    customer_doc = frappe.get_doc("Customer", customer)
    template_name = _text(customer_doc.get("print_configuration_template"))
    if not template_name:
        frappe.throw(_("Print Configuration Template is required before fetching defaults."))

    return get_template_defaults(template_name)


@frappe.whitelist()
def get_template_defaults(template: str) -> dict[str, Any]:
    """Return a Template's values for an unsaved or existing Customer form."""
    if not template:
        frappe.throw(_("Print Configuration Template is required before fetching defaults."))

    frappe.has_permission("Print Configuration Template", "read", template, throw=True)
    template_doc = frappe.get_doc("Print Configuration Template", template)
    values = {
        fieldname: template_doc.get(fieldname)
        for fieldname in CONFIGURATION_FIELDNAMES
        if template_doc.get(fieldname) is not None
    }
    return {
        "data": values,
        "message": _("Print configuration defaults loaded from Template."),
    }


@frappe.whitelist()
def get_sidebar_configuration(
    doctype: str,
    docname: str,
    print_format: str | None = None,
) -> dict[str, Any]:
    """Return allowed Sidebar controls and Customer defaults for one print view."""
    frappe.has_permission(doctype, "read", docname, throw=True)
    doc = frappe.get_doc(doctype, docname)
    customer = _customer_from_document(doc)
    configuration = _configuration_key(doctype, _text(print_format))
    if not customer or not configuration:
        return {"data": {"fields": [], "values": {}}, "message": ""}

    values = get_document_configuration(doc, configuration)
    if not cint(values.get(f"use_{configuration}")):
        return {
            "data": {"fields": [], "values": {}},
            "message": _("{0} is disabled for this Customer.").format(DOCUMENT_CONFIGURATION[configuration]),
        }
    return {
        "data": {
            "fields": _sidebar_fields(configuration),
            "values": values,
        },
        "message": _("Customer print defaults loaded."),
    }


def get_document_configuration(doc: Document | Mapping[str, Any], configuration: str) -> dict[str, Any]:
    """Merge fallback defaults, Customer defaults, and request-only print overrides."""
    values = get_default_configuration()
    customer = _customer_from_document(doc)
    if customer:
        available_fields = _available_customer_configuration_fields()
        customer_values = (
            cast(
                dict[str, Any] | None,
                frappe.db.get_value(
                    "Customer",
                    customer,
                    available_fields,
                    as_dict=True,
                ),
            )
            if available_fields
            else None
        )
        if customer_values:
            values.update({key: value for key, value in customer_values.items() if value is not None})

    print_settings = _print_settings(doc)
    for fieldname in _configuration_fields(configuration):
        override = print_settings.get(f"cd_{fieldname}")
        if override is not None:
            values[fieldname] = override
    return values


def get_document_print_context(doc: Document | Mapping[str, Any], configuration: str) -> dict[str, Any]:
    """Return normalized values available to Jinja print formats."""
    values = get_document_configuration(doc, configuration)
    if not cint(values.get(f"use_{configuration}")):
        frappe.throw(_("{0} is disabled for this Customer.").format(DOCUMENT_CONFIGURATION[configuration]))

    language = (
        "Thai" if configuration == "tax_invoice" else _text(values.get(f"{configuration}_language")) or "Thai"
    )
    if configuration == "tax_invoice":
        copies = _tax_invoice_copy_contexts(values)
        original_count = sum(copy["kind"] == "original" for copy in copies)
        copy_count = len(copies) - original_count
    else:
        original_count = max(cint(values.get(f"{configuration}_original_count")), 0)
        copy_count = max(cint(values.get(f"{configuration}_copy_count")), 0)
        copies = _copy_contexts(original_count, copy_count, language)
    customer_name = _text(values.get("customer_print_name")) or _document_customer_name(doc)

    return {
        "configuration": configuration,
        "customer_name": customer_name,
        "language": language,
        "show_thai": True if configuration == "tax_invoice" else language in {"Thai", "Thai / English"},
        "show_english": False
        if configuration == "tax_invoice"
        else language in {"English", "Thai / English"},
        "show_date": cint(values.get(f"show_{configuration}_date")) != 0,
        "original_count": original_count,
        "copy_count": copy_count,
        "copies": copies,
        "show_batch_serial": bool(cint(values.get("show_tax_invoice_batch_serial")))
        if configuration == "tax_invoice"
        else False,
        "quotation_signatory_type": _text(values.get("quotation_signatory_type")),
        "override_quotation_validity_text": cint(values.get("override_quotation_validity_text")),
        "quotation_custom_validity_text": _text(values.get("quotation_custom_validity_text")),
        "quotation_delivery_terms": _text(values.get("quotation_delivery_terms")),
    }


def _sidebar_fields(configuration: str) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = [
        {
            "fieldname": "customer_print_name",
            "label": _("Customer Print Name"),
            "fieldtype": "Data",
        },
        {
            "fieldname": f"show_{configuration}_date",
            "label": _("Show Date"),
            "fieldtype": "Check",
        },
    ]
    if configuration != "tax_invoice":
        fields.append(
            {
                "fieldname": f"{configuration}_language",
                "label": _("Language"),
                "fieldtype": "Select",
                "options": "Thai\nEnglish\nThai / English",
            }
        )
    if configuration == "tax_invoice":
        fields.extend(
            {
                "fieldname": fieldname,
                "label": _(label),
                "fieldtype": "Check",
            }
            for fieldname, _kind, label in TAX_INVOICE_COPY_DEFINITIONS
        )
        fields.append(
            {
                "fieldname": "show_tax_invoice_batch_serial",
                "label": _("Show Batch / Serial Number"),
                "fieldtype": "Check",
            }
        )
    else:
        fields.extend(
            [
                {
                    "fieldname": f"{configuration}_original_count",
                    "label": _("Original Count"),
                    "fieldtype": "Int",
                },
                {
                    "fieldname": f"{configuration}_copy_count",
                    "label": _("Copy Count"),
                    "fieldtype": "Int",
                },
            ]
        )
    if configuration != "quotation":
        return fields

    return [
        *fields,
        {
            "fieldname": "quotation_signatory_type",
            "label": _("Signatory Type"),
            "fieldtype": "Select",
            "options": "\n".join(quotation_setup.SIGNATORY_TYPES),
        },
        {
            "fieldname": "override_quotation_validity_text",
            "label": _("Override validity text"),
            "fieldtype": "Check",
        },
        {
            "fieldname": "quotation_custom_validity_text",
            "label": _("Custom Validity Text"),
            "fieldtype": "Small Text",
        },
        {
            "fieldname": "quotation_delivery_terms",
            "label": _("Delivery Terms"),
            "fieldtype": "Small Text",
        },
    ]


def _configuration_fields(configuration: str) -> tuple[str, ...]:
    if configuration == "tax_invoice":
        return (
            "customer_print_name",
            "show_tax_invoice_date",
            *TAX_INVOICE_SELECTION_FIELDS,
        )
    return (
        "customer_print_name",
        f"show_{configuration}_date",
        f"{configuration}_language",
        f"{configuration}_original_count",
        f"{configuration}_copy_count",
        *(QUOTATION_CONFIGURATION_FIELDS if configuration == "quotation" else ()),
    )


def _configuration_key(doctype: str, print_format: str) -> str:
    if print_format in PRINT_FORMAT_CONFIGURATION:
        return PRINT_FORMAT_CONFIGURATION[print_format]
    return {
        "Quotation": "quotation",
        "Sales Invoice": "tax_invoice",
        "Delivery Note": "delivery_note",
        "Payment Entry": "receipt",
    }.get(doctype, "")


def _customer_from_document(doc: Document | Mapping[str, Any]) -> str:
    doctype = _text(doc.get("doctype"))
    if doctype == "Quotation":
        return _text(doc.get("party_name")) if _text(doc.get("quotation_to")) == "Customer" else ""
    if doctype == "Payment Entry":
        return _text(doc.get("party")) if _text(doc.get("party_type")) == "Customer" else ""
    return _text(doc.get("customer"))


def _document_customer_name(doc: Document | Mapping[str, Any]) -> str:
    return _text(doc.get("customer_name")) or _text(doc.get("party_name"))


def _available_customer_configuration_fields() -> list[str]:
    """Return configuration fields present in the current site schema.

    Print view can load while a deployment has updated the app code but migration
    has not yet created the new Customer custom fields. Restricting the query to
    installed fields keeps the request on the safe system-default fallback.
    """
    customer_meta = frappe.get_meta("Customer")
    return [fieldname for fieldname in CONFIGURATION_FIELDNAMES if customer_meta.has_field(fieldname)]


def _print_settings(doc: Document | Mapping[str, Any]) -> Mapping[str, Any]:
    flags = getattr(doc, "flags", None)
    if flags is None:
        return {}
    return cast(Mapping[str, Any], flags.get("print_settings") or {})


def _copy_contexts(original_count: int, copy_count: int, language: str) -> list[dict[str, str]]:
    copies: list[dict[str, str]] = []
    for index in range(1, original_count + 1):
        copies.append(
            {
                "kind": "original",
                "label": _copy_label("ต้นฉบับ", "Original", index, original_count, language),
            }
        )
    for index in range(1, copy_count + 1):
        copies.append(
            {
                "kind": "copy",
                "label": _copy_label("สำเนา", "Copy", index, copy_count, language),
            }
        )
    return copies or [{"kind": "original", "label": _copy_label("ต้นฉบับ", "Original", 1, 1, language)}]


def _tax_invoice_copy_contexts(values: Mapping[str, Any]) -> list[dict[str, str]]:
    copies = [
        {
            "kind": kind,
            "label": thai,
        }
        for fieldname, kind, thai in TAX_INVOICE_COPY_DEFINITIONS
        if cint(values.get(fieldname))
    ]
    return copies or [
        {
            "kind": "original",
            "label": "ต้นฉบับ (สำหรับลูกค้า)",
        }
    ]


def _copy_label(thai: str, english: str, index: int, total: int, language: str) -> str:
    number = f" {index}/{total}" if total > 1 else ""
    if language == "Thai":
        return f"{thai}{number}"
    if language == "English":
        return f"{english}{number}"
    return f"{thai} / {english}{number}"


def _text(value: Any) -> str:
    return str(value or "").strip()
