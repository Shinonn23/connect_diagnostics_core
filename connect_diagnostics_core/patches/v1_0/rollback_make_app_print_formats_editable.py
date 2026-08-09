# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for make_app_print_formats_editable — mark app formats standard again.

The forward patch flipped every ``Connect Diagnostics Core`` Print Format from
``standard = "Yes"`` to ``"No"`` so users could edit them through Desk. This reverses
that flip for the same module. It cannot distinguish formats that were user-created as
editable from ones the patch converted, so it applies to every app-owned format in the
module — acceptable because app-owned formats are code-managed.
"""

from __future__ import annotations

from typing import cast

import frappe

APP_MODULE = "Connect Diagnostics Core"


def execute() -> None:
    names = cast(
        list[str],
        frappe.get_all(
            "Print Format",
            filters={"module": APP_MODULE, "standard": "No"},
            pluck="name",
        ),
    )

    for name in names:
        frappe.db.set_value(
            "Print Format",
            name,
            "standard",
            "Yes",
            update_modified=False,
        )

    frappe.logger(__name__).info(
        "rollback_make_app_print_formats_editable: reverted %s Print Formats",
        len(names),
    )
