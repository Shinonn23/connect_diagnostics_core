# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Quotation-specific values for the Customer-backed print configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, date_diff

from connect_diagnostics_core.api.erpnext.print_configuration import get_document_print_context
from connect_diagnostics_core.setup import quotation as quotation_setup


def get_quotation_print_context(doc: Document | Mapping[str, Any]) -> dict[str, Any]:
    """Build Quotation print values from the resolved configuration."""
    context = get_document_print_context(doc, "quotation")
    language = _text(context.get("language")) or "Thai"
    sales_representative = _text(context.get("sales_representative_employee"))

    return {
        **context,
        "validity_text": _validity_text(doc, context, language),
        "validity_is_custom": bool(cint(context.get("override_quotation_validity_text"))),
        "delivery_terms": _text(context.get("quotation_delivery_terms")),
        "signatory": _signatory_details(context, sales_representative, language),
        "sales_contact": _employee_details(sales_representative),
        "copies": context["copies"],
    }


def _validity_text(doc: Document | Mapping[str, Any], context: Mapping[str, Any], language: str) -> str:
    if cint(context.get("override_quotation_validity_text")):
        custom_validity_text = _text(context.get("quotation_custom_validity_text"))
        if not custom_validity_text:
            frappe.throw(_("Custom Validity Text is required when overriding Valid Till."))
        return custom_validity_text

    valid_till = doc.get("valid_till")
    transaction_date = doc.get("transaction_date")
    if not valid_till or not transaction_date:
        return ""

    days = date_diff(valid_till, transaction_date)
    if language == "Thai":
        return f"{days} วัน นับถัดจากวันที่เสนอราคา"
    if language == "English":
        return f"{days} days from the quotation date"
    return f"{days} วัน นับถัดจากวันที่เสนอราคา / {days} days from the quotation date"


def _signatory_details(
    context: Mapping[str, Any], sales_representative: str, language: str
) -> dict[str, str]:
    """Return the name and caption printed under the signature line.

    A Managing Director quotation prints an empty name on purpose: the director
    signs it and writes the name by hand, so no Employee is resolved.
    """
    signatory_type = _text(context.get("quotation_signatory_type"))
    caption = quotation_setup.SIGNATORY_CAPTIONS.get(signatory_type)
    if caption is None:
        frappe.throw(_("Quotation signatory type is required."))
        raise frappe.ValidationError(signatory_type)  # frappe.throw already raised

    caption_text = _caption_text(caption, language)
    if signatory_type not in quotation_setup.SIGNATORY_PRINTS_NAME:
        return {**_employee_details(""), "caption": caption_text}

    if not sales_representative:
        frappe.throw(_("Sales Representative is required when a Sales Representative signs the quotation."))
    return {**_employee_details(sales_representative), "caption": caption_text}


def _caption_text(caption: tuple[str, str], language: str) -> str:
    thai, english = caption
    if language == "Thai":
        return thai
    if language == "English":
        return english
    return f"{thai} / {english}"


def _employee_details(employee: str) -> dict[str, str]:
    if not employee:
        return {"employee": "", "name": "", "phone": ""}

    details = cast(
        dict[str, Any] | None,
        frappe.db.get_value(
            "Employee",
            employee,
            ["employee_name", "cell_number"],
            as_dict=True,
        ),
    )
    return {
        "employee": employee,
        "name": _text(details.get("employee_name")) if details else "",
        "phone": _text(details.get("cell_number")) if details else "",
    }


def _text(value: Any) -> str:
    return str(value or "").strip()
