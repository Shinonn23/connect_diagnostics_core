# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for sync_sales_invoice_print_format — one-way (idempotent sync).

The forward patch reloads the app-owned Sales Invoice Print Format from source. There is no
prior version to restore to; to change the rendered format, edit the source and re-run the
forward patch. No automatic reversal is performed."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_sync_sales_invoice_print_format: no-op; re-run the forward patch to resync the Print Format from source."
    )
