# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for backfill_quotation_delivery_terms -- one-way.

Once a backfilled delivery_terms_template/quotation_delivery_terms is saved,
it is indistinguishable from a value a human entered or edited afterward.
Clearing it back out would risk erasing a legitimate later edit, not just
undoing the backfill, so no automatic reversal is performed.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_backfill_quotation_delivery_terms: no-op; backfilled values "
        "are not automatically reversible (see docstring)."
    )
