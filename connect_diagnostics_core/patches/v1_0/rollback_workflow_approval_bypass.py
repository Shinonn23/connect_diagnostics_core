# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe


def execute() -> None:
    """Clear caches after rolling back the code that bypasses inactive workflows."""
    frappe.clear_cache()
