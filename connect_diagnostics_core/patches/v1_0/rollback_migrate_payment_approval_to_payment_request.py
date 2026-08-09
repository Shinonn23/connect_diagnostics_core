# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for migrate_payment_approval_to_payment_request — one-way.

The forward patch migrated the legacy payment-approval configuration onto the Payment Request
workflow. Reversing it would require reinstating the retired approval doctype, roles, and
in-flight state, which are not retained. No automatic reversal is performed."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_migrate_payment_approval_to_payment_request: no-op; legacy payment-approval configuration is not restorable."
    )
