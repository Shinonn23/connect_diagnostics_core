# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Resolve the print configuration for one document and one print request.

Values are resolved in four stages, later stages winning:

1. registry defaults from :mod:`connect_diagnostics_core.setup.print_documents`
2. the ``Print Configuration Template`` rows the Customer links to
3. the Customer's own scalar fields and per-document override rows
4. request-only sidebar overrides carried in ``doc.flags.print_settings``

Stage 2 is read live on every print, so editing a Template takes effect for every
linked Customer immediately. A Customer overrides a document by adding a row for
it; without a row it follows the Template.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from connect_diagnostics_core.setup import print_documents

SIDEBAR_PREFIX = "cd_"
COPY_FIELD_PREFIX = "copy_"


def get_default_configuration(document: print_documents.PrintDocument) -> dict[str, Any]:
    """Return the registry defaults for one document, before any site data."""
    values: dict[str, Any] = dict(print_documents.SCALAR_DEFAULTS)
    values.update(
        {
            "enabled": 1,
            "show_date": 1,
            "language": print_documents.default_language(document),
            "show_batch_serial": 1 if document.offers_batch_serial else 0,
        }
    )
    for definition in document.copies:
        values[_copy_field(definition.key)] = definition.default_count
    return values


@frappe.whitelist()
def get_sidebar_configuration(
    doctype: str,
    docname: str,
    print_format: str | None = None,
) -> dict[str, Any]:
    """Return the sidebar controls and resolved values for one print view."""
    frappe.has_permission(doctype, "read", docname, throw=True)
    doc = frappe.get_doc(doctype, docname)
    document = print_documents.get_document(
        print_documents.resolve_document_key(doctype, _text(print_format))
    )
    if not document or not _customer_from_document(doc):
        return {"data": {"fields": [], "values": {}, "sources": {}}, "message": ""}

    resolved = resolve_configuration(doc, document.key)
    if not cint(resolved.values.get("enabled")):
        return {
            "data": {"fields": [], "values": {}, "sources": {}},
            "message": _("{0} is disabled for this Customer.").format(document.label),
        }

    return {
        "data": {
            "fields": _sidebar_fields(document),
            "values": resolved.values,
            "sources": resolved.sources,
        },
        "message": _("Customer print defaults loaded."),
    }


@dataclass(frozen=True)
class Resolution:
    """Resolved configuration values and where each one came from."""

    values: dict[str, Any]
    sources: dict[str, str]


def _require_document(configuration: str) -> print_documents.PrintDocument:
    """Return the registered document, or fail with a clear message."""
    document = print_documents.get_document(configuration)
    if document is None:
        frappe.throw(_("Unknown print configuration {0}.").format(configuration))
        raise frappe.ValidationError(configuration)  # frappe.throw already raised
    return document


def resolve_configuration(doc: Document | Mapping[str, Any], configuration: str) -> Resolution:
    """Resolve one document's configuration through all four stages."""
    document = _require_document(configuration)

    values = get_default_configuration(document)
    sources = dict.fromkeys(values, print_documents.SOURCE_DEFAULT)

    customer = _customer_from_document(doc)
    template = _customer_template(customer)
    if template:
        _apply_row(values, sources, _template_rows(template, document), print_documents.SOURCE_TEMPLATE)

    if customer:
        _apply_scalars(values, sources, _customer_scalars(customer))
        _apply_row(values, sources, _customer_rows(customer, document), print_documents.SOURCE_CUSTOMER)

    _apply_document_fields(values, sources, doc, document)
    _apply_print_settings(values, sources, doc, document)
    return Resolution(values, sources)


def get_document_configuration(doc: Document | Mapping[str, Any], configuration: str) -> dict[str, Any]:
    """Return only the resolved values, without their provenance."""
    return resolve_configuration(doc, configuration).values


def get_document_print_context(doc: Document | Mapping[str, Any], configuration: str) -> dict[str, Any]:
    """Return the normalized values available to Jinja print formats."""
    from connect_diagnostics_core.api.frappe.print_log import register_print

    document = _require_document(configuration)
    values = get_document_configuration(doc, configuration)
    if not cint(values.get("enabled")):
        frappe.throw(_("{0} is disabled for this Customer.").format(document.label))

    language = document.fixed_language or _text(values.get("language")) or print_documents.LANGUAGE_THAI
    copies = _copy_contexts(document, values, language)
    original_count = sum(
        copy["count"] for copy in copies if copy["kind_group"] == print_documents.KIND_ORIGINAL
    )
    context = {
        "configuration": configuration,
        "customer_name": _text(values.get("customer_print_name")) or _document_customer_name(doc),
        "language": language,
        "show_thai": language in {print_documents.LANGUAGE_THAI, print_documents.LANGUAGE_BILINGUAL},
        "show_english": language in {print_documents.LANGUAGE_ENGLISH, print_documents.LANGUAGE_BILINGUAL},
        "show_date": cint(values.get("show_date")) != 0,
        "original_count": original_count,
        "copy_count": len(copies) - original_count,
        "copies": [{"kind": copy["kind"], "label": copy["label"]} for copy in copies],
        "show_batch_serial": bool(cint(values.get("show_batch_serial")))
        if document.offers_batch_serial
        else False,
        "quotation_signatory_type": _text(values.get("quotation_signatory_type")),
        "sales_representative_employee": _text(values.get("sales_representative_employee")),
        "override_quotation_validity_text": cint(values.get("override_quotation_validity_text")),
        "quotation_custom_validity_text": _text(values.get("quotation_custom_validity_text")),
        "quotation_delivery_terms": _text(values.get("quotation_delivery_terms")),
    }
    register_print(doc, configuration, context)
    return context


