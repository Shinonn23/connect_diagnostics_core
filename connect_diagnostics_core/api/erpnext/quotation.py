# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Quotation print-configuration defaults, validation, and rendering context."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, date_diff

from connect_diagnostics_core.setup import quotation as quotation_setup

_CUSTOMER_CONFIGURATION_FIELDS = (
    "quotation_form_preset",
    "show_quotation_date",
    "quotation_signatory_type",
    "quotation_validity_mode",
    "quotation_custom_validity_text",
    "quotation_delivery_terms",
    "quotation_language",
    "quotation_original_count",
    "quotation_copy_count",
)


def before_validate(doc: Document, method: str | None = None) -> None:
    """Default new records, preserve preset semantics, and validate signatory sources."""
    if doc.is_new() and not _text(doc.get("quotation_form_preset")):
        doc.update(quotation_setup.DEFAULT_PRINT_CONFIGURATION)

    _fill_missing_preset_values(doc)
    _default_sales_representative(doc)
    _mark_modified_preset_as_custom(doc)
    _validate_custom_validity(doc)
    _validate_delivery_terms(doc)
    _validate_signatory_source(doc)


@frappe.whitelist()
def get_print_configuration_defaults(
    customer: str,
    sales_person: str | None = None,
) -> dict[str, Any]:
    """Return a Customer's Quotation settings as a one-time editable snapshot."""
    frappe.has_permission("Quotation", "create", throw=True)
    frappe.has_permission("Customer", "read", customer, throw=True)

    values = cast(
        dict[str, Any] | None,
        frappe.db.get_value(
            "Customer",
            customer,
            list(_CUSTOMER_CONFIGURATION_FIELDS),
            as_dict=True,
        ),
    )
    if values is None:
        frappe.throw(_("Customer {0} was not found.").format(frappe.bold(customer)))
    customer_values = cast(dict[str, Any], values)

    configuration = dict(quotation_setup.DEFAULT_PRINT_CONFIGURATION)
    configuration.update(
        {
            fieldname: customer_values[fieldname]
            for fieldname in _CUSTOMER_CONFIGURATION_FIELDS
            if customer_values.get(fieldname) is not None
        }
    )
    configuration["quotation_sales_representative"] = _text(sales_person) or _first_customer_sales_person(
        customer
    )

    return {
        "data": configuration,
        "message": _("Quotation print configuration loaded from Customer."),
    }


def get_quotation_print_context(doc: Document | Mapping[str, Any]) -> dict[str, Any]:
    """Build deterministic language, copy, validity, and signatory print values."""
    language = _text(doc.get("quotation_language")) or "Thai"
    original_count = max(cint(doc.get("quotation_original_count")), 0)
    copy_count = max(cint(doc.get("quotation_copy_count")), 0)
    if doc.get("quotation_original_count") is None:
        original_count = 1
    show_date_value = doc.get("show_quotation_date")

    return {
        "language": language,
        "show_thai": language in {"Thai", "Thai / English"},
        "show_english": language in {"English", "Thai / English"},
        "show_date": True if show_date_value is None else cint(show_date_value) != 0,
        "validity_text": _validity_text(doc, language),
        "delivery_terms": _text(doc.get("quotation_delivery_terms")),
        "signatory": _signatory_details(doc),
        "sales_contact": _sales_contact_details(doc),
        "copies": _copy_contexts(original_count, copy_count, language),
    }


def _fill_missing_preset_values(doc: Document) -> None:
    expected = quotation_setup.PRESET_VALUES.get(_text(doc.get("quotation_form_preset")))
    if expected is None:
        return

    for fieldname, value in expected.items():
        if doc.get(fieldname) is None:
            doc.set(fieldname, value)

    for fieldname in ("quotation_language", "quotation_original_count", "quotation_copy_count"):
        if doc.get(fieldname) is None:
            doc.set(fieldname, quotation_setup.DEFAULT_PRINT_CONFIGURATION[fieldname])


def _mark_modified_preset_as_custom(doc: Document) -> None:
    expected = quotation_setup.PRESET_VALUES.get(_text(doc.get("quotation_form_preset")))
    if expected is None:
        return

    for fieldname, value in expected.items():
        actual = cint(doc.get(fieldname)) if isinstance(value, int) else _text(doc.get(fieldname))
        if actual != value:
            doc.set("quotation_form_preset", quotation_setup.FORM_PRESET_CUSTOM)
            return


def _default_sales_representative(doc: Document) -> None:
    if _text(doc.get("quotation_signatory_type")) != quotation_setup.SIGNATORY_SALES_REPRESENTATIVE or _text(
        doc.get("quotation_sales_representative")
    ):
        return

    sales_team = cast(list[Document], doc.get("sales_team") or [])
    if sales_team:
        doc.set(
            "quotation_sales_representative",
            _text(sales_team[0].get("sales_person")),
        )


