# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Print Format cleanup for the Connect Diagnostics site."""

from __future__ import annotations

from typing import Any

import frappe

PRINT_FORMAT_MODULE = "Connect Diagnostics Print"


def remove_non_app_print_formats() -> None:
    """Remove every Print Format outside the dedicated print module."""
    print_formats: list[dict[str, Any]] = frappe.get_all(
        "Print Format",
        fields=["name", "module"],
    )
    removed_count = 0

    for print_format in print_formats:
        if print_format.get("module") == PRINT_FORMAT_MODULE:
            continue

        frappe.delete_doc(
            "Print Format",
            print_format["name"],
            force=True,
            ignore_missing=True,
        )
        removed_count += 1

    if removed_count:
        frappe.logger(__name__).info(
            "Removed %s obsolete Print Format records during site synchronization",
            removed_count,
        )
