# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Backfill quotation_delivery_terms on already-submitted Quotations.

Delivery Terms used to be a print-sidebar-only override, never saved on the
document, so every historical submitted Quotation has it empty. Backfills
both delivery_terms_template and quotation_delivery_terms to the seeded
default Delivery Terms Template -- the wording every historical Quotation
print has actually shown -- since there is no per-document signal to compute
this from (unlike the signatory backfill, which has an owner to resolve from).

This patch runs in ``post_model_sync``, which is *before* this app's own
``after_migrate`` hook creates ``delivery_terms_section``/``delivery_terms_template``/
``quotation_delivery_terms`` (see ``connect_diagnostics_core.setup.after_migrate``).
So, like ``backfill_national_id_display``, it creates those fields itself first --
reusing the same definitions from ``setup.quotation.CUSTOM_FIELDS`` rather than
duplicating them -- to be correct on both a fresh migrate and a rerun.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup import quotation as quotation_setup

QUOTATION = "Quotation"
DELIVERY_TERMS_FIELDNAMES = ("delivery_terms_section", "delivery_terms_template", "quotation_delivery_terms")
DELIVERY_TERMS_FIELDS = [
    field
    for field in quotation_setup.CUSTOM_FIELDS[QUOTATION]
    if field["fieldname"] in DELIVERY_TERMS_FIELDNAMES
]


def execute() -> None:
    create_custom_fields({QUOTATION: DELIVERY_TERMS_FIELDS}, update=True)
    quotation_setup.ensure_configuration()

    backfilled = 0
    quotations = frappe.get_all(
        QUOTATION,
        filters={
            "docstatus": 1,
            "quotation_delivery_terms": ("in", ("", None)),
        },
        pluck="name",
    )
    for name in quotations:
        frappe.db.set_value(
            QUOTATION,
            name,
            {
                "delivery_terms_template": quotation_setup.DEFAULT_DELIVERY_TERMS_TEMPLATE,
                "quotation_delivery_terms": quotation_setup.DEFAULT_DELIVERY_TERMS_TEMPLATE,
            },
        )
        backfilled += 1

    frappe.db.commit()
    frappe.logger(__name__).info(f"backfill_quotation_delivery_terms: backfilled {backfilled} document(s)")