def _validate_custom_validity(doc: Document) -> None:
    if _text(doc.get("quotation_validity_mode")) == quotation_setup.VALIDITY_CUSTOM_TEXT and not _text(
        doc.get("quotation_custom_validity_text")
    ):
        frappe.throw(_("Custom Validity Text is required when Validity Mode is Custom Text."))


def _validate_delivery_terms(doc: Document) -> None:
    if not _text(doc.get("quotation_delivery_terms")):
        frappe.throw(_("Delivery Terms are required for Quotation."))


def _validate_signatory_source(doc: Document) -> None:
    signatory_type = _text(doc.get("quotation_signatory_type"))
    if signatory_type == quotation_setup.SIGNATORY_SALES_REPRESENTATIVE:
        sales_person = _text(doc.get("quotation_sales_representative"))
        if not sales_person:
            frappe.throw(_("Sales Representative is required for this Quotation form."))
        if not frappe.db.get_value("Sales Person", sales_person, "employee"):
            frappe.throw(
                _("Sales Person {0} must be linked to an Employee.").format(frappe.bold(sales_person))
            )
    elif signatory_type == quotation_setup.SIGNATORY_MANAGING_DIRECTOR:
        company = _text(doc.get("company"))
        employee = (
            frappe.db.get_value("Company", company, "quotation_authorized_signatory_employee")
            if company
            else None
        )
        if not employee:
            frappe.throw(
                _("Quotation Authorized Signatory Employee must be configured on Company {0}.").format(
                    frappe.bold(company)
                )
            )


def _first_customer_sales_person(customer: str) -> str:
    sales_people = cast(
        list[str],
        frappe.get_all(
            "Sales Team",
            filters={"parent": customer, "parenttype": "Customer"},
            pluck="sales_person",
            order_by="idx asc",
            limit_page_length=1,
        ),
    )
    return sales_people[0] if sales_people else ""


def _validity_text(doc: Document | Mapping[str, Any], language: str) -> str:
    if _text(doc.get("quotation_validity_mode")) == quotation_setup.VALIDITY_CUSTOM_TEXT:
        return _text(doc.get("quotation_custom_validity_text"))

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


def _signatory_details(doc: Document | Mapping[str, Any]) -> dict[str, str]:
    signatory_type = _text(doc.get("quotation_signatory_type"))
    employee = ""
    if signatory_type == quotation_setup.SIGNATORY_SALES_REPRESENTATIVE:
        sales_person = _text(doc.get("quotation_sales_representative"))
        employee = _text(frappe.db.get_value("Sales Person", sales_person, "employee"))
    elif signatory_type == quotation_setup.SIGNATORY_MANAGING_DIRECTOR:
        company = _text(doc.get("company"))
        employee = _text(frappe.db.get_value("Company", company, "quotation_authorized_signatory_employee"))

    if not employee:
        return {"employee": "", "name": "", "designation": "", "phone": ""}

    details = cast(
        dict[str, Any] | None,
        frappe.db.get_value(
            "Employee",
            employee,
            ["employee_name", "designation", "cell_number"],
            as_dict=True,
        ),
    )
    return {
        "employee": employee,
        "name": _text(details.get("employee_name")) if details else "",
        "designation": _text(details.get("designation")) if details else "",
        "phone": _text(details.get("cell_number")) if details else "",
    }


def _sales_contact_details(doc: Document | Mapping[str, Any]) -> dict[str, str]:
    sales_person = _text(doc.get("quotation_sales_representative"))
    if not sales_person:
        return {"employee": "", "name": "", "designation": "", "phone": ""}

    employee = _text(frappe.db.get_value("Sales Person", sales_person, "employee"))
    if not employee:
        return {"employee": "", "name": "", "designation": "", "phone": ""}

    details = cast(
        dict[str, Any] | None,
        frappe.db.get_value(
            "Employee",
            employee,
            ["employee_name", "designation", "cell_number"],
            as_dict=True,
        ),
    )
    return {
        "employee": employee,
        "name": _text(details.get("employee_name")) if details else "",
        "designation": _text(details.get("designation")) if details else "",
        "phone": _text(details.get("cell_number")) if details else "",
    }


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
    return copies


def _copy_label(thai: str, english: str, index: int, count: int, language: str) -> str:
    suffix = f" {index}/{count}" if count > 1 else ""
    if language == "Thai":
        return f"{thai}{suffix}"
    if language == "English":
        return f"{english}{suffix}"
    return f"{thai} / {english}{suffix}"


def _text(value: Any) -> str:
    return str(value or "").strip()
