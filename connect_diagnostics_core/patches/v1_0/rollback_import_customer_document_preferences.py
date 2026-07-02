# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for import_customer_document_preferences.

Resets the document / print preference fields back to their field defaults
(all ``use_*`` checks to 0, ``print_date`` to 1) for the customers that
were populated by the import.
"""

from __future__ import annotations

import frappe

from connect_diagnostics_core.patches.v1_0.import_customer_document_preferences import (
    FIELD_MAP,
    load_preferences,
)

_DEFAULTS: dict[str, int] = {
    fieldname: (1 if fieldname == "print_date" else 0) for fieldname in FIELD_MAP.values()
}


def execute() -> None:
    preferences = load_preferences()
    existing = set(
        frappe.get_all(
            "Customer",
            filters={"name": ["in", list(preferences)]},
            pluck="name",
        )
    )

    reset = 0
    for code in preferences:
        if code not in existing:
            continue
        frappe.db.set_value("Customer", code, dict(_DEFAULTS), update_modified=False)
        reset += 1

    frappe.logger(__name__).info(
        "rollback_import_customer_document_preferences: reset %s customers",
        reset,
    )
