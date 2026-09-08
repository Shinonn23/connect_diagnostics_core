# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.erpnext.material_request import RETURNABLE_USAGES


class BorrowedAssetReturnInspection(Document):
    def before_validate(self) -> None:
        if not self.get("inspected_by"):
            employee = frappe.db.get_value(
                "Employee", {"user_id": frappe.session.user, "status": "Active"}, "name"
            )
            if employee:
                self.set("inspected_by", employee)

    def validate(self) -> None:
        self._validate_return_reference()
        self._validate_result()

    def before_submit(self) -> None:
        frappe.db.get_value(
            "Dispatch Transfer", self.get("return_dispatch_transfer"), "name", for_update=True
        )
        if self.get("inspection_result") != "Accepted":
            return
        duplicate = frappe.db.exists(
            "Borrowed Asset Return Inspection",
            {
                "name": ("!=", self.name or ""),
                "return_dispatch_transfer": self.get("return_dispatch_transfer"),
                "inspection_result": "Accepted",
                "docstatus": 1,
            },
        )
        if duplicate:
            frappe.throw(_("This Return Dispatch line already has an accepted inspection."))

    def on_submit(self) -> None:
        if self.get("inspection_result") == "Accepted":
            self._create_release_movement()
        elif self.get("return_disposition") == "Repairable":
            self._create_repair_movement()

    def _create_release_movement(self) -> None:
        if self.get("release_asset_movement"):
            return
        transfer = self._get_transfer()
        target = transfer.get("planned_final_location") or transfer.get("original_source_location")
        if not target:
            frappe.throw(_("Planned final Location is required before accepting this inspection."))
        movement = frappe.new_doc("Asset Movement")
        source_location = frappe.db.get_value("Asset", self.get("asset"), "location")
        movement.update(
            {
                "company": self.get("company"),
                "purpose": "Transfer",
                "transaction_date": self.get("inspected_at"),
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "material_request": self.get("material_request"),
            }
        )
        qa_location = frappe.db.get_value("Company", self.get("company"), "return_qa_hold_location")
        if not qa_location:
            frappe.throw(_("Return QA Hold Location is required before accepting an inspection."))
        movement.append(
            "assets",
            {
                "asset": self.get("asset"),
                "source_location": source_location or qa_location,
                "target_location": target,
            },
        )
        movement.insert()
        self.db_set("release_asset_movement", movement.name, update_modified=False)

    def _create_repair_movement(self) -> None:
        if self.get("repair_asset_movement"):
            return
        repair_location = frappe.db.get_value("Company", self.get("company"), "return_repair_location")
        if not repair_location:
            frappe.throw(_("Return Repair Location is required for a Repairable inspection."))
        movement = frappe.new_doc("Asset Movement")
        movement.update(
            {
                "company": self.get("company"),
                "purpose": "Transfer",
                "transaction_date": self.get("inspected_at"),
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "material_request": self.get("material_request"),
            }
        )
        qa_location = frappe.db.get_value("Company", self.get("company"), "return_qa_hold_location")
        if not qa_location:
            frappe.throw(_("Return QA Hold Location is required before sending an asset to Repair."))
        movement.append(
            "assets",
            {
                "asset": self.get("asset"),
                "source_location": frappe.db.get_value("Asset", self.get("asset"), "location") or qa_location,
                "target_location": repair_location,
            },
        )
        movement.insert()
        self.db_set("repair_asset_movement", movement.name, update_modified=False)

    def _get_transfer(self) -> Document:
        return frappe.get_doc("Dispatch Transfer", self.get("return_dispatch_transfer"))

    def _validate_return_reference(self) -> None:
        dispatch = frappe.db.get_value(
            "Dispatch",
            self.get("return_dispatch"),
            ["company", "material_request", "dispatch_type", "delivery_status", "docstatus"],
            as_dict=True,
        )
        if (
            not dispatch
            or dispatch.docstatus != 1
            or dispatch.dispatch_type != "Return"
            or dispatch.delivery_status != "Delivered"
        ):
            frappe.throw(_("Return Dispatch must be submitted and delivered before inspection."))
        if self.get("company") and dispatch.get("company") != self.get("company"):
            frappe.throw(_("Return Dispatch must use the same company and Material Request."))
        if self.get("material_request") and dispatch.get("material_request") != self.get("material_request"):
            frappe.throw(_("Return Dispatch must use the same company and Material Request."))
        self.set("company", dispatch.get("company"))
        self.set("material_request", dispatch.get("material_request"))
        if (
            frappe.db.get_value("Material Request", self.get("material_request"), "request_usage")
            not in RETURNABLE_USAGES
        ):
            frappe.throw(
                _("Borrowed Asset Return Inspection is available only for returnable Material Requests.")
            )

        transfer = frappe.db.get_value(
            "Dispatch Transfer",
            self.get("return_dispatch_transfer"),
            [
                "parent",
                "asset",
                "item_code",
                "reference_doctype",
                "asset_movement",
                "planned_final_location",
                "original_source_location",
            ],
            as_dict=True,
        )
        if not transfer or transfer.get("parent") != self.get("return_dispatch"):
            frappe.throw(_("Return Dispatch Transfer must belong to the selected Return Dispatch."))
        if (
            not transfer.get("asset")
            or transfer.get("reference_doctype") != "Asset Movement"
            or not transfer.get("asset_movement")
        ):
            frappe.throw(_("Borrowed Asset Return Inspection can inspect only an Asset Movement line."))
        if transfer.get("asset") != self.get("asset"):
            frappe.throw(_("Asset must match the Return Dispatch Transfer."))
        self.set("item_code", transfer.get("item_code"))

    def _validate_result(self) -> None:
        if not self.get("checks"):
            frappe.throw(_("Add at least one inspection checklist row."))
        failed = [row for row in self.get("checks") if row.get("result") == "Fail"]
        if self.get("inspection_result") == "Accepted" and failed:
            frappe.throw(_("An accepted inspection cannot contain failed checks."))
        if self.get("inspection_result") == "Rejected":
            if not failed:
                frappe.throw(_("A rejected inspection must contain at least one failed check."))
            if not self.get("damage_note"):
                frappe.throw(_("Damage Note is required for a rejected inspection."))
            if self.get("return_disposition") not in {"Repairable", "Damaged Beyond Repair"}:
                frappe.throw(_("Select a Return Disposition for a rejected inspection."))


DemoReturnInspection = BorrowedAssetReturnInspection
