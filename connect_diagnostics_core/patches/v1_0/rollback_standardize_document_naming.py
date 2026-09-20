# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Remove the go-live document naming Property Setters without changing data."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute() -> None:
    import json
    from pathlib import Path

    from connect_diagnostics_core.setup.document_naming import PROPERTY_SETTERS

    fixture_path = Path(__file__).parents[2] / "fixtures" / "property_setter.json"
    legacy_setters = {
        (row["doc_type"], row.get("field_name"), row["property"]): row["value"]
        for row in json.loads(fixture_path.read_text())
        if row.get("doctype") == "Property Setter"
    }

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
                    key = (doctype, fieldname, prop)
                    legacy_value = legacy_setters.get(key)
                    if legacy_value is None:
                        frappe.delete_doc(
                            "Property Setter",
                            property_setter.name,
                            ignore_permissions=True,
                            force=True,
                        )
                    else:
                        make_property_setter(
                            doctype,
                            fieldname,
                            prop,
                            legacy_value,
                            _property_type,
                            for_doctype=fieldname is None,
                            validate_fields_for_doctype=False,
                        )
        frappe.clear_cache(doctype=doctype)
    frappe.db.commit()
