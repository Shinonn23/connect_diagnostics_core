# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Build the Jinja print context for one document and one print request.

Values come from two sources, the sidebar winning:

1. registry defaults from :mod:`connect_diagnostics_core.setup.print_documents`
2. request-only sidebar overrides carried in ``doc.flags.print_settings``

Print options are chosen per print in the print sidebar; there is no stored
per-Customer print configuration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from connect_diagnostics_core.api.erpnext import company as company_api
from connect_diagnostics_core.setup import print_documents
from connect_diagnostics_core.setup import quotation as quotation_setup

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
    """Resolve one document's configuration from registry defaults + sidebar."""
    document = _require_document(configuration)

    values = get_default_configuration(document)
    sources = dict.fromkeys(values, print_documents.SOURCE_DEFAULT)

    _apply_document_fields(values, sources, doc, document)
    _apply_print_settings(values, sources, doc, document)
    return Resolution(values, sources)


def get_document_configuration(doc: Document | Mapping[str, Any], configuration: str) -> dict[str, Any]:
    """Return only the resolved values, without their provenance."""
    return resolve_configuration(doc, configuration).values


@frappe.whitelist()
def get_print_options(doctype: str, docname: str, print_format: str | None = None) -> dict[str, Any]:
    """Return the print sidebar controls and their default values for one print.

    Registry controls and document-scoped defaults. There is no per-Customer
    configuration: every print is chosen fresh in the sidebar. Quotation's
    authorized manager choices are read from its Company allow-list. Returns an
    empty set for an unconfigured doctype/format.
    """
    frappe.has_permission(doctype, "read", docname, throw=True)
    document = print_documents.get_document(
        print_documents.resolve_document_key(doctype, _text(print_format))
    )
    if not document:
        return {"data": {"fields": [], "values": {}}, "message": ""}
    values = get_default_configuration(document)
    manager_signatories: list[dict[str, Any]] = []
    if document.key == "quotation":
        quotation_values = (
            frappe.db.get_value("Quotation", docname, ["company", "quotation_signatory_type"], as_dict=True)
            or {}
        )
        signatory_type = _text(quotation_values.get("quotation_signatory_type"))
        if signatory_type:
            values["quotation_signatory_type"] = signatory_type
        manager_signatories = company_api.get_quotation_authorized_signatories(
            _text(quotation_values.get("company"))
        )
    return {
        "data": {
            "fields": _sidebar_fields(document, manager_signatories),
            "values": values,
            "manager_signatories": manager_signatories,
        },
        "message": _("Print options loaded."),
    }


def _sidebar_fields(
    document: print_documents.PrintDocument,
    manager_signatories: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
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
    if document.key == "quotation":
        fields.extend(
            [
                {
                    "fieldname": "quotation_signatory_type",
                    "label": _("Signatory"),
                    "fieldtype": "Select",
                    "options": "\n".join(quotation_setup.SIGNATORY_TYPES),
                },
                {
                    "fieldname": "manager_signatory_employee",
                    "label": _("Manager Signatory"),
                    "fieldtype": "Select",
                    "options": "\n"
                    + "\n".join(
                        _text(row.get("employee")) for row in manager_signatories if row.get("employee")
                    ),
                    "option_labels": {
                        _text(row.get("employee")): _text(row.get("name")) or _text(row.get("employee"))
                        for row in manager_signatories
                        if row.get("employee")
                    },
                    "depends_on": "eval:cd_quotation_signatory_type=='Managing Director'",
                    "mandatory_depends_on": "eval:cd_quotation_signatory_type=='Managing Director'",
                    "description": _(
                        "Only Employees in this Company's authorized signatory list can be selected."
                    ),
                },
            ]
        )
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
    return fields


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
        "manager_signatory_employee": _text(values.get("manager_signatory_employee")),
        "sales_representative_employee": _text(values.get("sales_representative_employee")),
        "edit_validity_text": cint(values.get("edit_validity_text")),
        "validity_text": _text(values.get("validity_text")),
        "quotation_delivery_terms": _text(values.get("quotation_delivery_terms")),
    }
    if document.key == "quotation":
        context["signatory_employee"] = (
            context["manager_signatory_employee"]
            if context["quotation_signatory_type"] == quotation_setup.SIGNATORY_MANAGING_DIRECTOR
            else context["sales_representative_employee"]
        )
    # Quotation resolves its Employee/E-Signature after this shared context is
    # built, so its own API registers only after readiness validation. This
    # prevents an attempted print with a missing signatory from creating an
    # audit row.
    if configuration != "quotation":
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


def _copy_field(copy_key: str) -> str:
    return f"{COPY_FIELD_PREFIX}{copy_key}"


def _copy_label_field(copy_key: str) -> str:
    return f"{COPY_FIELD_PREFIX}{copy_key}_label"


def _document_customer_name(doc: Document | Mapping[str, Any]) -> str:
    return _text(doc.get("customer_name")) or _text(doc.get("party_name"))


def _print_settings(doc: Document | Mapping[str, Any]) -> Mapping[str, Any]:
    flags = getattr(doc, "flags", None)
    if flags is None:
        return {}
    return cast(Mapping[str, Any], flags.get("print_settings") or {})


def _text(value: Any) -> str:
    return str(value or "").strip()
