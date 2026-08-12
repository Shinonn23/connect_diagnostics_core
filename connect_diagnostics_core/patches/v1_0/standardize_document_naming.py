# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Install the go-live document naming policy."""

from __future__ import annotations

import frappe


def execute() -> None:
    from connect_diagnostics_core.setup import document_naming

    document_naming.apply()
    frappe.db.commit()
