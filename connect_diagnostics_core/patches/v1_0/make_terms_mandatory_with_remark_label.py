from __future__ import annotations

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

TERMS_DOCTYPES = (
    "Blanket Order",
    "Delivery Note",
    "Material Request",
    "POS Invoice",
    "Purchase Invoice",
    "Purchase Order",
    "Purchase Receipt",
    "Quotation",
    "Request for Quotation",
    "Sales Invoice",
    "Sales Order",
    "Supplier Quotation",
    "Terms and Conditions",
)

TERMS_PROPERTIES = {
    "reqd": ("1", "Check"),
    "label": ("Terms and Conditions Content (Remark)", "Data"),
}


def execute() -> None:
    for doctype in TERMS_DOCTYPES:
        for property_name, (value, property_type) in TERMS_PROPERTIES.items():
            _set_property_setter(doctype, "terms", property_name, value, property_type)
        frappe.clear_cache(doctype=doctype)


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
