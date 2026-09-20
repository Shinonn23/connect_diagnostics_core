# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Allow users to edit app-owned Print Formats through Desk."""

from __future__ import annotations

from typing import cast

import frappe

APP_MODULE = "Connect Diagnostics Core"


def execute() -> None:
    """Convert existing app-owned standard formats to editable records."""
    names = cast(
        list[str],
        frappe.get_all(
            "Print Format",
            filters={"module": APP_MODULE, "standard": "Yes"},
            pluck="name",
        ),
    )

    for name in names:
        frappe.db.set_value(
            "Print Format",
            name,
            "standard",
            "No",
            update_modified=False,
        )

    frappe.logger(__name__).info(
        "make_app_print_formats_editable: updated %s Print Formats",
        len(names),
    )
