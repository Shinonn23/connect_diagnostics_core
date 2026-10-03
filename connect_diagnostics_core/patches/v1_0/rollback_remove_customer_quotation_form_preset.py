# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_customer_quotation_form_preset — one-way.

The removed field was a Select whose options came from the retired quotation_setup
module (FORM_PRESETS) and whose visibility depended on other retired fields. That
definition can no longer be reconstructed faithfully, and the per-record preset values
were dropped with the column. No automatic reversal is performed."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_remove_customer_quotation_form_preset: no-op; field definition and data are not recoverable (retired quotation preset module)."
    )
