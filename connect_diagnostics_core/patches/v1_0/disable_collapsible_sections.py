from __future__ import annotations

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

COLLAPSIBLE_PROPERTIES = {
    "collapsible": ("0", "Check"),
    "collapsible_depends_on": ("", "Data"),
}


def execute() -> None:
    standard_fields = _get_collapsible_fields("DocField", "parent")
    custom_fields = _get_collapsible_fields("Custom Field", "dt")
    property_setter_fields = _get_collapsible_property_setter_fields()
    doctypes_to_clear = set()

    for doctype, fieldname in sorted(custom_fields):
        frappe.db.set_value(
            "Custom Field",
            {"dt": doctype, "fieldname": fieldname},
            {"collapsible": 0, "collapsible_depends_on": None},
            update_modified=False,
        )
        doctypes_to_clear.add(doctype)

    for doctype, fieldname in sorted(standard_fields | property_setter_fields):
        for property_name, (value, property_type) in COLLAPSIBLE_PROPERTIES.items():
            _set_property_setter(doctype, fieldname, property_name, value, property_type)
        doctypes_to_clear.add(doctype)

    for doctype in sorted(doctypes_to_clear):
        frappe.clear_cache(doctype=doctype)


def _get_collapsible_fields(doctype: str, parent_field: str) -> set[tuple[str, str]]:
    return {
        (row.get(parent_field), row.get("fieldname"))
        for row in frappe.get_all(
            doctype,
            filters={"fieldtype": "Section Break"},
            or_filters={
                "collapsible": 1,
                "collapsible_depends_on": ("is", "set"),
            },
            fields=[parent_field, "fieldname"],
            order_by=None,
        )
        if row.get(parent_field) and row.get("fieldname")
    }


def _get_collapsible_property_setter_fields() -> set[tuple[str, str]]:
    return {
        (row.get("doc_type"), row.get("field_name"))
        for row in frappe.get_all(
            "Property Setter",
            filters={
                "doctype_or_field": "DocField",
                "property": ("in", tuple(COLLAPSIBLE_PROPERTIES)),
                "field_name": ("is", "set"),
            },
            fields=["doc_type", "field_name"],
            order_by=None,
        )
        if row.get("doc_type") and row.get("field_name")
    }


def _set_property_setter(
    doctype: str, fieldname: str, property_name: str, value: str, property_type: str
) -> None:
    property_setter = frappe.db.exists(
        "Property Setter",
        {
            "doc_type": doctype,
            "field_name": fieldname,
            "property": property_name,
        },
    )

    if property_setter:
        frappe.db.set_value(
            "Property Setter",
            property_setter,
            "value",
            value,
            update_modified=False,
        )
        return

    make_property_setter(
        doctype,
        fieldname,
        property_name,
        value,
        property_type,
        validate_fields_for_doctype=False,
    )