def _copy_contexts(
    document: print_documents.PrintDocument,
    values: Mapping[str, Any],
    language: str,
) -> list[dict[str, Any]]:
    """Expand each named copy into one page-set entry per requested count."""
    copies: list[dict[str, Any]] = []
    for definition in document.copies:
        count = max(cint(values.get(_copy_field(definition.key))), 0)
        label = _text(values.get(_copy_label_field(definition.key))) or definition.label(language)
        for index in range(1, count + 1):
            suffix = f" {index}/{count}" if count > 1 else ""
            copies.append(
                {
                    "kind": definition.key,
                    "kind_group": definition.kind,
                    "label": f"{label}{suffix}",
                    "count": 1,
                }
            )
    if copies:
        return copies

    fallback = document.copies[0]
    return [
        {
            "kind": fallback.key,
            "kind_group": fallback.kind,
            "label": fallback.label(language),
            "count": 1,
        }
    ]


def _sidebar_fields(document: print_documents.PrintDocument) -> list[dict[str, Any]]:
    """Build the sidebar controls for one document from the registry."""
    fields: list[dict[str, Any]] = [
        {
            "fieldname": "customer_print_name",
            "label": _("Customer Print Name"),
            "fieldtype": "Data",
        },
        {
            "fieldname": "show_date",
            "label": _("Show Date"),
            "fieldtype": "Check",
        },
    ]
    if document.language_selectable:
        fields.append(
            {
                "fieldname": "language",
                "label": _("Language"),
                "fieldtype": "Select",
                "options": "\n".join(print_documents.LANGUAGE_OPTIONS),
            }
        )
    if document.offers_batch_serial:
        fields.append(
            {
                "fieldname": "show_batch_serial",
                "label": _("Show Batch / Serial Number"),
                "fieldtype": "Check",
            }
        )
    fields.extend(
        {
            "fieldname": _copy_field(definition.key),
            "label": definition.label_th,
            "fieldtype": "Int",
        }
        for definition in document.copies
    )
    if document.key != "quotation":
        return fields

    return [
        *fields,
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


def _apply_scalars(
    values: dict[str, Any],
    sources: dict[str, str],
    scalars: Mapping[str, Any],
) -> None:
    """Apply Customer scalar fields; a blank text value keeps the default."""
    for fieldname, value in scalars.items():
        if value is None or value == "":
            continue
        values[fieldname] = value
        sources[fieldname] = print_documents.SOURCE_CUSTOMER


def _apply_row(
    values: dict[str, Any],
    sources: dict[str, str],
    row: Mapping[str, Any] | None,
    source: str,
) -> None:
    """Apply one whole document row and its copies."""
    if not row:
        return
    for fieldname, value in row.items():
        if value is None:
            continue
        values[fieldname] = value
        sources[fieldname] = source


def _apply_document_fields(
    values: dict[str, Any],
    sources: dict[str, str],
    doc: Document | Mapping[str, Any],
    document: print_documents.PrintDocument,
) -> None:
    """Apply fields set on the transaction itself, such as a chosen signatory."""
    for fieldname in document.document_fields:
        value = _text(doc.get(fieldname))
        if not value:
            continue
        values[fieldname] = value
        sources[fieldname] = print_documents.SOURCE_DOCUMENT


def _apply_print_settings(
    values: dict[str, Any],
    sources: dict[str, str],
    doc: Document | Mapping[str, Any],
    document: print_documents.PrintDocument,
) -> None:
    """Apply request-only sidebar overrides; they never touch stored data."""
    print_settings = _print_settings(doc)
    if not print_settings:
        return
    for fieldname in _overridable_fields(document):
        override = print_settings.get(f"{SIDEBAR_PREFIX}{fieldname}")
        if override is None:
            continue
        values[fieldname] = override
        sources[fieldname] = print_documents.SOURCE_REQUEST


def _overridable_fields(document: print_documents.PrintDocument) -> tuple[str, ...]:
    return (
        "customer_print_name",
        "show_date",
        *(("language",) if document.language_selectable else ()),
        *(("show_batch_serial",) if document.offers_batch_serial else ()),
        *tuple(_copy_field(definition.key) for definition in document.copies),
        *document.extra_fields,
    )


def get_document_enabled_map(customers: Sequence[str], configuration: str) -> dict[str, bool]:
    """Return, for many Customers at once, whether one document is enabled.

    Mirrors stages 1-3 of :func:`resolve_configuration` — registry default, then
    Template row, then Customer row — for the ``enabled`` flag alone, in three
    queries rather than three per Customer. A report needs the answer for a whole
    page at once; request-only overrides do not apply outside a print request.
    """
    document = _require_document(configuration)
    names = sorted({name for name in customers if name})
    if not names:
        return {}

    enabled = dict.fromkeys(names, bool(cint(get_default_configuration(document)["enabled"])))
    linked = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Customer",
            filters={"name": ["in", names]},
            fields=["name", "print_configuration_template"],
        ),
    )
    templates = {_text(row.get("print_configuration_template")) for row in linked}
    templates.discard("")

    by_template = _enabled_rows("Print Configuration Template", sorted(templates), document.key)
    for row in linked:
        template = _text(row.get("print_configuration_template"))
        if template in by_template:
            enabled[cast(str, row["name"])] = by_template[template]

    enabled.update(_enabled_rows("Customer", names, document.key))
    return enabled


