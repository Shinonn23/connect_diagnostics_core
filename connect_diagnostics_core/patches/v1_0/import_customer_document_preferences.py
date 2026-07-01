# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Import per-customer document / print preferences from the source spreadsheet.

The preferences originate from ``Customer terms และเอกสารใบกำกับภาษี.xlsx`` and
were extracted into ``data/customer_document_preferences.json`` (keyed by Customer
name / CD code). This patch backfills the ``cd_use_*`` and ``cd_print_date`` custom
fields on existing Customer records.

Idempotent: re-running sets the same values. Customers absent from the site are
skipped (logged as a summary count, never row-by-row).
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup import customer as customer_setup

_DATA_FILE = Path(__file__).parent / "data" / "customer_document_preferences.json"

# JSON key -> Customer custom fieldname
FIELD_MAP: dict[str, str] = {
    "use_quotation": "cd_use_quotation",
    "use_customer_po": "cd_use_customer_po",
    "use_tax_invoice": "cd_use_tax_invoice",
    "use_receipt": "cd_use_receipt",
    "use_abbreviated_tax_invoice": "cd_use_abbreviated_tax_invoice",
    "print_date": "cd_print_date",
}


def load_preferences() -> dict[str, dict[str, int]]:
    """Return the extracted preference map ``{customer_code: {key: 0|1}}``."""
    with _DATA_FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


def execute() -> None:
    # Patches run before the after_migrate hook that creates these fields, so
    # ensure the Customer custom fields exist before writing to them.
    create_custom_fields(customer_setup.CUSTOM_FIELDS, ignore_validate=True)

    preferences = load_preferences()
    existing = set(
        frappe.get_all(
            "Customer",
            filters={"name": ["in", list(preferences)]},
            pluck="name",
        )
    )

    updated = 0
    for code, prefs in preferences.items():
        if code not in existing:
            continue
        values = {FIELD_MAP[key]: int(value) for key, value in prefs.items() if key in FIELD_MAP}
        frappe.db.set_value("Customer", code, values, update_modified=False)
        updated += 1

    skipped = len(preferences) - updated
    frappe.logger(__name__).info(
        "import_customer_document_preferences: updated %s, skipped %s (missing on site)",
        updated,
        skipped,
    )
