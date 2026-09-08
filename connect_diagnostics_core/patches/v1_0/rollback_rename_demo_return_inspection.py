# Copyright (c) 2026, Siwat Sroisuwan and contributors

"""Reverse the inspection rename when restoring a pre-release backup."""

from __future__ import annotations

import frappe

from connect_diagnostics_core.patches.v1_0.rename_demo_return_inspection import RENAMES


def execute() -> None:
    for doctype, old_name, new_name in reversed(RENAMES):
        if frappe.db.exists(doctype, new_name) and not frappe.db.exists(doctype, old_name):
            frappe.rename_doc(doctype, new_name, old_name, force=True)
