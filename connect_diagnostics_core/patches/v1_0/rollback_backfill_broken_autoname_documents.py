# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for backfill_broken_autoname_documents — one-way.

The forward patch renamed documents from their broken literal
{YY-BE}{MM-DOC} name to the resolved year/month name, rewriting the document
name across all linked transactions. Renaming back is unsafe once documents
have been transacted and the original broken names are not retained, and
would reintroduce the very defect the forward patch fixes. No automatic
reversal is performed; reverse manually with a reviewed rename plan if ever
required.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_backfill_broken_autoname_documents: no-op; renames are not "
        "automatically reversible (see docstring)."
    )
