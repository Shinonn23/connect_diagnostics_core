# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Remove the go-live document naming Property Setters without changing data."""

from __future__ import annotations

import frappe


def execute() -> None:
    from connect_diagnostics_core.setup.document_naming import PROPERTY_SETTERS

    for doctype, setters in PROPERTY_SETTERS.items():
        for fieldname, prop, value, _property_type in setters:
            filters: dict[str, str | list[str]] = {"doc_type": doctype, "property": prop}
            if fieldname is None:
                filters["field_name"] = ["is", "not set"]
            else:
                filters["field_name"] = fieldname
            property_setters = frappe.get_all(
                "Property Setter",
                filters=filters,
                fields=["name", "value"],
            )
            for property_setter in property_setters:
                if property_setter.value == value:
                    frappe.delete_doc(
                        "Property Setter",
                        property_setter.name,
                        ignore_permissions=True,
                        force=True,
                    )
        frappe.clear_cache(doctype=doctype)
    frappe.db.commit()
