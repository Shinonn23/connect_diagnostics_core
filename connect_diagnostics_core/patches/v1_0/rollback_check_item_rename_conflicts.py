# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for check_item_rename_conflicts — no-op by design.

The forward patch is read-only: it inspects Item names for rename conflicts and throws if any
exist, making no database change. There is nothing to reverse."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_check_item_rename_conflicts: no-op; the forward patch is read-only and makes no changes."
    )
