# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Reverse ``move_dksh_item_to_dksh_module``: repoint DKSH Item back to Core.

Only the ``DocType.module`` value is restored. The DocType folder itself is a code
concern reverted by git, so — like ``rollback_rebuild_print_configuration`` — this
patch does not ``reload_doc`` from a folder that the code rollback has moved.

Idempotent: repointing the module is a no-op once the record sits in Core again.
"""

from __future__ import annotations

import frappe

from connect_diagnostics_core.patches.v1_0.move_dksh_item_to_dksh_module import _refresh_module_map

CORE_MODULE = "Connect Diagnostics Core"


def execute() -> None:
    """Point the DKSH Item DocType record back at the core module."""
    _refresh_module_map()
    if frappe.db.exists("DocType", "DKSH Item"):
        frappe.db.set_value("DocType", "DKSH Item", "module", CORE_MODULE)
    frappe.clear_cache()
