# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_item_regulation_class_field — one-way.

Recreating this Link field requires its target DocType, "Regulation Class", to exist —
but that DocType is retired by remove_regulation_class_doctype with a one-way rollback
of its own (its JSON/controller files are deleted from the repo, not just the DB record).
No automatic reversal is performed here either; restore both from git history if the
field must come back.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_remove_item_regulation_class_field: no-op; the field's target DocType "
        "(Regulation Class) is not recoverable by patch. Restore both from git history if needed."
    )
