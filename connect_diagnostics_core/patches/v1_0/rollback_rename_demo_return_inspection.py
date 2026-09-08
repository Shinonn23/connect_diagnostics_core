# Copyright (c) 2026, Siwat Sroisuwan and contributors

"""Reverse the inspection rename when restoring a pre-release backup."""

from __future__ import annotations

import frappe
from frappe.model.rename_doc import rename_doc

from connect_diagnostics_core.patches.v1_0.rename_demo_return_inspection import (
    RENAMES,
    _drop_empty_synced_target,
)


def execute() -> None:
    for doctype, old_name, new_name in reversed(RENAMES):
        old_exists = frappe.db.exists(doctype, old_name)
        new_exists = frappe.db.exists(doctype, new_name)
        if doctype == "Print Format":
            if old_exists and new_exists:
                frappe.delete_doc(doctype, old_name, force=True, ignore_permissions=True)
                old_exists = False
        elif old_exists and new_exists:
            _drop_empty_synced_target(old_name)
            old_exists = False
        if new_exists and not old_exists:
            rename_doc(doctype, new_name, old_name, force=True, ignore_permissions=True)
