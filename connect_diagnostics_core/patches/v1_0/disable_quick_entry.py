from __future__ import annotations

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute() -> None:
    doctypes_to_disable = _get_quick_entry_doctypes() | _get_quick_entry_property_setter_doctypes()

    for doctype in sorted(doctypes_to_disable):
        _set_quick_entry_property_setter(doctype)
        frappe.clear_cache(doctype=doctype)


def _get_quick_entry_doctypes() -> set[str]:
    return {
        row.get("name")
        for row in frappe.get_all(
            "DocType",
            filters={"quick_entry": 1},
            fields=["name"],
            order_by=None,
        )
        if row.get("name")
    }


def _get_quick_entry_property_setter_doctypes() -> set[str]:
    return {
        row.get("doc_type")
        for row in frappe.get_all(
            "Property Setter",
            filters={
                "doctype_or_field": "DocType",
                "field_name": ("is", "not set"),
                "property": "quick_entry",
            },
            fields=["doc_type"],
            order_by=None,
        )
        if row.get("doc_type")
    }


def _set_quick_entry_property_setter(doctype: str) -> None:
    property_setter = frappe.db.exists(
        "Property Setter",
        {
            "doc_type": doctype,
            "field_name": ("is", "not set"),
            "property": "quick_entry",
        },
    )

    if property_setter:
        frappe.db.set_value(
            "Property Setter",
            property_setter,
            "value",
            "0",
            update_modified=False,
        )
        return

    make_property_setter(
        doctype,
        None,
        "quick_entry",
        "0",
        "Check",
        for_doctype=True,
        validate_fields_for_doctype=False,
    )
