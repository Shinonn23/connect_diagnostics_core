# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

from frappe import _

from connect_diagnostics_core.connect_diagnostics_dksh import reference


def get_item_dashboard_data(data: dict[str, Any]) -> dict[str, Any]:
    """Surface the linked DKSH Item under the Item form's Connections."""
    return reference.inject_connection(
        data,
        reference_doctype="DKSH Item",
        link_field="item",
        group_label=_("Reference"),
    )
