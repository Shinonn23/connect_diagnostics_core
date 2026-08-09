from __future__ import annotations

import frappe

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

ROLLBACK_PROPERTIES = ("reqd", "label")


def execute() -> None:
    for doctype in TERMS_DOCTYPES:
        for property_name in ROLLBACK_PROPERTIES:
            _delete_property_setter(doctype, "terms", property_name)
        frappe.clear_cache(doctype=doctype)


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
