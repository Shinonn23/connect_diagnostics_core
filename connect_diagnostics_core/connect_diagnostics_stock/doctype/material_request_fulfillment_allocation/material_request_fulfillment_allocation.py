# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.model.document import Document


class MaterialRequestFulfillmentAllocation(Document):
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        asset_reservation: DF.Link | None
        downstream_doctype: DF.Link | None
        downstream_reference: DF.DynamicLink | None
        equipment_model: DF.Link
        fixed_asset_item: DF.Link
        item_code: DF.Link
        item_name: DF.Data | None
        material_request_item: DF.Link
        qty: DF.Float
        selected_source: DF.Data | None
        source_type: DF.Literal["Unplanned", "Existing Asset", "Returning Asset", "Stock Conversion"]
        uom: DF.Link | None
        expected_available_on: DF.Date | None
        conversion_source_bundle: DF.Link | None
        conversion_state: DF.Literal["Draft", "Ready", "Cancelled"] | None
        conversion_source_warehouse: DF.Link | None
        resolved_asset: DF.Link | None
        asset_movement: DF.Link | None
        dispatch_transfer: DF.Link | None
        lifecycle_state: DF.Literal["Ready", "Dispatched", "Delivered", "Returned", "Sold"] | None
        current_sales_invoice: DF.Link | None
        sale_attempt: DF.Int | None
