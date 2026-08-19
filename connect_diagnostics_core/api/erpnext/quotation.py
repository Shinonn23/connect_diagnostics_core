# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Quotation-specific values for the Customer-backed print configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import frappe
from frappe import _
from frappe.desk.reportview import get_match_cond
from frappe.model.document import Document
from frappe.utils import cint, date_diff

from connect_diagnostics_core.api.erpnext.print_configuration import get_document_print_context
from connect_diagnostics_core.setup import quotation as quotation_setup


def validate_signatory_before_submit(doc: Document, method: str | None = None) -> None:
    """Require an Employee whenever the signatory type prints a name.

    Mirrors `_signatory_details()`'s own resolution and the same
    `SIGNATORY_SALES_REPRESENTATIVE` fallback `print_documents.SCALAR_DEFAULTS`
    uses, so this check and the print-time throw can never disagree.
    """
    signatory_type = (
        _text(doc.get("quotation_signatory_type")) or quotation_setup.SIGNATORY_SALES_REPRESENTATIVE
    )
    if signatory_type in quotation_setup.SIGNATORY_PRINTS_NAME and not _text(
        doc.get("sales_representative_employee")
    ):
        frappe.throw(_("Sales Representative is required when a Sales Representative signs the quotation."))


def validate_delivery_terms_before_submit(doc: Document, method: str | None = None) -> None:
    """Require Delivery Terms before a Quotation is submitted."""
    if not _text(doc.get("quotation_delivery_terms")):
        frappe.throw(_("Delivery Terms is required before submitting a Quotation."))


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def signatory_employee_query(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict[str, Any] | None,
) -> list[tuple[str, str]]:
    """Link query for sales_representative_employee, filtered by signatory type.

    Standard Frappe get_query/query convention: returns (name, description)
    tuples, not this app's {data, message} API shape -- this is a link-search
    hook, not an app API endpoint.
    """
    filters = dict(filters or {})
    signatory_type = _text(filters.get("quotation_signatory_type"))
    roles = quotation_setup.SIGNATORY_EMPLOYEE_ROLES.get(signatory_type, ())
    if not roles:
        return []

    query = (
        "select e.name, e.employee_name "
        "from `tabEmployee` e "
        "inner join `tabHas Role` hr on hr.parent = e.user_id and hr.role in %(roles)s "
        "where e.status = 'Active' "
        "and (e.name like %(txt)s or e.employee_name like %(txt)s) "
        + get_match_cond("Employee")
        + " order by e.employee_name limit %(page_len)s offset %(start)s"
    )
    return cast(
        list[tuple[str, str]],
        frappe.db.sql(
            query,
            {"roles": tuple(roles), "txt": "%" + txt + "%", "page_len": page_len, "start": start},
        ),
    )


def get_quotation_print_context(doc: Document | Mapping[str, Any]) -> dict[str, Any]:
    """Build Quotation print values from the resolved configuration."""
    context = get_document_print_context(doc, "quotation")
    language = _text(context.get("language")) or "Thai"
    sales_representative = _text(context.get("sales_representative_employee"))

    return {
        **context,
        # Overrides the raw "validity_text" document field spread in above:
        # this is the computed, language-rendered display text (custom
        # wording verbatim, or the Valid Till day-count), not the raw field.
        "validity_text": _validity_text(doc, context, language),
        "validity_is_custom": bool(cint(context.get("edit_validity_text"))),
        "delivery_terms": _text(context.get("quotation_delivery_terms")),
        "signatory": _signatory_details(context, sales_representative, language),
        "sales_contact": _employee_details(sales_representative),
        "copies": context["copies"],
    }


def _validity_text(doc: Document | Mapping[str, Any], context: Mapping[str, Any], language: str) -> str:
    if cint(context.get("edit_validity_text")):
        custom_validity_text = _text(context.get("validity_text"))
        if not custom_validity_text:
            frappe.throw(_("Validity Text is required when Edit validity text is checked."))
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
