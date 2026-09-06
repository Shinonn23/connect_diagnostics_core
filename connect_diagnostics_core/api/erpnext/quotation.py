# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Quotation-specific values for the Employee-backed print configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import frappe
from frappe import _
from frappe.desk.reportview import get_match_cond
from frappe.model.document import Document
from frappe.utils import cint, date_diff

from connect_diagnostics_core.api.erpnext import company as company_api
from connect_diagnostics_core.api.erpnext.print_configuration import (
    get_document_print_context,
    prepare_signature_for_print,
)
from connect_diagnostics_core.setup import quotation as quotation_setup


def validate_signatory_before_submit(doc: Document, method: str | None = None) -> None:
    """Require the Sales Contact when a Sales Representative signs.

    Managing Director selection happens per print in the sidebar, so it cannot
    be required on the Quotation itself at submit time.
    """
    signatory_type = (
        _text(doc.get("quotation_signatory_type")) or quotation_setup.SIGNATORY_SALES_REPRESENTATIVE
    )
    if signatory_type not in quotation_setup.SIGNATORY_TYPES:
        frappe.throw(_("Quotation signatory type is invalid."))
    if signatory_type == quotation_setup.SIGNATORY_SALES_REPRESENTATIVE and not _text(
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
    """Link query for the Quotation's Sales Contact Employee.

    Standard Frappe get_query/query convention: returns (name, description)
    tuples, not this app's {data, message} API shape -- this is a link-search
    hook, not an app API endpoint.
    """
    filters = dict(filters or {})
    signatory_type = _text(filters.get("quotation_signatory_type"))
    if signatory_type and signatory_type not in quotation_setup.SIGNATORY_TYPES:
        return []
    roles = quotation_setup.SIGNATORY_EMPLOYEE_ROLES[quotation_setup.SIGNATORY_SALES_REPRESENTATIVE]

    company = _text(filters.get("company"))
    company_condition = "and `tabEmployee`.company = %(company)s " if company else ""
    query = (
        "select `tabEmployee`.name, `tabEmployee`.employee_name "
        "from `tabEmployee` "
        "where `tabEmployee`.status = 'Active' "
        + company_condition
        + "and (`tabEmployee`.name like %(txt)s or `tabEmployee`.employee_name like %(txt)s) "
        "and exists (select 1 from `tabHas Role` "
        "where `tabHas Role`.parent = `tabEmployee`.user_id "
        "and `tabHas Role`.parenttype = 'User' "
        "and `tabHas Role`.role in %(roles)s) "
        + get_match_cond("Employee")
        + " order by `tabEmployee`.employee_name limit %(page_len)s offset %(start)s"
    )
    query_values: dict[str, Any] = {
        "roles": tuple(roles),
        "txt": "%" + txt + "%",
        "page_len": page_len,
        "start": start,
    }
    if company:
        query_values["company"] = company
    return cast(
        list[tuple[str, str]],
        frappe.db.sql(query, query_values),
    )


def get_quotation_print_context(doc: Document | Mapping[str, Any]) -> dict[str, Any]:
    """Build Quotation print values from the resolved configuration."""
    from connect_diagnostics_core.api.frappe.print_log import register_print

    context = get_document_print_context(doc, "quotation")
    language = _text(context.get("language")) or "Thai"
    sales_representative = _text(context.get("sales_representative_employee"))
    manager_signatory = _text(context.get("manager_signatory_employee"))
    signatory_action = (context.get("print_actions") or {}).get("signatory", {})

    result = {
        **context,
        # Overrides the raw "validity_text" document field spread in above:
        # this is the computed, language-rendered display text (custom
        # wording verbatim, or the Valid Till day-count), not the raw field.
        "validity_text": _validity_text(doc, context, language),
        "validity_is_custom": bool(cint(context.get("edit_validity_text"))),
        "delivery_terms": _text(context.get("quotation_delivery_terms")),
        # New workflow-backed quotations use the immutable action snapshot.
        # Keep the existing print-sidebar resolution only for legacy quotations
        # that predate the snapshot fields.
        "signatory": (
            _snapshot_signatory_details(context, signatory_action, language)
            if _action_has_snapshot(signatory_action)
            else _signatory_details(
                context,
                sales_representative,
                manager_signatory,
                _text(doc.get("company")),
                language,
            )
        ),
        "sales_contact": _employee_details(sales_representative),
        "copies": context["copies"],
    }
    register_print(doc, "quotation", result)
    return result


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
    context: Mapping[str, Any],
    sales_representative: str,
    manager_signatory: str,
    company: str,
    language: str,
) -> dict[str, Any]:
    """Resolve the selected Employee and signature image for one quotation."""
    signatory_type = _text(context.get("quotation_signatory_type"))
    caption = quotation_setup.SIGNATORY_CAPTIONS.get(signatory_type)
    if caption is None:
        frappe.throw(_("Quotation signatory type is required."))
        raise frappe.ValidationError(signatory_type)  # frappe.throw already raised

    caption_text = _caption_text(caption, language)
    if signatory_type == quotation_setup.SIGNATORY_SALES_REPRESENTATIVE:
        employee = sales_representative
        reason = _("Sales Representative is required when a Sales Representative signs the quotation.")
    elif signatory_type == quotation_setup.SIGNATORY_MANAGING_DIRECTOR:
        employee = manager_signatory
        reason = _("Manager Signatory is required when a Managing Director signs the quotation.")
        if employee and not _is_authorized_manager(employee, company):
            reason = _("The selected Manager Signatory is not authorized for this Company.")
            employee = ""
    else:
        employee = ""
        reason = _("Quotation signatory type is required.")

    details = _employee_details(employee)
    details.update({"caption": caption_text, "type": signatory_type})
    if not employee:
        details["ready"] = False
        details["reason"] = reason
    elif not details.get("name"):
        details["ready"] = False
        details["reason"] = _("The selected signatory Employee could not be found.")
    elif not details.get("signature"):
        details["ready"] = False
        details["reason"] = _("The selected signatory has no Quotation E-Signature configured.")
    else:
        details["reason"] = ""

    if _is_real_print_or_pdf_request() and not details.get("ready"):
        frappe.throw(details["reason"] or _("A ready signatory is required before printing."))
    return details


