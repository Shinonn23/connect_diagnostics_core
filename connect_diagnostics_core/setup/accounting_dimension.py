# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Register Connect Diagnostics Accounting Dimensions (Department, Territory)."""

from __future__ import annotations

from dataclasses import dataclass

import frappe


@dataclass(frozen=True)
class DimensionSpec:
    """One ERPNext Accounting Dimension this app owns."""

    document_type: str
    fieldname: str
    label: str


# Both reuse `fieldname`s that already exist as custom (or native) fields on the
# Sales/Purchase transaction doctypes, so ERPNext's `validate_fieldname_conflict`
# leaves those untouched and only creates the field where it is still missing —
# most importantly GL Entry and Journal Entry Account, so the value reaches the ledger.
DEPARTMENT_DIMENSION = DimensionSpec("Department", "department", "Department")
TERRITORY_DIMENSION = DimensionSpec("Territory", "territory", "Territory")
DIMENSIONS = (DEPARTMENT_DIMENSION, TERRITORY_DIMENSION)


def ensure_configuration() -> None:
    """Register each Accounting Dimension idempotently.

    mandatory_for_bs/mandatory_for_pl and dimension_defaults are deliberately not
    set here: those are business-rule decisions for the owner to make in Desk.
    """
    for dimension in DIMENSIONS:
        if frappe.db.exists("Accounting Dimension", {"document_type": dimension.document_type}):
            continue
        frappe.get_doc(
            {
                "doctype": "Accounting Dimension",
                "document_type": dimension.document_type,
                "fieldname": dimension.fieldname,
                "label": dimension.label,
            }
        ).insert(ignore_permissions=True)
