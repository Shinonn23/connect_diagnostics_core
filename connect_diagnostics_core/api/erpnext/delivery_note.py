# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe

from connect_diagnostics_core.api.erpnext.stock_traceability import get_item_traceability


@frappe.whitelist()
def get_serial_no_summary(delivery_note: str) -> list[dict]:
    """Per-item serial numbers of a Delivery Note, for quick verification.

    Read live from the DB so the summary shows for every document (including ones
    already saved/submitted) without re-saving. Only serial-tracked items are
    returned — batch-only / plain items would be noise. Serial numbers live either
    on the row's ``serial_no`` text (when ``use_serial_batch_fields`` is set) or
    inside the linked Serial and Batch Bundle; both paths are resolved here.
    """
    frappe.has_permission("Delivery Note", doc=delivery_note, throw=True)

    rows = frappe.db.get_all(
        "Delivery Note Item",
        filters={"parent": delivery_note},
        fields=["item_code", "item_name", "qty", "serial_no", "serial_and_batch_bundle"],
        order_by="idx asc",
    )

    summary = []
    for row in rows:
        serial_nos = get_item_traceability(row)["serial_nos"]

        has_serial_no = frappe.get_cached_value("Item", row.item_code, "has_serial_no")
        if not has_serial_no and not serial_nos:
            continue

        summary.append(
            {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "qty": row.qty,
                "serial_nos": serial_nos,
            }
        )

    return summary