def _snapshot_signatory_details(
    context: Mapping[str, Any], action: Mapping[str, Any], language: str
) -> dict[str, Any]:
    """Build the Quotation signatory from the stored workflow action snapshot."""
    signatory_type = _text(context.get("quotation_signatory_type"))
    caption = quotation_setup.SIGNATORY_CAPTIONS.get(signatory_type)
    if caption is None:
        frappe.throw(_("Quotation signatory type is required."))
        raise frappe.ValidationError(signatory_type)  # frappe.throw already raised

    employee = _text(action.get("employee"))
    name = _text(action.get("name"))
    signature = _text(action.get("signature"))
    details = {
        "employee": employee,
        "name": name,
        "phone": "",
        "signature": signature,
        "acted_at": action.get("acted_at"),
        "ready": bool(employee and name and signature),
        "caption": _caption_text(caption, language),
        "type": signatory_type,
    }
    if not employee:
        details["reason"] = _("The signatory action has not recorded an Employee.")
    elif not name:
        details["reason"] = _("The signatory Employee could not be found.")
    elif not signature:
        # A missing Employee signature is deliberately non-blocking. The
        # action name and time remain valid evidence and the print leaves the
        # image area empty.
        details["reason"] = _("The signatory Employee has no signature.")
    else:
        details["reason"] = ""
    return details


def _action_has_snapshot(action: Mapping[str, Any]) -> bool:
    """Return whether a workflow action has written any snapshot value."""
    return bool(_text(action.get("employee")) or _text(action.get("signature")) or action.get("acted_at"))


def _caption_text(caption: tuple[str, str], language: str) -> str:
    thai, english = caption
    if language == "Thai":
        return thai
    if language == "English":
        return english
    return f"{thai} / {english}"


def _employee_details(employee: str) -> dict[str, Any]:
    if not employee:
        return {"employee": "", "name": "", "phone": "", "signature": "", "ready": False}

    details = cast(
        dict[str, Any] | None,
        frappe.db.get_value(
            "Employee",
            employee,
            ["employee_name", "cell_number", "quotation_signature"],
            as_dict=True,
        ),
    )
    signature = prepare_signature_for_print(_text(details.get("quotation_signature"))) if details else ""
    return {
        "employee": employee,
        "name": _text(details.get("employee_name")) if details else "",
        "phone": _text(details.get("cell_number")) if details else "",
        "signature": signature,
        "ready": bool(details and details.get("employee_name") and signature),
    }


def _is_authorized_manager(employee: str, company: str) -> bool:
    if not employee or not company:
        return False
    return any(
        _text(row.get("employee")) == employee
        for row in company_api.get_quotation_authorized_signatories(company)
    )


def _is_real_print_or_pdf_request() -> bool:
    form_dict = getattr(frappe.local, "form_dict", None)
    if form_dict and cint(form_dict.get("trigger_print")):
        return True
    flags = getattr(frappe.local, "flags", None)
    return bool(flags and flags.get("cd_pdf_request"))


def _text(value: Any) -> str:
    return str(value or "").strip()
