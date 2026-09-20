# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback fields restored for ERPNext Thailand withholding compatibility.

Any values entered after the forward patch must be exported before running this
rollback because removing the Custom Fields also removes their database columns.
"""

from __future__ import annotations

import frappe

from connect_diagnostics_core.patches.v1_0.restore_thai_withholding_tax_fields import (
    THAI_WITHHOLDING_FIELDNAMES,
)
from connect_diagnostics_core.patches.v1_0.strip_custom_prefix_from_field_names import _drop_old


def execute() -> None:
    """Remove only the fields introduced by the matching forward patch."""
    for doctype, fieldnames in THAI_WITHHOLDING_FIELDNAMES.items():
        for fieldname in fieldnames:
            _drop_old(doctype, fieldname)
    frappe.db.commit()
