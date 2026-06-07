from __future__ import annotations

import frappe

ROLLBACK_PROPERTIES = ("collapsible", "collapsible_depends_on")


def execute() -> None:
    fields = _get_disabled_property_setter_fields()
    doctypes_to_clear = set()

    for doctype, fieldname in sorted(fields):
        for property_name in ROLLBACK_PROPERTIES:
            _delete_property_setter(doctype, fieldname, property_name)
        doctypes_to_clear.add(doctype)

    for doctype in sorted(doctypes_to_clear):
        frappe.clear_cache(doctype=doctype)


def _get_disabled_property_setter_fields() -> set[tuple[str, str]]:
    return {
        (row.get("doc_type"), row.get("field_name"))
        for row in frappe.get_all(
            "Property Setter",
            filters={
                "doctype_or_field": "DocField",
                "property": ("in", ROLLBACK_PROPERTIES),
                "field_name": ("is", "set"),
            },
            fields=["doc_type", "field_name"],
            order_by=None,
        )
        if row.get("doc_type") and row.get("field_name")
    }


def _delete_property_setter(doctype: str, fieldname: str, property_name: str) -> None:
    property_setter = frappe.db.exists(
        "Property Setter",
        {
            "doc_type": doctype,
            "field_name": fieldname,
            "property": property_name,
        },
    )

    if property_setter:
        frappe.delete_doc("Property Setter", property_setter, force=True)
