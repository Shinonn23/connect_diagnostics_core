# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Remove the Item Dimension fields (``length``, ``width``, ``height``).

A single Item has one physical dimension regardless of which UOM it is currently
transacted in (Pack vs. Piece, etc.) — ERPNext's own multi-UOM support (``UOM Conversion
Detail``) carries no per-UOM dimension or weight, so there was no way for put-away or any
other stock movement to know which UOM a stored Length/Width/Height was measured in. The
feature is retired before anything consumes it; no data is migrated. Idempotent.
"""

from __future__ import annotations

import frappe

from connect_diagnostics_core.patches.v1_0.strip_custom_prefix_from_field_names import _drop_old

_FIELDS = ("length", "width", "height")


def execute() -> None:
    for field in _FIELDS:
        _drop_old("Item", field)
    frappe.db.commit()
