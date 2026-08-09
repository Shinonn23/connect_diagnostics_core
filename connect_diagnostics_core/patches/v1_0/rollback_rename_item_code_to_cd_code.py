# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for rename_item_code_to_cd_code — one-way.

The forward patch renamed Item documents to their custom_cd_item_code value, rewriting the
document name across all linked transactions. Renaming back is unsafe once documents have
been transacted and the original names are not retained. No automatic reversal is performed;
reverse manually with a reviewed rename plan if ever required."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_rename_item_code_to_cd_code: no-op; Item renames are not automatically reversible (see docstring)."
    )
