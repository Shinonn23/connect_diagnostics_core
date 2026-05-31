import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

COLLAPSIBLE_PROPERTIES = {
    "collapsible": ("0", "Check"),
    "collapsible_depends_on": ("", "Data"),
}


def execute():
    standard_fields = _get_collapsible_fields("DocField", "parent")
    custom_fields = _get_collapsible_fields("Custom Field", "dt")
    property_setter_fields = _get_collapsible_property_setter_fields()
    doctypes_to_clear = set()

    for doctype, fieldname in custom_fields:
        frappe.db.set_value(
            "Custom Field",
            {"dt": doctype, "fieldname": fieldname},
            {"collapsible": 0, "collapsible_depends_on": None},
            update_modified=False,
        )
        doctypes_to_clear.add(doctype)

    for doctype, fieldname in standard_fields | property_setter_fields:
        for property_name, (value, property_type) in COLLAPSIBLE_PROPERTIES.items():
            _set_property_setter(doctype, fieldname, property_name, value, property_type)
        doctypes_to_clear.add(doctype)

    for doctype in doctypes_to_clear:
        frappe.clear_cache(doctype=doctype)


def _get_collapsible_fields(doctype, parent_field):
    return {
        (row[parent_field], row.fieldname)
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
    }


def _get_collapsible_property_setter_fields():
    return {
        (row.doc_type, row.field_name)
        for row in frappe.get_all(
            "Property Setter",
            filters={
                "doctype_or_field": "DocField",
                "property": ("in", COLLAPSIBLE_PROPERTIES),
                "field_name": ("is", "set"),
            },
            fields=["doc_type", "field_name"],
            order_by=None,
        )
    }


def _set_property_setter(doctype, fieldname, property_name, value, property_type):
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
