# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

ASSET_ROUTES = frozenset({"Existing Asset", "Stock Capitalization"})
STOCK_ROUTES = frozenset({"Stock Entry", "Purchase"})


class Dispatch(Document):
    def on_submit(self) -> None:
        if self.get("dispatch_type") == "Outbound":
            for row in sorted(
                self.get("transfers", []),
                key=lambda value: cast(str, value.get("fulfillment_allocation") or ""),
            ):
                if row.get("fulfillment_allocation"):
                    allocation = frappe.db.get_value(
                        "Material Request Fulfillment Allocation",
                        row.fulfillment_allocation,
                        ["resolved_asset", "lifecycle_state"],
                        as_dict=True,
                        for_update=True,
                    )
                    if (
                        not allocation
                        or allocation.resolved_asset != row.get("asset")
                        or allocation.lifecycle_state not in (None, "Ready")
                    ):
                        frappe.throw(_("A Demo allocation changed before Dispatch submission."))
                    frappe.db.set_value(
                        "Material Request Fulfillment Allocation",
                        row.fulfillment_allocation,
                        {"dispatch_transfer": row.name, "lifecycle_state": "Dispatched"},
                        update_modified=False,
                    )

    def validate(self) -> None:
        self._validate_header()
        self._validate_transfers()
        self._validate_post_submit_mutation()

    def before_submit(self) -> None:
        if self.get("delivery_status") != "Draft":
            frappe.throw(_("Only a Draft delivery can be dispatched."))
        self._lock_and_revalidate_return_quantities()
        self._validate_asset_availability()
        if isinstance(self, Document) and self.get("dispatch_type") == "Outbound":
            self._validate_outbound_completeness()
        self.set("delivery_status", "Dispatched")
        if not self.get("dispatched_at"):
            self.set("dispatched_at", now_datetime())
        self._set_outward_stock_entry()
        self._set_asset_movement()

    def before_cancel(self) -> None:
        frappe.throw(
            _("A submitted Dispatch cannot be cancelled. Use Return, Retry, or Return to Origin instead.")
        )

    def on_cancel(self) -> None:
        self.db_set("delivery_status", "Cancelled", update_modified=False)

    def _set_outward_stock_entry(self) -> None:
        entries = {
            row.get("reference_name")
            for row in self.get("transfers", [])
            if row.get("reference_doctype") == "Stock Entry" and row.get("reference_name")
        }
        if len(entries) > 1:
            frappe.throw(_("One Dispatch must use one Stock Entry movement cycle."))
        if entries and not self.get("outward_stock_entry"):
            self.set("outward_stock_entry", next(iter(entries)))

    def _set_asset_movement(self) -> None:
        """Require one submitted Asset Movement and mirror it into the child rows."""
        asset_rows = [row for row in self.get("transfers", []) if row.get("asset")]
        if not asset_rows:
            return
        if any(not row.get("reference_name") for row in asset_rows):
            frappe.throw(_("Every Asset Dispatch row must reference a submitted Asset Movement."))
        if any(not row.get("original_source_location") for row in asset_rows):
            frappe.throw(_("Every Asset Dispatch row must retain its original source Location."))
        movements = {row.get("reference_name") for row in asset_rows if row.get("reference_name")}
        if not movements:
            frappe.throw(_("Asset Dispatch rows must reference a submitted Asset Movement."))
        if len(movements) != 1:
            frappe.throw(_("One Dispatch must use one Asset Movement for all Asset rows."))
        movement = next(iter(movements))
        self.set("asset_movement", movement)
        for row in asset_rows:
            row.set("asset_movement", movement)

    def _validate_outbound_completeness(self) -> None:
        """Require one complete outbound cycle for every routed MR item."""
        demo_rows = [row for row in self.get("transfers", []) if row.get("fulfillment_allocation")]
        if demo_rows:
            self._validate_demo_outbound_completeness(demo_rows)
            return
        items = frappe.get_all(
            "Material Request Item",
            filters={"parent": self.get("material_request")},
            fields=["name", "stock_qty", "stock_uom", "fulfillment_route", "allocated_asset"],
        )
        transfers_by_item: dict[str, list[Document]] = defaultdict(list)
        for transfer in self.get("transfers", []):
            transfers_by_item[transfer.get("material_request_item")].append(transfer)

        for item in items:
            route = item.fulfillment_route
            transfers = transfers_by_item.get(item.name, [])
            if route in STOCK_ROUTES:
                if (
                    len(transfers) != 1
                    or abs(sum(flt(row.get("qty")) for row in transfers) - flt(item.stock_qty)) > 0.00001
                ):
                    frappe.throw(
                        _(
                            "Outbound Dispatch must contain the full Stock quantity for Material Request row {0}."
                        ).format(item.name)
                    )
                if transfers[0].get("uom") != item.stock_uom:
                    frappe.throw(
                        _(
                            "Outbound Dispatch stock quantity must be entered in the Stock UOM for row {0}."
                        ).format(item.name)
                    )
            elif route in ASSET_ROUTES:
                if (
                    len(transfers) != 1
                    or transfers[0].get("asset") != item.allocated_asset
                    or flt(transfers[0].get("qty")) != 1
                ):
                    frappe.throw(
                        _(
                            "Outbound Dispatch must contain the allocated Asset exactly once for Material Request row {0}."
                        ).format(item.name)
                    )

    def _validate_demo_outbound_completeness(self, transfers: list[Document]) -> None:
        if len(transfers) != len(self.get("transfers", [])):
            frappe.throw(_("A Demo Dispatch cannot mix allocation and legacy transfer rows."))
        allocation_names = [cast(str, row.get("fulfillment_allocation")) for row in transfers]
        if len(allocation_names) != len(set(allocation_names)):
            frappe.throw(_("Each Demo allocation must appear exactly once in the Dispatch."))
        parents = {
            frappe.db.get_value("Material Request Fulfillment Allocation", name, "parent")
            for name in allocation_names
        }
        if len(parents) != 1 or None in parents:
            frappe.throw(_("All Demo Dispatch allocations must belong to one Fulfillment."))
        fulfillment = cast(str, next(iter(parents)))
        plan = frappe.db.get_value(
            "Material Request Fulfillment",
            fulfillment,
            ["material_request", "status"],
            as_dict=True,
        )
        if not plan or plan.material_request != self.get("material_request") or plan.status != "Planned":
            frappe.throw(_("The Demo Dispatch must use the active Fulfillment."))
        current = frappe.db.get_value(
            "Material Request Fulfillment",
            {"material_request": self.get("material_request"), "status": "Planned"},
            "name",
            order_by="plan_revision desc",
        )
        expected = set(
            frappe.get_all(
                "Material Request Fulfillment Allocation",
                filters={"parent": fulfillment},
                pluck="name",
            )
        )
        if current != fulfillment or set(allocation_names) != expected:
            frappe.throw(_("The Demo Dispatch must contain every latest allocation exactly once."))

    def _validate_header(self) -> None:
        if not self.get("transfers"):
            frappe.throw(_("Add at least one Dispatch Transfer."))
        mr = frappe.db.get_value(
            "Material Request",
            self.get("material_request"),
            ["company", "docstatus", "request_usage"],
            as_dict=True,
        )
        if not mr or mr.docstatus != 1:
            frappe.throw(_("Material Request must be submitted before creating a Dispatch."))
        if mr.company != self.get("company"):
            frappe.throw(_("Dispatch and Material Request must belong to the same company."))
        if mr.request_usage not in {"Employee Borrow", "Customer Demo", "Customer Loan"}:
            frappe.throw(_("Dispatch is available only for returnable Material Requests."))

        dispatch_type = self.get("dispatch_type")
        if dispatch_type == "Outbound":
            if self.get("original_dispatch"):
                frappe.throw(_("Outbound Dispatch must not reference an Original Dispatch."))
            duplicate = frappe.db.exists(
                "Dispatch",
                {
                    "name": ("!=", self.name or ""),
                    "material_request": self.get("material_request"),
                    "dispatch_type": "Outbound",
                    "docstatus": 1,
                },
            )
            if duplicate:
                frappe.throw(_("This Material Request already has a submitted Outbound Dispatch."))
            return
        if dispatch_type not in {"Return", "Retry"}:
            frappe.throw(_("Dispatch Type must be Outbound, Return, or Retry."))

        original = frappe.db.get_value(
            "Dispatch",
            self.get("original_dispatch"),
            ["company", "material_request", "dispatch_type", "docstatus", "delivery_status"],
            as_dict=True,
        )
        if not original or original.docstatus != 1 or original.dispatch_type != "Outbound":
            frappe.throw(_("Original Dispatch must be a submitted Outbound Dispatch."))
        if original.company != self.get("company") or original.material_request != self.get(
            "material_request"
        ):
            frappe.throw(_("Original Dispatch must use the same company and Material Request."))
        if dispatch_type == "Return" and original.delivery_status != "Delivered":
            frappe.throw(_("Return Dispatch can be created only after the Outbound Dispatch is delivered."))
        if dispatch_type == "Retry":
            self._validate_retry_header(original)

    def _validate_post_submit_mutation(self) -> None:
        if self.docstatus != 1:
            return
        before = self.get_doc_before_save()
        if not before:
            return
        controlled = (
            "delivery_status",
            "received_at",
            "receiver_name",
            "receiver_contact",
            "receiver_signature",
            "delivery_note",
            "delivery_confirmation_method",
            "delivery_confirmed_by",
            "delivery_confirmed_at",
            "delivery_override_reason",
            "delivery_override_attachment",
        )
        if not any(self.get(fieldname) != before.get(fieldname) for fieldname in controlled):
            protected_child_fields = (
                "outward_stock_entry_detail",
                "end_transit_stock_entry_detail",
                "asset_movement",
            )
            before_rows = {row.name: row for row in before.get("transfers", [])}
            child_changed = any(
                row.get(fieldname) != before_rows.get(row.name, {}).get(fieldname)
                for row in self.get("transfers", [])
                for fieldname in protected_child_fields
            )
            if not child_changed:
                return

        action = self.flags.get("dispatch_action")
        if action not in {"delivery", "failure", "return_origin"} and self.docstatus == 1:
            frappe.throw(_("Use the controlled Dispatch action to update movement audit links."))
        if action == "delivery":
            if before.get("delivery_status") != "Dispatched" or self.get("delivery_status") != "Delivered":
                frappe.throw(_("Invalid delivery confirmation transition."))
            if not self.get("receiver_name") or not self.get("receiver_signature"):
                if self.get("delivery_confirmation_method") != "Warehouse Override":
                    frappe.throw(_("Receiver Name and Receiver Signature are required."))
            if self.get("delivery_confirmation_method") == "Warehouse Override" and not self.get(
                "delivery_override_reason"
            ):
                frappe.throw(_("Delivery Override Reason is required."))
            if self.get("received_at") < self.get("dispatched_at"):
                frappe.throw(_("Received At cannot be before Dispatched At."))
            return
        if action == "return_origin":
            if (
                before.get("delivery_status") not in {"Failed", "Dispatched"}
                or self.get("delivery_status") != "Returned to Origin"
            ):
                frappe.throw(_("Invalid Return to Origin transition."))
            if not self.get("delivery_note"):
                frappe.throw(_("Return to Origin reason is required."))
            return
        if action == "failure":
            if before.get("delivery_status") != "Dispatched" or self.get("delivery_status") != "Failed":
                frappe.throw(_("Invalid dispatch failure transition."))
            if not self.get("delivery_note"):
                frappe.throw(_("Failure Note is required."))
            return
        frappe.throw(_("Use Confirm Delivery or Report Failure to update a submitted Dispatch."))

    def _validate_retry_header(self, original: Any) -> None:
        if original.delivery_status != "Failed":
            frappe.throw(_("Retry is allowed only after the Outbound Dispatch has failed."))
        active_retry = frappe.db.exists(
            "Dispatch",
            {
                "name": ("!=", self.name or ""),
                "dispatch_type": "Retry",
                "original_dispatch": self.get("original_dispatch"),
                "docstatus": 1,
                "delivery_status": ("in", ("Dispatched", "Delivered")),
            },
        )
        if active_retry:
            frappe.throw(_("This Outbound Dispatch already has an active or delivered Retry."))

    def _validate_transfers(self) -> None:
        seen: set[tuple[str, str, str, str]] = set()
        asset_rows: set[str] = set()
        for row in self.get("transfers"):
            if flt(row.get("qty")) <= 0:
                frappe.throw(_("Row #{0}: Quantity must be greater than zero.").format(row.idx))
            key = (
                cast(str, row.get("material_request_item")),
                cast(str, row.get("reference_doctype")),
                cast(str, row.get("reference_name")),
                cast(str, row.get("asset") or ""),
            )
            if key in seen:
                frappe.throw(_("Row #{0}: Duplicate Dispatch Transfer.").format(row.idx))
            seen.add(key)
            if row.get("asset"):
                if row.get("asset") in asset_rows:
                    frappe.throw(_("Row #{0}: An Asset can appear only once per Dispatch.").format(row.idx))
                asset_rows.add(cast(str, row.get("asset")))
            self._validate_transfer(row)

    def _validate_transfer(self, row: Document) -> None:
        mr_item = frappe.db.get_value(
            "Material Request Item",
            row.get("material_request_item"),
            ["parent", "item_code", "fulfillment_route", "allocated_asset", "stock_uom"],
            as_dict=True,
        )
        if not mr_item or mr_item.parent != self.get("material_request"):
            frappe.throw(
                _("Row #{0}: Material Request Item does not belong to this request.").format(row.idx)
            )
        if mr_item.item_code != row.get("item_code"):
            frappe.throw(_("Row #{0}: Item Code does not match the Material Request Item.").format(row.idx))
        if not row.get("uom"):
            row.set("uom", mr_item.stock_uom)

        if row.get("fulfillment_allocation"):
            self._validate_demo_asset_transfer(row, mr_item)
        elif mr_item.fulfillment_route in ASSET_ROUTES:
            self._validate_asset_transfer(row, mr_item)
        elif mr_item.fulfillment_route in STOCK_ROUTES:
            self._validate_stock_transfer(row)
        else:
            frappe.throw(_("Row #{0}: Select a supported Fulfillment Route first.").format(row.idx))

        if self.get("dispatch_type") in {"Return", "Retry"}:
            self._validate_against_outbound(row)

    def _validate_demo_asset_transfer(self, row: Document, mr_item: Any) -> None:
        allocation = frappe.db.get_value(
            "Material Request Fulfillment Allocation",
            row.get("fulfillment_allocation"),
            [
                "parent",
                "material_request_item",
                "item_code",
                "qty",
                "resolved_asset",
                "lifecycle_state",
                "asset_movement",
            ],
            as_dict=True,
        )
        if (
            not allocation
            or allocation.material_request_item != row.get("material_request_item")
            or allocation.item_code != row.get("item_code")
            or allocation.resolved_asset != row.get("asset")
            or float(allocation.qty) != 1
            or flt(row.get("qty")) != 1
        ):
            frappe.throw(_("Row #{0}: Transfer does not match its Demo allocation.").format(row.idx))
        plan = frappe.db.get_value(
            "Material Request Fulfillment",
            allocation.parent,
            ["material_request", "company", "status"],
            as_dict=True,
        )
        if (
            not plan
            or plan.material_request != self.get("material_request")
            or plan.company != self.get("company")
            or plan.status != "Planned"
            or mr_item.parent != plan.material_request
        ):
            frappe.throw(_("Row #{0}: Demo allocation is not active for this request.").format(row.idx))
        expected_state = "Delivered" if self.get("dispatch_type") == "Return" else "Ready"
        if self.get("dispatch_type") == "Outbound" and allocation.lifecycle_state not in (
            None,
            expected_state,
        ):
            frappe.throw(_("Row #{0}: Demo allocation is not ready for outbound.").format(row.idx))
        if self.get("dispatch_type") == "Return" and allocation.lifecycle_state != expected_state:
            frappe.throw(_("Row #{0}: Demo allocation is not ready for return.").format(row.idx))
        self._validate_demo_asset_movement(row, allocation)

    def _validate_demo_asset_movement(self, row: Document, allocation: Any) -> None:
        if row.get("reference_doctype") != "Asset Movement" or not row.get("reference_name"):
            frappe.throw(_("Row #{0}: Demo Asset must reference an Asset Movement.").format(row.idx))
        movement = frappe.db.get_value(
            "Asset Movement",
            row.get("reference_name"),
            ["company", "material_request", "docstatus", "purpose", "reference_doctype", "reference_name"],
            as_dict=True,
        )
        is_return = self.get("dispatch_type") == "Return"
        expected_purpose = "Receipt" if is_return else "Issue"
        expected_reference_doctype = "Dispatch" if is_return else "Material Request Fulfillment"
        expected_reference_name = self.get("original_dispatch") if is_return else allocation.parent
        if (
            not movement
            or movement.docstatus != 1
            or movement.company != self.get("company")
            or movement.material_request != self.get("material_request")
            or movement.purpose != expected_purpose
            or movement.reference_doctype != expected_reference_doctype
            or movement.reference_name != expected_reference_name
        ):
            frappe.throw(_("Row #{0}: Demo Asset Movement does not match this journey.").format(row.idx))
        movement_item = frappe.db.get_value(
            "Asset Movement Item",
            {"parent": row.get("reference_name"), "asset": row.get("asset")},
            ["source_location", "target_location", "to_employee"],
            as_dict=True,
        )
        if not movement_item:
            frappe.throw(_("Row #{0}: Asset is missing from the movement.").format(row.idx))
        if is_return:
            qa_location = frappe.db.get_value("Company", self.get("company"), "return_qa_hold_location")
            if movement_item.target_location != qa_location:
                frappe.throw(_("Row #{0}: Return must receive into QA Hold.").format(row.idx))
        else:
            employee = frappe.db.get_value(
                "Material Request", self.get("material_request"), "responsible_employee"
            )
            if movement_item.to_employee != employee:
                frappe.throw(_("Row #{0}: Outbound must issue to the responsible Employee.").format(row.idx))

    def _validate_stock_transfer(self, row: Document) -> None:
        if row.get("reference_doctype") != "Stock Entry" or row.get("asset"):
            frappe.throw(_("Row #{0}: Stock fulfillment must reference a Stock Entry.").format(row.idx))
        if self.get("dispatch_type") == "Return" and not row.get("reference_name"):
            return
        entry = frappe.db.get_value(
            "Stock Entry",
            row.get("reference_name"),
            ["company", "docstatus"],
            as_dict=True,
        )
        if not entry or entry.docstatus != 1 or entry.company != self.get("company"):
            frappe.throw(_("Row #{0}: Stock Entry must be submitted for this company.").format(row.idx))
        is_return_dispatch = self.get("dispatch_type") == "Return"
        movement_qty = frappe.db.sql(
            """
            SELECT COALESCE(SUM(ABS(transfer_qty)), 0)
            FROM `tabStock Entry Detail`
            WHERE parent = %s AND item_code = %s
                AND material_request_item = %s
                AND COALESCE(s_warehouse, '') != ''
            """,
            (row.get("reference_name"), row.get("item_code"), row.get("material_request_item")),
        )[0][0]
        if not movement_qty:
            direction = _("out of the Borrow Warehouse") if is_return_dispatch else _("out of a warehouse")
            frappe.throw(_("Row #{0}: Stock Entry must move this item {1}.").format(row.idx, direction))
        if flt(row.get("qty")) > flt(movement_qty):
            frappe.throw(
                _("Row #{0}: Dispatch quantity exceeds the referenced Stock Entry quantity.").format(row.idx)
            )
        details = frappe.get_all(
            "Stock Entry Detail",
            filters={
                "parent": row.get("reference_name"),
                "material_request_item": row.get("material_request_item"),
                "item_code": row.get("item_code"),
                "s_warehouse": ("is", "set"),
            },
            fields=["name", "s_warehouse", "t_warehouse"],
        )
        if len(details) != 1:
            frappe.throw(_("Row {0}: Dispatch must link exactly one Stock Entry Detail row.").format(row.idx))
        row.set("outward_stock_entry_detail", details[0].name)
        if is_return_dispatch:
            entry = frappe.db.get_value(
                "Stock Entry",
                row.get("reference_name"),
                ["add_to_transit", "to_warehouse"],
                as_dict=True,
            )
            transit = frappe.db.get_value("Company", self.get("company"), "borrow_in_transit_warehouse")
            if not entry or not entry.add_to_transit or entry.to_warehouse != transit:
                frappe.throw(
                    _("Row {0}: Return Outward must use the Company's Borrow In Transit Warehouse.").format(
                        row.idx
                    )
                )
        elif self.get("dispatch_type") in {"Outbound", "Retry"}:
            entry = frappe.db.get_value(
                "Stock Entry",
                row.get("reference_name"),
                ["add_to_transit", "to_warehouse"],
                as_dict=True,
            )
            transit = frappe.db.get_value("Company", self.get("company"), "borrow_in_transit_warehouse")
            if not entry or not entry.add_to_transit or entry.to_warehouse != transit:
                frappe.throw(
                    _("Row {0}: Outbound stock must use the Company's Borrow In Transit Warehouse.").format(
                        row.idx
                    )
                )

    def _validate_asset_transfer(self, row: Document, mr_item: Any) -> None:
        is_return_dispatch = self.get("dispatch_type") == "Return"
        if row.get("reference_doctype") != "Asset Movement" or not row.get("asset"):
            frappe.throw(_("Row #{0}: Asset fulfillment must reference an Asset Movement.").format(row.idx))
        if row.get("asset") != mr_item.allocated_asset:
            frappe.throw(_("Row #{0}: Asset must match the Allocated Asset.").format(row.idx))
        if flt(row.get("qty")) != 1:
            frappe.throw(_("Row #{0}: Asset quantity must be exactly one.").format(row.idx))
        if is_return_dispatch and not row.get("reference_name"):
            return
        movement = frappe.db.get_value(
            "Asset Movement",
            row.get("reference_name"),
            ["company", "material_request", "docstatus", "purpose"],
            as_dict=True,
        )
        if (
            not movement
            or movement.docstatus != 1
            or movement.company != self.get("company")
            or movement.material_request != self.get("material_request")
        ):
            frappe.throw(
                _("Row #{0}: Asset Movement must be submitted and linked to this request.").format(row.idx)
            )
        movement_item = frappe.db.get_value(
            "Asset Movement Item",
            {"parent": row.get("reference_name"), "asset": row.get("asset")},
            ["name", "source_location", "target_location", "from_employee", "to_employee"],
            as_dict=True,
        )
        if not movement_item:
            frappe.throw(_("Row #{0}: Asset is not present in the Asset Movement.").format(row.idx))
        if is_return_dispatch:
            qa_location = frappe.db.get_value("Company", self.get("company"), "return_qa_hold_location")
            if movement.purpose != "Receipt" or movement_item.target_location != qa_location:
                frappe.throw(
                    _(
                        "Row #{0}: Return must use a submitted Receipt Asset Movement into the QA Hold Location."
                    ).format(row.idx)
                )
        else:
            employee = frappe.db.get_value(
                "Material Request", self.get("material_request"), "responsible_employee"
            )
            if movement.purpose != "Issue" or movement_item.to_employee != employee:
                frappe.throw(
                    _(
                        "Row #{0}: Outbound Asset Movement must be a submitted Issue to the Responsible Employee."
                    ).format(row.idx)
                )
            source_location = frappe.db.get_value("Asset", row.get("asset"), "location")
            if source_location and not row.get("original_source_location"):
                row.set("original_source_location", source_location)

    def _validate_against_outbound(self, row: Document) -> None:
        original = frappe.db.get_value(
            "Dispatch Transfer",
            row.get("against_dispatch_transfer"),
            [
                "parent",
                "material_request_item",
                "item_code",
                "asset",
                "qty",
                "uom",
                "reference_doctype",
                "reference_name",
                "fulfillment_allocation",
                "original_source_location",
            ],
            as_dict=True,
        )
        if not original or original.parent != self.get("original_dispatch"):
            frappe.throw(_("Row #{0}: Select a transfer from the Original Dispatch.").format(row.idx))
        for fieldname in ("material_request_item", "item_code", "asset", "fulfillment_allocation"):
            if (row.get(fieldname) or "") != (original.get(fieldname) or ""):
                frappe.throw(_("Row #{0}: Returned or retried item must match the original.").format(row.idx))

        if self.get("dispatch_type") == "Retry":
            if (
                row.get("reference_doctype") != original.reference_doctype
                or row.get("reference_name") != original.reference_name
                or flt(row.get("qty")) != flt(original.qty)
            ):
                frappe.throw(
                    _("Row #{0}: Retry must reuse the original movement and quantity.").format(row.idx)
                )
            if row.get("asset"):
                source_location = original.get("original_source_location")
                if not source_location:
                    frappe.throw(
                        _("Row {0}: The original outbound Asset source Location is missing.").format(row.idx)
                    )
                row.set("original_source_location", source_location)
            return

        if (
            row.get("reference_doctype") == "Stock Entry"
            and row.get("reference_name")
            and self.get("dispatch_type") == "Return"
        ):
            self._validate_return_stock_movement(row)

        if self.get("dispatch_type") == "Return":
            self._set_return_source_and_destination(row, original)

        already_returned = frappe.db.sql(
            """
            SELECT COALESCE(SUM(dt.qty), 0)
            FROM `tabDispatch Transfer` dt
            INNER JOIN `tabDispatch` d ON d.name = dt.parent
            WHERE dt.against_dispatch_transfer = %s
                AND d.dispatch_type = 'Return'
                AND d.docstatus = 1
                AND d.delivery_status IN ('Dispatched', 'Failed', 'Delivered')
                AND d.name != %s
            """,
            (row.get("against_dispatch_transfer"), self.name or ""),
        )[0][0]
        if flt(already_returned) + flt(row.get("qty")) > flt(original.qty):
            frappe.throw(_("Row #{0}: Return quantity exceeds the unreturned quantity.").format(row.idx))

    def _validate_return_stock_movement(self, row: Document) -> None:
        entry = frappe.db.get_value(
            "Stock Entry", row.get("reference_name"), ["add_to_transit", "to_warehouse"], as_dict=True
        )
        transit = frappe.db.get_value("Company", self.get("company"), "borrow_in_transit_warehouse")
        if not entry or not entry.add_to_transit or entry.to_warehouse != transit:
            frappe.throw(
                _("Row {0}: Return must first move stock from Borrow Warehouse into Transit.").format(row.idx)
            )
        employee = frappe.db.get_value(
            "Material Request", self.get("material_request"), "responsible_employee"
        )
        borrow_warehouse = frappe.db.get_value("Employee", employee, "borrow_warehouse") if employee else None
        source = frappe.db.get_value(
            "Stock Entry Detail",
            {"parent": row.get("reference_name"), "material_request_item": row.get("material_request_item")},
            "s_warehouse",
        )
        if source != borrow_warehouse:
            frappe.throw(
                _("Row {0}: Return stock must come from the responsible Employee Borrow Warehouse.").format(
                    row.idx
                )
            )

    def _set_return_source_and_destination(self, row: Document, original: Any) -> None:
        if row.get("reference_doctype") == "Stock Entry":
            source = frappe.db.get_value(
                "Stock Entry Detail",
                {"parent": original.reference_name, "material_request_item": original.material_request_item},
                "s_warehouse",
            )
            if source:
                row.set("original_source_warehouse", source)
        elif row.get("asset"):
            source_location = original.get("original_source_location")
            if source_location:
                row.set("original_source_location", source_location)
                if not row.get("planned_final_location"):
                    row.set("planned_final_location", source_location)
            else:
                frappe.throw(
                    _("Row {0}: The original outbound Asset source Location is missing.").format(row.idx)
                )
        if not row.get("planned_final_warehouse"):
            row.set("planned_final_warehouse", row.get("original_source_warehouse"))
        if row.get("planned_final_warehouse"):
            details = frappe.db.get_value(
                "Warehouse",
                row.get("planned_final_warehouse"),
                ["company", "is_group", "disabled"],
                as_dict=True,
            )
            if not details or details.company != self.get("company") or details.is_group or details.disabled:
                frappe.throw(
                    _("Row {0}: Planned final Warehouse must be an active leaf in this Company.").format(
                        row.idx
                    )
                )
        if row.get("planned_final_location"):
            if frappe.db.get_value("Location", row.get("planned_final_location"), "is_group"):
                frappe.throw(_("Row {0}: Planned final Location must be a leaf Location.").format(row.idx))

    def _validate_reversed_stock_movement(self, row: Document, original: Any) -> None:
        if row.get("reference_name") == original.reference_name:
            frappe.throw(_("Row #{0}: Return must use a separate Stock Entry.").format(row.idx))

        original_rows = frappe.get_all(
            "Stock Entry Detail",
            filters={
                "parent": original.reference_name,
                "item_code": row.get("item_code"),
                "material_request_item": row.get("material_request_item"),
            },
            fields=["s_warehouse", "t_warehouse"],
        )
        return_rows = frappe.get_all(
            "Stock Entry Detail",
            filters={"parent": row.get("reference_name"), "item_code": row.get("item_code")},
            fields=["s_warehouse", "t_warehouse"],
        )
        original_sources = {item.s_warehouse for item in original_rows if item.s_warehouse}
        return_targets = {item.t_warehouse for item in return_rows if item.t_warehouse}
        if not original_sources or not return_targets or not return_targets.issubset(original_sources):
            frappe.throw(
                _("Row #{0}: Return Stock Entry must receive into the original source Warehouse.").format(
                    row.idx
                )
            )

        original_targets = {item.t_warehouse for item in original_rows if item.t_warehouse}
        return_sources = {item.s_warehouse for item in return_rows if item.s_warehouse}
        if original_targets and (not return_sources or not return_sources.issubset(original_targets)):
            frappe.throw(
                _("Row #{0}: Return Stock Entry must reverse the original Warehouse movement.").format(
                    row.idx
                )
            )

    def _validate_asset_availability(self) -> None:
        if self.get("dispatch_type") != "Outbound":
            return
        for row in self.get("transfers"):
            asset = row.get("asset")
            if not asset:
                continue
            frappe.db.get_value("Asset", asset, "name", for_update=True)
            outstanding = frappe.db.sql(
                """
                SELECT out_row.qty - COALESCE(
                    SUM(CASE WHEN ret_doc.name IS NOT NULL THEN ret_row.qty ELSE 0 END), 0
                ) AS outstanding_qty
                FROM `tabDispatch Transfer` out_row
                INNER JOIN `tabDispatch` out_doc ON out_doc.name = out_row.parent
                LEFT JOIN `tabDispatch Transfer` ret_row
                    ON ret_row.against_dispatch_transfer = out_row.name
                LEFT JOIN `tabDispatch` ret_doc
                    ON ret_doc.name = ret_row.parent
                    AND ret_doc.dispatch_type = 'Return'
                    AND ret_doc.docstatus = 1
                    AND ret_doc.delivery_status = 'Delivered'
                WHERE out_row.asset = %s
                    AND out_doc.dispatch_type = 'Outbound'
                    AND out_doc.docstatus = 1
                    AND out_doc.name != %s
                GROUP BY out_row.name, out_row.qty
                HAVING outstanding_qty > 0
                LIMIT 1
                """,
                (asset, self.name or ""),
                as_dict=True,
            )
            if outstanding:
                frappe.throw(_("Asset {0} is already in an outstanding Outbound Dispatch.").format(asset))

    def _lock_and_revalidate_return_quantities(self) -> None:
        if self.get("dispatch_type") not in {"Return", "Retry"}:
            return
        if self.get("dispatch_type") == "Retry":
            original = frappe.db.get_value(
                "Dispatch",
                self.get("original_dispatch"),
                ["delivery_status"],
                as_dict=True,
                for_update=True,
            )
            if not original:
                frappe.throw(_("Original Dispatch does not exist."))
            self._validate_retry_header(original)
        for row in self.get("transfers"):
            frappe.db.get_value(
                "Dispatch Transfer", row.get("against_dispatch_transfer"), "name", for_update=True
            )
            self._validate_against_outbound(row)
