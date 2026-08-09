# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Record every document actually printed or downloaded as PDF.

Two channels reach this module, because Frappe exposes them differently:

* **PDF** — ``frappe.utils.print_format.download_pdf`` is a whitelisted method, so
  :func:`download_pdf` replaces it through ``override_whitelisted_methods`` and
  the client cannot skip it.
* **Print** — the Print button loads the ``/printview`` route rather than
  ``/api/method``, so it cannot be overridden. :func:`register_print` runs while
  the template renders and recognises a real print by ``trigger_print`` in the
  request; a plain preview is not recorded.

Two deliberate deviations from the general engineering rules, both required for
an audit trail rather than accidental:

* A print render is a GET and Frappe does not commit it, so the insert commits
  explicitly even though it happens during a read request. Enqueuing was
  rejected: the record must not disappear when workers are down.
* Logging is fail-open. Any failure is reported through ``frappe.log_error`` and
  never blocks the document from printing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

import frappe
from frappe.model.document import Document
from frappe.utils import cint

CHANNEL_PRINT = "Print"
CHANNEL_PDF = "PDF"

CUSTOMER_SOURCES = (
    ("Quotation", "quotation_to", "Customer", "party_name"),
    ("Payment Entry", "party_type", "Customer", "party"),
)


# allow_guest mirrors frappe.utils.print_format.download_pdf, which this replaces
# wholesale. Removing it would silently break guest PDF links. Access is still
# gated inside the original by validate_print_permission(doc).
@frappe.whitelist(allow_guest=True)  # nosemgrep: guest-whitelisted-method
def download_pdf(
    doctype: str,
    name: str,
    format: str | None = None,
    doc: str | dict[str, Any] | Document | None = None,
    no_letterhead: int | str = 0,
    language: str | None = None,
    letterhead: str | None = None,
    pdf_generator: Literal["wkhtmltopdf", "chrome"] | None = None,
) -> Any:
    """Wrap Frappe's PDF download so the request is recorded.

    The signature, ``allow_guest``, and return value mirror the original method:
    this replaces it for every caller through ``override_whitelisted_methods``.
    """
    from frappe.utils.print_format import download_pdf as frappe_download_pdf

    from connect_diagnostics_core.api.erpnext.source_purchase_order import append_source_copy

    result = frappe_download_pdf(
        doctype,
        name,
        format=format,
        doc=doc,
        no_letterhead=no_letterhead,
        language=language,
        letterhead=letterhead,
        pdf_generator=pdf_generator,
    )
    # The only override point for the PDF channel, so the source Purchase Order
    # copy a Customer requires is joined on here rather than in its own wrapper.
    append_source_copy(doctype, name, print_format=format)
    record_print(doctype, name, CHANNEL_PDF, print_format=format, language=language)
    return result


def register_print(
    doc: Document | Mapping[str, Any],
    configuration: str = "",
    context: Mapping[str, Any] | None = None,
) -> str:
    """Record a real print from a rendering template.

    Exposed to Jinja so the print formats that carry no Customer configuration
    can register themselves with ``{{ register_print(doc) }}``. Returns an empty
    string so a template can call it inline.
    """
    if not _is_triggered_print():
        return ""

    copies = list(context.get("copies") or []) if context else []
    record_print(
        _text(doc.get("doctype")),
        _text(doc.get("name")),
        CHANNEL_PRINT,
        print_format=_requested_print_format(),
        language=_text(context.get("language")) if context else "",
        copies=len(copies) or 1,
        copy_labels=", ".join(_text(copy.get("label")) for copy in copies),
        customer=_customer_from_document(doc),
        configuration=configuration,
    )
    return ""


def record_print(
    reference_doctype: str,
    reference_name: str,
    channel: str,
    print_format: str | None = None,
    language: str | None = None,
    copies: int = 1,
    copy_labels: str = "",
    customer: str = "",
    configuration: str = "",
) -> None:
    """Insert one Print Log row, never letting a failure block printing."""
    if not reference_doctype or not reference_name:
        return

    try:
        log = frappe.new_doc("Print Log")
        log.update(
            {
                "reference_doctype": reference_doctype,
                "reference_name": reference_name,
                "customer": customer or _customer_for_reference(reference_doctype, reference_name),
                "print_format": _text(print_format) or None,
                "channel": channel,
                "language": _text(language),
                "copies": max(cint(copies), 1),
                "copy_labels": copy_labels,
            }
        )
        log.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="Print Log not recorded",
            message=(
                f"reference_doctype={reference_doctype} reference_name={reference_name} "
                f"channel={channel} print_format={print_format} configuration={configuration}\n\n"
                f"{frappe.get_traceback()}"
            ),
        )


def _is_triggered_print() -> bool:
    """Return True only for the Print button, not for a preview render."""
    form_dict = getattr(frappe.local, "form_dict", None)
    if not form_dict:
        return False
    return bool(cint(form_dict.get("trigger_print")))


def _requested_print_format() -> str:
    form_dict = getattr(frappe.local, "form_dict", None)
    if not form_dict:
        return ""
    return _text(form_dict.get("format") or form_dict.get("print_format"))


def _customer_for_reference(reference_doctype: str, reference_name: str) -> str | None:
    """Resolve the Customer for a reference without loading the whole document."""
    for doctype, discriminator, expected, fieldname in CUSTOMER_SOURCES:
        if doctype != reference_doctype:
            continue
        values = frappe.db.get_value(
            reference_doctype, reference_name, [discriminator, fieldname], as_dict=True
        )
        if values and _text(values.get(discriminator)) == expected:
            return _text(values.get(fieldname)) or None
        return None

    meta = frappe.get_meta(reference_doctype)
    if not meta.has_field("customer"):
        return None
    return _text(frappe.db.get_value(reference_doctype, reference_name, "customer")) or None


def _customer_from_document(doc: Document | Mapping[str, Any]) -> str:
    doctype = _text(doc.get("doctype"))
    for source_doctype, discriminator, expected, fieldname in CUSTOMER_SOURCES:
        if source_doctype == doctype:
            return _text(doc.get(fieldname)) if _text(doc.get(discriminator)) == expected else ""
    return _text(doc.get("customer"))


def _text(value: Any) -> str:
    return str(value or "").strip()
