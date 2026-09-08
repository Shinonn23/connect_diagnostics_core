# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Block migration until combined prototype Demo/Loan values are classified."""

from __future__ import annotations

import frappe
from frappe import _

LEGACY_USAGE = "Customer Demo / Loan"


def execute() -> None:
    if not frappe.db.has_column("Material Request", "request_usage"):
        return
    documents = frappe.get_all(
        "Material Request", filters={"request_usage": LEGACY_USAGE}, pluck="name", limit=20
    )
    if not documents:
        return
    frappe.throw(
        _(
            "Choose Customer Demo or Customer Loan on these Material Requests before migration: {0}. "
            "The migration will not guess the business meaning."
        ).format(", ".join(documents))
    )
