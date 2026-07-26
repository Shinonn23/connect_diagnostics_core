# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback helper for the irreversible DKSH Sales Settings retirement."""

from __future__ import annotations

import frappe


def execute() -> None:
    """Warn that restoring the retired settings requires restoring the prior source and data backup."""
    frappe.logger(__name__).warning(
        "DKSH Sales Settings metadata and Single values were permanently retired; "
        "restore a database backup and the prior app revision to recover them."
    )
    frappe.clear_cache()