def _enabled_rows(parenttype: str, parents: Sequence[str], document_key: str) -> dict[str, bool]:
    if not parents:
        return {}
    rows = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Print Document Configuration",
            filters={
                "parenttype": parenttype,
                "parent": ["in", list(parents)],
                "parentfield": "print_documents",
                "document_key": document_key,
            },
            fields=["parent", "enabled"],
        ),
    )
    return {cast(str, row["parent"]): bool(cint(row.get("enabled"))) for row in rows}


def _template_rows(template: str, document: print_documents.PrintDocument) -> dict[str, Any] | None:
    return _rows_for_document("Print Configuration Template", template, document)


def _customer_rows(customer: str, document: print_documents.PrintDocument) -> dict[str, Any] | None:
    return _rows_for_document("Customer", customer, document)


def _rows_for_document(
    parenttype: str,
    parent: str,
    document: print_documents.PrintDocument,
) -> dict[str, Any] | None:
    """Return one parent's settings for a document, or None when it has no row."""
    settings = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Print Document Configuration",
            filters={
                "parenttype": parenttype,
                "parent": parent,
                "parentfield": "print_documents",
                "document_key": document.key,
            },
            fields=["enabled", "show_date", "language", "show_batch_serial"],
            limit=1,
        ),
    )
    if not settings:
        return None

    row: dict[str, Any] = dict(settings[0])
    if not document.language_selectable:
        row.pop("language", None)
    if not document.offers_batch_serial:
        row.pop("show_batch_serial", None)

    copies = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Print Copy Configuration",
            filters={
                "parenttype": parenttype,
                "parent": parent,
                "parentfield": "print_copies",
                "document_key": document.key,
            },
            fields=["copy_key", "label", "count"],
        ),
    )
    for copy in copies:
        copy_key = _text(copy.get("copy_key"))
        if not document.copy(copy_key):
            continue
        row[_copy_field(copy_key)] = copy.get("count")
        row[_copy_label_field(copy_key)] = copy.get("label")
    return row


def _customer_template(customer: str) -> str:
    if not customer:
        return ""
    return _text(frappe.db.get_value("Customer", customer, "print_configuration_template"))


def _customer_scalars(customer: str) -> dict[str, Any]:
    available = _available_customer_fields()
    if not available:
        return {}
    return cast(
        dict[str, Any],
        frappe.db.get_value("Customer", customer, available, as_dict=True) or {},
    )


def _available_customer_fields() -> list[str]:
    """Return the scalar fields the current site schema actually has.

    A deployment can serve print views after the app code updates but before
    migration creates the Customer fields; restricting the query keeps those
    requests on registry defaults instead of erroring.
    """
    customer_meta = frappe.get_meta("Customer")
    return [fieldname for fieldname in print_documents.SCALAR_FIELDS if customer_meta.has_field(fieldname)]


def _copy_field(copy_key: str) -> str:
    return f"{COPY_FIELD_PREFIX}{copy_key}"


def _copy_label_field(copy_key: str) -> str:
    return f"{COPY_FIELD_PREFIX}{copy_key}_label"


def _customer_from_document(doc: Document | Mapping[str, Any]) -> str:
    doctype = _text(doc.get("doctype"))
    if doctype == "Quotation":
        return _text(doc.get("party_name")) if _text(doc.get("quotation_to")) == "Customer" else ""
    if doctype == "Payment Entry":
        return _text(doc.get("party")) if _text(doc.get("party_type")) == "Customer" else ""
    return _text(doc.get("customer"))


def _document_customer_name(doc: Document | Mapping[str, Any]) -> str:
    return _text(doc.get("customer_name")) or _text(doc.get("party_name"))


def _print_settings(doc: Document | Mapping[str, Any]) -> Mapping[str, Any]:
    flags = getattr(doc, "flags", None)
    if flags is None:
        return {}
    return cast(Mapping[str, Any], flags.get("print_settings") or {})


def _text(value: Any) -> str:
    return str(value or "").strip()
