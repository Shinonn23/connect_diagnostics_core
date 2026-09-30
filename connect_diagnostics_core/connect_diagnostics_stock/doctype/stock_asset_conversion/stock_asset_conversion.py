# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, cast

import frappe
from erpnext.accounts.general_ledger import make_gl_entries as post_gl_entries
from erpnext.accounts.general_ledger import make_reverse_gl_entries
from erpnext.assets.doctype.asset_category.asset_category import get_asset_category_account
from erpnext.controllers.accounts_controller import validate_account_head
from erpnext.controllers.stock_controller import StockController
from erpnext.stock.utils import get_incoming_rate, validate_disabled_warehouse, validate_warehouse_company
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, flt

FULL_DEPRECIATION = "Full Depreciation — Single Entry"
NORMAL_DEPRECIATION = "Normal Depreciation"


class StockAssetConversion(StockController):
    """Convert one stock unit into one normal ERPNext Asset."""

    if TYPE_CHECKING:
        from frappe.types import DF

        from connect_diagnostics_core.connect_diagnostics_stock.doctype.stock_asset_conversion_item.stock_asset_conversion_item import (
            StockAssetConversionItem,
        )

        accounting_treatment: DF.Literal["Full Depreciation — Single Entry", "Normal Depreciation"]
        asset: DF.Link | None
        asset_category: DF.Link
        company: DF.Link
        cost_center: DF.Link | None
        depreciation_start_date: DF.Date
        expected_value_after_useful_life: DF.Currency
        finance_book: DF.Link | None
        fixed_asset_account: DF.Link | None
        frequency_of_depreciation: DF.Int
        items: DF.Table[StockAssetConversionItem]
        fulfillment_allocation: DF.Link | None
        material_request_fulfillment: DF.Link | None
        operation_id: DF.Data | None
        posting_date: DF.Date
        posting_time: DF.Time
        preview_approved_by: DF.Link | None
        preview_approved_on: DF.Datetime | None
        preview_hash: DF.Data | None
        preview_recommendation: DF.Literal["Full Depreciation — Single Entry", "Normal Depreciation"] | None
        preview_stock_value: DF.Currency
        preview_valuation_rate: DF.Currency
        target_asset_item: DF.Link
        target_location: DF.Link
        treatment_override_reason: DF.SmallText | None
        total_number_of_depreciations: DF.Int

    def before_insert(self) -> None:
        if self.fulfillment_allocation and not getattr(frappe.flags, "stock_asset_conversion_handoff", False):
            frappe.throw(_("Linked Stock Asset Conversion can only be created by the Fulfillment action."))

    def validate(self) -> None:
        self._validate_linked_identity()
        self._validate_single_source_unit()
        self._validate_items()
        self._validate_warehouse()
        self._set_and_validate_fixed_asset_account()
        self._validate_depreciation_configuration()
        self._invalidate_stale_preview()

    def on_submit(self) -> None:
        self._validate_linked_identity()
        if self.fulfillment_allocation and not self.preview_hash:
            frappe.throw(_("A fresh Accounts preview approval is required before submit."))
        self.update_stock_ledger()
        self._validate_approved_preview_against_actual()
        self.make_gl_entries()
        self._create_and_submit_asset()
        self.repost_future_sle_and_gle()
        if self.fulfillment_allocation:
            frappe.db.set_value(
                "Material Request Fulfillment Allocation",
                self.fulfillment_allocation,
                {
                    "conversion_state": "Ready",
                    "downstream_doctype": self.doctype,
                    "downstream_reference": self.name,
                    "resolved_asset": self.asset,
                    "lifecycle_state": "Ready",
                },
                update_modified=False,
            )

    def on_cancel(self) -> None:
        self._validate_linked_identity()
        self.ignore_linked_doctypes = (
            "GL Entry",
            "Stock Ledger Entry",
            "Repost Item Valuation",
            "Serial and Batch Bundle",
        )
        self._cancel_asset()
        self.update_stock_ledger()
        self.make_gl_entries()
        self.repost_future_sle_and_gle()
        if self.fulfillment_allocation:
            frappe.db.set_value(
                "Material Request Fulfillment Allocation",
                self.fulfillment_allocation,
                {
                    "conversion_state": "Cancelled",
                    "downstream_doctype": self.doctype,
                    "downstream_reference": self.name,
                    "resolved_asset": None,
                    "lifecycle_state": None,
                },
                update_modified=False,
            )

    def _validate_linked_identity(self) -> None:
        if not self.fulfillment_allocation:
            return
        plan = frappe.db.get_value(
            "Material Request Fulfillment",
            self.material_request_fulfillment,
            ["name", "material_request", "company", "status", "plan_revision"],
            as_dict=True,
        )
        if not plan:
            frappe.throw(_("The linked Fulfillment no longer exists."))
        material_request = frappe.db.get_value(
            "Material Request",
            plan.material_request,
            ["name", "company", "docstatus", "request_usage"],
            as_dict=True,
            for_update=True,
        )
        locked_plan = frappe.db.get_value(
            "Material Request Fulfillment",
            self.material_request_fulfillment,
            ["name", "material_request", "company", "status", "plan_revision"],
            as_dict=True,
            for_update=True,
        )
        current_plan = frappe.db.get_value(
            "Material Request Fulfillment",
            {"material_request": plan.material_request, "status": "Planned"},
            ["name", "plan_revision"],
            order_by="plan_revision desc",
            as_dict=True,
        )
        if (
            not material_request
            or material_request.docstatus != 1
            or material_request.request_usage != "Customer Demo"
            or material_request.company != self.company
            or not locked_plan
            or locked_plan.company != self.company
            or locked_plan.status != "Planned"
            or not current_plan
            or current_plan.name != locked_plan.name
        ):
            frappe.throw(_("The linked Fulfillment is no longer the active Demo plan."))
        pool_location = frappe.db.get_value("Company", self.company, "demo_asset_pool_location")
        if (
            not pool_location
            or pool_location != self.target_location
            or frappe.db.get_value("Location", pool_location, "is_group")
        ):
            frappe.throw(_("The linked target Location no longer matches the active Demo asset pool."))
        persisted = (
            frappe.db.get_value(
                "Stock Asset Conversion",
                self.name,
                [
                    "company",
                    "material_request_fulfillment",
                    "fulfillment_allocation",
                    "operation_id",
                    "target_asset_item",
                    "asset_category",
                    "target_location",
                ],
                as_dict=True,
            )
            if not self.is_new()
            else None
        )
        if persisted:
            for field in (
                "company",
                "material_request_fulfillment",
                "fulfillment_allocation",
                "operation_id",
                "target_asset_item",
                "asset_category",
                "target_location",
            ):
                if self.get(field) != persisted.get(field):
                    frappe.throw(_("Linked Stock Asset Conversion identity cannot be changed."))
            persisted_row = frappe.db.get_value(
                "Stock Asset Conversion Item",
                {"parent": self.name},
                [
                    "item_code",
                    "warehouse",
                    "qty",
                    "uom",
                    "stock_qty",
                    "stock_uom",
                    "serial_and_batch_bundle",
                    "serial_no",
                    "batch_no",
                ],
                as_dict=True,
            )
            current_row = self.items[0] if len(self.items) == 1 else None
            if (
                not persisted_row
                or not current_row
                or any(
                    current_row.get(field) != persisted_row.get(field)
                    for field in (
                        "item_code",
                        "warehouse",
                        "qty",
                        "uom",
                        "stock_qty",
                        "stock_uom",
                        "serial_and_batch_bundle",
                        "serial_no",
                        "batch_no",
                    )
                )
            ):
                frappe.throw(_("Linked Stock Asset Conversion source cannot be changed."))
        allocation = frappe.db.get_value(
            "Material Request Fulfillment Allocation",
            self.fulfillment_allocation,
            [
                "parent",
                "source_type",
                "qty",
                "item_code",
                "fixed_asset_item",
                "equipment_model",
                "conversion_state",
                "conversion_source_warehouse",
                "conversion_source_bundle",
            ],
            as_dict=True,
            for_update=True,
        )
        if (
            not allocation
            or allocation.parent != self.material_request_fulfillment
            or allocation.source_type != "Stock Conversion"
            or flt(allocation.qty) != 1
            or self.operation_id
            != f"fulfillment-allocation:{self.fulfillment_allocation}:stock-asset-conversion"
        ):
            frappe.throw(_("The linked allocation is no longer an active Stock Conversion."))
        if allocation.conversion_state in {"Ready", "Cancelled"} and self.docstatus == 0:
            frappe.throw(_("The linked allocation already has a conversion lifecycle result."))
        row = self.items[0] if self.items else None
        if (
            not row
            or row.item_code != allocation.item_code
            or flt(row.qty) != 1
            or (
                allocation.conversion_source_warehouse
                and row.warehouse != allocation.conversion_source_warehouse
            )
            or (
                allocation.conversion_source_bundle
                and row.serial_and_batch_bundle != allocation.conversion_source_bundle
            )
        ):
            frappe.throw(_("The conversion source no longer matches the linked allocation."))
        model = frappe.db.get_value(
            "Equipment Model",
            allocation.equipment_model,
            ["name", "stock_item", "fixed_asset_item", "company", "disabled", "allow_demo"],
            as_dict=True,
        )
        if (
            not model
            or model.stock_item != allocation.item_code
            or model.fixed_asset_item != allocation.fixed_asset_item
            or model.disabled
            or not model.allow_demo
            or (model.company and model.company != self.company)
        ):
            frappe.throw(_("The linked Equipment Model is no longer eligible."))

    def update_stock_ledger(self) -> None:
        row = self.items[0]
        sl_entry = self.get_sl_entries(
            row,
            {
                "actual_qty": -flt(row.stock_qty),
                "serial_and_batch_bundle": row.serial_and_batch_bundle,
                "warehouse": row.warehouse,
            },
        )
        self.make_sl_entries([sl_entry])

    def make_gl_entries(
        self,
        gl_entries: list[frappe._dict] | None = None,
        from_repost: bool = False,
        via_landed_cost_voucher: bool = False,
    ) -> None:
        if self.docstatus == 2:
            make_reverse_gl_entries(voucher_type=self.doctype, voucher_no=self.name)
            return

        entries = gl_entries or self._build_conversion_gl_entries()
        if entries:
            post_gl_entries(entries, merge_entries=False, from_repost=from_repost)

    def _validate_single_source_unit(self) -> None:
        if len(self.items) != 1:
            frappe.throw(_("Stock Asset Conversion requires exactly one source item."))
        if flt(self.items[0].qty) != 1:
            frappe.throw(_("Stock Asset Conversion currently supports exactly one stock unit."))

    def _validate_items(self) -> None:
        row = self.items[0]
        source = frappe.get_cached_value(
            "Item",
            row.item_code,
            ["is_stock_item", "is_fixed_asset", "disabled", "stock_uom"],
            as_dict=True,
        )
        target = frappe.get_cached_value(
            "Item",
            self.target_asset_item,
            ["is_stock_item", "is_fixed_asset", "disabled", "asset_category"],
            as_dict=True,
        )
        if not source or not source.is_stock_item or source.is_fixed_asset or source.disabled:
            frappe.throw(_("Source Item must be an enabled stock Item and must not be a fixed-asset Item."))
        if not target or target.is_stock_item or not target.is_fixed_asset or target.disabled:
            frappe.throw(_("Target Item must be an enabled non-stock fixed-asset Item."))
        if target.asset_category and target.asset_category != self.asset_category:
            frappe.throw(_("Asset Category must match the Target Asset Item."))

        row.stock_qty = 1
        row.stock_uom = source.stock_uom
        row.uom = source.stock_uom

    def _validate_warehouse(self) -> None:
        warehouse = self.items[0].warehouse
        validate_warehouse_company(warehouse, self.company)
        validate_disabled_warehouse(warehouse)

    def _set_and_validate_fixed_asset_account(self) -> None:
        account = get_asset_category_account(
            "fixed_asset_account",
            item=self.target_asset_item,
            asset_category=self.asset_category,
            company=self.company,
        )
        if not account:
            frappe.throw(_("Set a Fixed Asset Account for this Asset Category and Company."))
        self.fixed_asset_account = account
        validate_account_head(1, account, self.company, _("Fixed Asset"))
        if frappe.get_cached_value("Account", account, "account_type") != "Fixed Asset":
            frappe.throw(_("The resolved Fixed Asset Account must have account type Fixed Asset."))

    def _validate_depreciation_configuration(self) -> None:
        if self.accounting_treatment not in {FULL_DEPRECIATION, NORMAL_DEPRECIATION}:
            frappe.throw(_("Select a supported Accounting Treatment."))
        if self.accounting_treatment == FULL_DEPRECIATION:
            self.total_number_of_depreciations = 1
            self.expected_value_after_useful_life = 0
            self.depreciation_start_date = add_months(self.posting_date, 1)
        elif self.total_number_of_depreciations < 1:
            frappe.throw(_("Total Number of Depreciations must be greater than zero."))
        if self.frequency_of_depreciation < 1:
            frappe.throw(_("Frequency of Depreciation must be greater than zero."))

    def _build_conversion_gl_entries(self, stock_value_difference: float | None = None) -> list[frappe._dict]:
        row = self.items[0]
        if stock_value_difference is None:
            ledger_rows = self.get_stock_ledger_details().get(row.name, [])
            if len(ledger_rows) != 1:
                frappe.throw(_("Expected exactly one active Stock Ledger Entry for this conversion."))
            stock_value_difference = flt(ledger_rows[0].stock_value_difference)
        if stock_value_difference >= 0:
            frappe.throw(_("The conversion Stock Ledger Entry must reduce stock value."))
        amount = abs(stock_value_difference)

        inventory_account = self.get_inventory_account_dict(row, self.get_inventory_account_map())
        inventory_account_name = cast(str, inventory_account.account)
        cost_center = self.cost_center or frappe.get_cached_value("Company", self.company, "cost_center")
        fixed_asset_account = cast(str, self.fixed_asset_account)
        fixed_asset_currency = frappe.get_cached_value("Account", fixed_asset_account, "account_currency")

        return [
            self.get_gl_dict(
                {
                    "account": fixed_asset_account,
                    "against": inventory_account_name,
                    "debit": amount,
                    "cost_center": cost_center,
                    "remarks": _("Stock converted to fixed asset"),
                    "voucher_detail_no": row.name,
                },
                fixed_asset_currency,
                item=row,
            ),
            self.get_gl_dict(
                {
                    "account": inventory_account_name,
                    "against": fixed_asset_account,
                    "credit": amount,
                    "cost_center": cost_center,
                    "remarks": _("Stock converted to fixed asset"),
                    "voucher_detail_no": row.name,
                },
                inventory_account.account_currency,
                item=row,
            ),
        ]

    def build_preview_facts(
        self,
        stock_value: float | None = None,
        valuation_rate: float | None = None,
    ) -> dict[str, Any]:
        """Build deterministic review facts without persisting accounting records."""
        row = self.items[0]
        if stock_value is None or valuation_rate is None:
            valuation_rate = flt(
                get_incoming_rate(
                    frappe._dict(
                        {
                            "item_code": row.item_code,
                            "warehouse": row.warehouse,
                            "posting_date": self.posting_date,
                            "posting_time": self.posting_time,
                            "qty": -flt(row.stock_qty),
                            "serial_no": row.serial_no,
                            "batch_no": row.batch_no,
                            "voucher_type": self.doctype,
                            "voucher_no": self.name,
                            "voucher_detail_no": row.name,
                            "company": self.company,
                            "serial_and_batch_bundle": row.serial_and_batch_bundle,
                        }
                    ),
                    raise_error_if_no_rate=True,
                )
            )
            stock_value = flt(valuation_rate * flt(row.stock_qty))
        stock_value = flt(stock_value)
        valuation_rate = flt(valuation_rate)
        if stock_value <= 0 or valuation_rate <= 0:
            frappe.throw(_("A positive native stock valuation is required for preview."))
        threshold = frappe.db.get_value("Company", self.company, "demo_low_value_asset_threshold")
        if threshold is None:
            frappe.throw(_("Configure the Demo low-value asset threshold before review."))
        recommendation = FULL_DEPRECIATION if stock_value <= flt(threshold) else NORMAL_DEPRECIATION
        inventory_account = self.get_inventory_account_dict(row, self.get_inventory_account_map())
        gl_entries = self._build_conversion_gl_entries(stock_value_difference=-stock_value)
        facts = {
            "company": self.company,
            "fulfillment": self.material_request_fulfillment,
            "allocation": self.fulfillment_allocation,
            "operation_id": self.operation_id,
            "source_item": row.item_code,
            "warehouse": row.warehouse,
            "qty": flt(row.stock_qty),
            "serial_and_batch_bundle": row.serial_and_batch_bundle,
            "serial_no": row.serial_no,
            "batch_no": row.batch_no,
            "target_item": self.target_asset_item,
            "asset_category": self.asset_category,
            "target_location": self.target_location,
            "posting_date": self.posting_date,
            "posting_time": self.posting_time,
            "valuation_rate": valuation_rate,
            "stock_value": stock_value,
            "inventory_account": inventory_account.account,
            "fixed_asset_account": self.fixed_asset_account,
            "cost_center": self.cost_center
            or frappe.get_cached_value("Company", self.company, "cost_center"),
            "threshold": flt(threshold),
            "recommendation": recommendation,
            "treatment": self.accounting_treatment,
            "override_reason": (self.treatment_override_reason or "").strip(),
            "finance_book": self.finance_book,
            "depreciation_start_date": self.depreciation_start_date,
            "frequency": self.frequency_of_depreciation,
            "count": self.total_number_of_depreciations,
            "residual": flt(self.expected_value_after_useful_life),
        }
        facts["preview_hash"] = hashlib.sha256(
            json.dumps(facts, sort_keys=True, default=str).encode()
        ).hexdigest()
        facts["stock_ledger"] = [
            {
                "item_code": row.item_code,
                "warehouse": row.warehouse,
                "qty": -flt(row.stock_qty),
                "valuation_rate": valuation_rate,
                "stock_value_difference": -stock_value,
            }
        ]
        facts["general_ledger"] = [
            {
                "account": entry.account,
                "debit": flt(entry.debit),
                "credit": flt(entry.credit),
            }
            for entry in gl_entries
        ]
        facts["depreciation"] = {
            "treatment": self.accounting_treatment,
            "finance_book": self.finance_book,
            "schedule_start": self.depreciation_start_date,
            "frequency_months": self.frequency_of_depreciation,
            "number_of_depreciations": self.total_number_of_depreciations,
            "expected_residual_value": flt(self.expected_value_after_useful_life),
            "expected_single_entry_amount": stock_value
            if self.accounting_treatment == FULL_DEPRECIATION
            else None,
            "expected_nbv_after_single_entry": 0 if self.accounting_treatment == FULL_DEPRECIATION else None,
        }
        return facts

    def _invalidate_stale_preview(self) -> None:
        if not self.fulfillment_allocation or not self.preview_hash or self.is_new():
            return
        current = self.build_preview_facts(
            stock_value=flt(self.preview_stock_value),
            valuation_rate=flt(self.preview_valuation_rate),
        )
        if current["preview_hash"] == self.preview_hash:
            return
        self.preview_stock_value = 0
        self.preview_valuation_rate = 0
        self.preview_recommendation = None
        self.preview_hash = None
        self.preview_approved_by = None
        self.preview_approved_on = None

    def _validate_approved_preview_against_actual(self) -> None:
        if not self.fulfillment_allocation:
            return
        row = self.items[0]
        ledger_rows = self.get_stock_ledger_details().get(row.name, [])
        if len(ledger_rows) != 1:
            frappe.throw(_("Expected exactly one active Stock Ledger Entry for this conversion."))
        actual_value = abs(flt(ledger_rows[0].stock_value_difference))
        facts = self.build_preview_facts(
            stock_value=actual_value,
            valuation_rate=actual_value / flt(row.stock_qty),
        )
        if facts["preview_hash"] != self.preview_hash:
            frappe.throw(
                _("Stock valuation or accounting inputs changed. Accounts review is required again.")
            )

    def _create_and_submit_asset(self) -> None:
        row = self.items[0]
        ledger_rows = self.get_stock_ledger_details().get(row.name, [])
        if len(ledger_rows) != 1:
            frappe.throw(_("Stock valuation is unavailable for Asset creation."))
        amount = abs(flt(ledger_rows[0].stock_value_difference))

        asset = self._build_asset(amount)
        self._validate_asset_acquisition_context(asset)
        asset.insert()
        asset.submit()
        if frappe.db.exists("GL Entry", {"voucher_type": "Asset", "voucher_no": asset.name}):
            frappe.throw(_("Asset submission created duplicate acquisition accounting."))
        self.db_set("asset", asset.name, update_modified=False)

    def _build_asset(self, amount: float) -> Document:
        return cast(
            Document,
            frappe.get_doc(
                {
                    "doctype": "Asset",
                    "asset_name": self.target_asset_item,
                    "item_code": self.target_asset_item,
                    "asset_category": self.asset_category,
                    "company": self.company,
                    "purchase_date": self.posting_date,
                    "available_for_use_date": self.posting_date,
                    "purchase_amount": amount,
                    "net_purchase_amount": amount,
                    "calculate_depreciation": 1,
                    "asset_type": "Existing Asset",
                    "asset_owner": "Company",
                    "asset_quantity": 1,
                    "location": self.target_location,
                    "cost_center": self.cost_center,
                    "finance_books": [self._asset_finance_book()],
                }
            ),
        )

    def _validate_asset_acquisition_context(self, asset: Document) -> None:
        if asset.get("asset_type") != "Existing Asset":
            frappe.throw(_("Stock Asset Conversion cannot create a composite Asset."))
        if asset.get("purchase_receipt"):
            frappe.throw(_("Stock Asset Conversion Asset must not be linked to a Purchase Receipt."))
        if asset.get("purchase_invoice"):
            if frappe.db.get_value("Purchase Invoice", asset.get("purchase_invoice"), "update_stock"):
                frappe.throw(
                    _("Stock Asset Conversion Asset must not be linked to a stock-updating Purchase Invoice.")
                )
            frappe.throw(_("Stock Asset Conversion Asset must not be linked to a Purchase Invoice."))

    def _asset_finance_book(self) -> dict[str, Any]:
        return {
            "finance_book": self.finance_book,
            "depreciation_method": "Straight Line",
            "total_number_of_depreciations": self.total_number_of_depreciations,
            "frequency_of_depreciation": self.frequency_of_depreciation,
            "expected_value_after_useful_life": self.expected_value_after_useful_life,
            "depreciation_start_date": self.depreciation_start_date,
        }

    def _cancel_asset(self) -> None:
        if not self.asset:
            return
        asset = cast(Document, frappe.get_doc("Asset", self.asset))
        if asset.docstatus == 1:
            asset.cancel()
