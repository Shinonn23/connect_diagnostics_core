# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast
from unittest.mock import patch

import frappe
from erpnext.assets.doctype.asset.asset import make_sales_invoice
from erpnext.assets.doctype.asset.depreciation import make_depreciation_entry
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import add_months, today

from connect_diagnostics_core.connect_diagnostics_stock.doctype.stock_asset_conversion.stock_asset_conversion import (
    FULL_DEPRECIATION,
    NORMAL_DEPRECIATION,
    StockAssetConversion,
)

COMPANY = "_Test Company"
WAREHOUSE = "_Test Warehouse - _TC"
SOURCE_ITEM = "_Test TSK512 Stock Item"
SERIAL_ITEM = "_Test TSK512 Serialized Item"
TARGET_ITEM = "_Test TSK512 Asset Item"
ASSET_CATEGORY = "Computers"
LOCATION = "_Test TSK512 Asset Pool"
CUSTOMER = "_TEST-TSK512-CUSTOMER"
PRICE_LIST = "_Test TSK512 Selling"

# The test builds its exact accounting/stock masters below. Avoid ERPNext's broad
# bootstrap generator, which is incompatible with this app's mandatory Customer Code.
IGNORE_TEST_RECORD_DEPENDENCIES = [
    "Account",
    "Asset",
    "Asset Category",
    "Batch",
    "Company",
    "Cost Center",
    "Finance Book",
    "Item",
    "Location",
    "Material Request Fulfillment",
    "Material Request Fulfillment Allocation",
    "Serial and Batch Bundle",
    "Stock Asset Conversion",
    "UOM",
    "User",
    "Warehouse",
]


def _ensure_test_master_data() -> None:
    thai_tax_settings = frappe.get_single("Thai Tax Settings")
    if not any(row.company == COMPANY for row in thai_tax_settings.company_accounts):
        thai_tax_settings.append("company_accounts", {"company": COMPANY})
        thai_tax_settings.save(ignore_permissions=True)

    if not frappe.db.exists("Asset Category", ASSET_CATEGORY):
        category = frappe.get_doc(
            {
                "doctype": "Asset Category",
                "asset_category_name": ASSET_CATEGORY,
                "accounts": [
                    {
                        "company_name": COMPANY,
                        "fixed_asset_account": "_Test Fixed Asset - _TC",
                        "accumulated_depreciation_account": "_Test Accumulated Depreciations - _TC",
                        "depreciation_expense_account": "_Test Depreciations - _TC",
                    }
                ],
            }
        )
        category.insert()

    if not frappe.db.exists("Item", SOURCE_ITEM):
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": SOURCE_ITEM,
                "item_name": SOURCE_ITEM,
                "item_group": "All Item Groups",
                "stock_uom": "_Test UOM",
                "is_stock_item": 1,
                "is_fixed_asset": 0,
            }
        ).insert()

    if not frappe.db.exists("Item", SERIAL_ITEM):
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": SERIAL_ITEM,
                "item_name": SERIAL_ITEM,
                "item_group": "All Item Groups",
                "stock_uom": "_Test UOM",
                "is_stock_item": 1,
                "is_fixed_asset": 0,
                "has_serial_no": 1,
                "serial_no_series": "_TSK512-SERIAL-.#####",
            }
        ).insert()

    if not frappe.db.exists("Item", TARGET_ITEM):
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": TARGET_ITEM,
                "item_name": TARGET_ITEM,
                "item_group": "All Item Groups",
                "stock_uom": "_Test UOM",
                "is_stock_item": 0,
                "is_fixed_asset": 1,
                "asset_category": ASSET_CATEGORY,
                "auto_create_assets": 0,
            }
        ).insert()

    if not frappe.db.exists("Location", LOCATION):
        frappe.get_doc(
            {
                "doctype": "Location",
                "location_name": LOCATION,
                "is_group": 0,
            }
        ).insert()

    if not frappe.db.exists("Customer", CUSTOMER):
        frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_code": CUSTOMER,
                "customer_name": "_Test TSK512 Demo Customer",
                "customer_type": "Company",
                "customer_group": "_Test Customer Group",
                "territory": "_Test Territory",
            }
        ).insert()

    if not frappe.db.exists("Price List", PRICE_LIST):
        frappe.get_doc(
            {
                "doctype": "Price List",
                "price_list_name": PRICE_LIST,
                "enabled": 1,
                "selling": 1,
                "currency": frappe.get_cached_value("Company", COMPANY, "default_currency"),
            }
        ).insert()


def _make_stock_receipt(item_code: str = SOURCE_ITEM) -> Any:
    entry = cast(
        Document,
        frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Material Receipt",
                "purpose": "Material Receipt",
                "company": COMPANY,
                "set_posting_time": 1,
                "posting_date": today(),
                "posting_time": "09:00:00",
                "items": [
                    {
                        "item_code": item_code,
                        "t_warehouse": WAREHOUSE,
                        "qty": 1,
                        "uom": "_Test UOM",
                        "stock_uom": "_Test UOM",
                        "conversion_factor": 1,
                        "basic_rate": 125.5,
                    }
                ],
            }
        ),
    )
    entry.insert()
    entry.submit()
    return entry


def _draft(**overrides: object) -> StockAssetConversion:
    values: dict[str, object] = {
        "doctype": "Stock Asset Conversion",
        "company": COMPANY,
        "posting_date": today(),
        "posting_time": "12:00:00",
        "target_asset_item": TARGET_ITEM,
        "asset_category": ASSET_CATEGORY,
        "target_location": LOCATION,
        "accounting_treatment": FULL_DEPRECIATION,
        "depreciation_start_date": today(),
        "frequency_of_depreciation": 1,
        "total_number_of_depreciations": 1,
        "expected_value_after_useful_life": 0,
        "items": [{"item_code": SOURCE_ITEM, "warehouse": WAREHOUSE, "qty": 1}],
    }
    values.update(overrides)
    return cast(StockAssetConversion, frappe.get_doc(values))


@contextmanager
def _inactive_asset_posting_workflows() -> Iterator[None]:
    """Serialize native posting tests against the dedicated local.test site."""
    workflows = frappe.get_all(
        "Workflow",
        filters={
            "document_type": ["in", ["Journal Entry", "Sales Invoice"]],
            "is_active": 1,
        },
        pluck="name",
    )
    for workflow in workflows:
        frappe.db.set_value("Workflow", workflow, "is_active", 0, update_modified=False)
    frappe.clear_cache(doctype="Journal Entry")
    frappe.clear_cache(doctype="Sales Invoice")
    try:
        yield
    finally:
        for workflow in workflows:
            frappe.db.set_value("Workflow", workflow, "is_active", 1, update_modified=False)
        frappe.clear_cache(doctype="Journal Entry")
        frappe.clear_cache(doctype="Sales Invoice")


class TestStockAssetConversionUnit(UnitTestCase):
    def test_preview_recommendation_uses_configured_threshold_boundary(self) -> None:
        doc = _draft()
        doc.name = "SAC-PREVIEW"
        doc.fixed_asset_account = "Fixed Asset - TC"
        doc.items[0].name = "SAC-PREVIEW-ROW"
        doc.items[0].stock_qty = 1
        gl_rows = [
            frappe._dict(account="Fixed Asset - TC", debit=100, credit=0),
            frappe._dict(account="Inventory - TC", debit=0, credit=100),
        ]
        with (
            patch.object(frappe.db, "get_value", return_value=100),
            patch.object(frappe, "get_cached_value", return_value="Main - TC"),
            patch.object(doc, "get_inventory_account_map", return_value=frappe._dict()),
            patch.object(
                doc,
                "get_inventory_account_dict",
                return_value=frappe._dict(account="Inventory - TC"),
            ),
            patch.object(doc, "_build_conversion_gl_entries", return_value=gl_rows),
        ):
            below = doc.build_preview_facts(stock_value=99, valuation_rate=99)
            equal = doc.build_preview_facts(stock_value=100, valuation_rate=100)
            above = doc.build_preview_facts(stock_value=101, valuation_rate=101)

        self.assertEqual(below["recommendation"], FULL_DEPRECIATION)
        self.assertEqual(equal["recommendation"], FULL_DEPRECIATION)
        self.assertEqual(above["recommendation"], NORMAL_DEPRECIATION)
        self.assertNotEqual(equal["preview_hash"], above["preview_hash"])

    def test_requires_exactly_one_unit(self) -> None:
        doc = _draft(items=[])
        with self.assertRaises(frappe.ValidationError):
            doc._validate_single_source_unit()

        doc = _draft(items=[{"item_code": SOURCE_ITEM, "warehouse": WAREHOUSE, "qty": 2}])
        with self.assertRaises(frappe.ValidationError):
            doc._validate_single_source_unit()

    def test_full_depreciation_forces_one_zero_residual_entry(self) -> None:
        doc = _draft(total_number_of_depreciations=12, expected_value_after_useful_life=50)
        doc._validate_depreciation_configuration()
        self.assertEqual(doc.total_number_of_depreciations, 1)
        self.assertEqual(doc.expected_value_after_useful_life, 0)
        self.assertEqual(doc.depreciation_start_date, add_months(doc.posting_date, 1))

    def test_normal_depreciation_preserves_accounts_schedule(self) -> None:
        doc = _draft(
            accounting_treatment=NORMAL_DEPRECIATION,
            total_number_of_depreciations=12,
            expected_value_after_useful_life=10,
        )
        doc._validate_depreciation_configuration()
        self.assertEqual(doc.total_number_of_depreciations, 12)
        self.assertEqual(doc.expected_value_after_useful_life, 10)
        self.assertEqual(doc.depreciation_start_date, today())

    @patch.object(StockAssetConversion, "get_stock_ledger_details")
    @patch.object(StockAssetConversion, "get_inventory_account_map")
    @patch.object(StockAssetConversion, "get_inventory_account_dict")
    @patch.object(StockAssetConversion, "get_gl_dict")
    @patch.object(frappe, "get_cached_value")
    def test_gl_builder_uses_actual_negative_sle_value(
        self,
        get_cached_value,
        get_gl_dict,
        get_inventory_account_dict,
        get_inventory_account_map,
        get_stock_ledger_details,
    ) -> None:
        doc = _draft()
        doc.name = "SAC-TEST"
        doc.fixed_asset_account = "Fixed Asset - TC"
        doc.items[0].name = "SAC-ROW"
        get_stock_ledger_details.return_value = {"SAC-ROW": [frappe._dict(stock_value_difference=-125.5)]}
        get_inventory_account_map.return_value = frappe._dict()
        get_inventory_account_dict.return_value = frappe._dict(
            account="Inventory - TC", account_currency="THB"
        )
        get_cached_value.side_effect = ["Main - TC", "THB"]
        get_gl_dict.side_effect = lambda values, *_args, **_kwargs: frappe._dict(values)

        entries = doc._build_conversion_gl_entries()

        self.assertEqual(entries[0].debit, 125.5)
        self.assertEqual(entries[1].credit, 125.5)
        self.assertEqual(entries[0].account, "Fixed Asset - TC")
        self.assertEqual(entries[1].account, "Inventory - TC")


class TestStockAssetConversionIntegration(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        _ensure_test_master_data()

    def test_submit_and_cancel_use_conversion_ledgers_and_no_asset_gl(self) -> None:
        _make_stock_receipt()
        # Keep this voucher after all same-day proof vouchers so its reversal
        # cannot be ordered ahead of an earlier test's still-active outward SLE.
        conversion = _draft(posting_time="23:59:00")
        conversion.insert()
        conversion.submit()

        sle = frappe.db.get_value(
            "Stock Ledger Entry",
            {
                "voucher_type": "Stock Asset Conversion",
                "voucher_no": conversion.name,
                "is_cancelled": 0,
            },
            ["actual_qty", "stock_value_difference"],
            as_dict=True,
        )
        self.assertIsNotNone(sle)
        self.assertEqual(sle.actual_qty, -1)
        self.assertLess(sle.stock_value_difference, 0)

        gl_entries = frappe.get_all(
            "GL Entry",
            filters={
                "voucher_type": "Stock Asset Conversion",
                "voucher_no": conversion.name,
                "is_cancelled": 0,
            },
            fields=["account", "debit", "credit"],
        )
        self.assertEqual(len(gl_entries), 2)
        self.assertEqual(sum(row.debit for row in gl_entries), abs(sle.stock_value_difference))
        self.assertEqual(sum(row.credit for row in gl_entries), abs(sle.stock_value_difference))

        asset = frappe.get_doc("Asset", conversion.asset)
        self.assertEqual(asset.item_code, TARGET_ITEM)
        self.assertEqual(asset.docstatus, 1)
        self.assertEqual(len(asset.finance_books), 1)
        self.assertEqual(asset.finance_books[0].total_number_of_depreciations, 1)
        self.assertFalse(frappe.db.exists("GL Entry", {"voucher_type": "Asset", "voucher_no": asset.name}))

        conversion.cancel()
        self.assertEqual(frappe.db.get_value("Asset", asset.name, "docstatus"), 2)
        self.assertTrue(
            frappe.db.exists(
                "Stock Ledger Entry",
                {
                    "voucher_type": "Stock Asset Conversion",
                    "voucher_no": conversion.name,
                    "is_cancelled": 1,
                },
            )
        )

    def test_posting_failure_rolls_back_stock_gl_and_asset(self) -> None:
        _make_stock_receipt()
        conversion = _draft()
        conversion.insert()
        frappe.db.savepoint("before_failed_stock_asset_conversion")

        create_asset = StockAssetConversion._create_and_submit_asset

        def fail_after_asset(doc: StockAssetConversion) -> None:
            create_asset(doc)
            frappe.throw(frappe._("Simulated failure after Asset submission."))

        with (
            patch.object(StockAssetConversion, "_create_and_submit_asset", fail_after_asset),
            self.assertRaises(frappe.ValidationError),
        ):
            conversion.submit()

        asset_name = conversion.asset
        frappe.db.rollback(save_point="before_failed_stock_asset_conversion")

        self.assertFalse(
            frappe.db.exists(
                "Stock Ledger Entry",
                {"voucher_type": conversion.doctype, "voucher_no": conversion.name},
            )
        )
        self.assertFalse(
            frappe.db.exists(
                "GL Entry",
                {"voucher_type": conversion.doctype, "voucher_no": conversion.name},
            )
        )
        self.assertTrue(asset_name)
        self.assertFalse(frappe.db.exists("Asset", asset_name))

    def test_rejects_composite_asset_before_any_acquisition_posting(self) -> None:
        _make_stock_receipt()
        conversion = _draft()
        conversion.insert()
        build_asset = StockAssetConversion._build_asset

        def build_composite_asset(doc: StockAssetConversion, amount: float) -> Document:
            asset = build_asset(doc, amount)
            asset.set("asset_type", "Composite Asset")
            return asset

        frappe.db.savepoint("before_rejected_composite_asset")
        with (
            patch.object(StockAssetConversion, "_build_asset", build_composite_asset),
            self.assertRaisesRegex(frappe.ValidationError, "composite Asset"),
        ):
            conversion.submit()
        frappe.db.rollback(save_point="before_rejected_composite_asset")

        self.assertFalse(
            frappe.db.exists(
                "Stock Ledger Entry",
                {"voucher_type": conversion.doctype, "voucher_no": conversion.name},
            )
        )
        self.assertFalse(
            frappe.db.exists(
                "GL Entry",
                {"voucher_type": conversion.doctype, "voucher_no": conversion.name},
            )
        )

    def test_rejects_purchase_acquisition_contexts(self) -> None:
        conversion = _draft()
        asset = conversion._build_asset(125.5)
        asset.set("purchase_receipt", "_Test TSK512 Purchase Receipt")
        with self.assertRaisesRegex(frappe.ValidationError, "Purchase Receipt"):
            conversion._validate_asset_acquisition_context(asset)

        asset.set("purchase_receipt", None)
        asset.set("purchase_invoice", "_Test TSK512 Purchase Invoice")
        with (
            patch.object(frappe.db, "get_value", return_value=1),
            self.assertRaisesRegex(frappe.ValidationError, "stock-updating Purchase Invoice"),
        ):
            conversion._validate_asset_acquisition_context(asset)

    def test_serialized_stock_uses_native_outward_bundle_and_restores_on_cancel(self) -> None:
        original_serial_batch_enabled = frappe.db.get_single_value(
            "Stock Settings", "enable_serial_and_batch_no_for_item"
        )
        original_auto_bundle = frappe.db.get_single_value(
            "Stock Settings", "auto_create_serial_and_batch_bundle_for_outward"
        )
        frappe.db.set_single_value("Stock Settings", "enable_serial_and_batch_no_for_item", 1)
        frappe.db.set_single_value("Stock Settings", "auto_create_serial_and_batch_bundle_for_outward", 1)
        try:
            receipt = _make_stock_receipt(SERIAL_ITEM)
            receipt.reload()
            serial_no = frappe.db.get_value(
                "Serial and Batch Entry",
                {"parent": receipt.items[0].serial_and_batch_bundle},
                "serial_no",
            )
            self.assertTrue(serial_no)

            conversion = _draft(items=[{"item_code": SERIAL_ITEM, "warehouse": WAREHOUSE, "qty": 1}])
            conversion.insert()
            conversion.submit()
            conversion.reload()

            bundle_name = conversion.items[0].serial_and_batch_bundle
            self.assertTrue(bundle_name)
            bundle = frappe.get_doc("Serial and Batch Bundle", bundle_name)
            self.assertEqual(bundle.type_of_transaction, "Outward")
            self.assertEqual(bundle.voucher_type, conversion.doctype)
            self.assertEqual(bundle.voucher_no, conversion.name)
            self.assertEqual(abs(bundle.total_qty), 1)
            self.assertIsNone(frappe.db.get_value("Serial No", serial_no, "warehouse"))

            conversion.cancel()
            self.assertEqual(frappe.db.get_value("Serial No", serial_no, "warehouse"), WAREHOUSE)
        finally:
            frappe.db.set_single_value(
                "Stock Settings",
                "enable_serial_and_batch_no_for_item",
                original_serial_batch_enabled,
            )
            frappe.db.set_single_value(
                "Stock Settings",
                "auto_create_serial_and_batch_bundle_for_outward",
                original_auto_bundle,
            )

    def test_one_entry_depreciation_reaches_zero_and_asset_can_be_sold(self) -> None:
        with _inactive_asset_posting_workflows():
            self._assert_full_depreciation_and_sale()

    def test_normal_depreciation_uses_native_multi_entry_schedule(self) -> None:
        with _inactive_asset_posting_workflows():
            _make_stock_receipt()
            conversion = _draft(
                accounting_treatment=NORMAL_DEPRECIATION,
                depreciation_start_date=add_months(today(), 1),
                total_number_of_depreciations=2,
                expected_value_after_useful_life=25,
            )
            conversion.insert()
            conversion.submit()

            schedule_name = frappe.db.get_value(
                "Asset Depreciation Schedule",
                {"asset": conversion.asset, "docstatus": 1, "status": "Active"},
                "name",
            )
            self.assertTrue(schedule_name)
            schedule = frappe.get_doc("Asset Depreciation Schedule", schedule_name)
            self.assertEqual(len(schedule.depreciation_schedule), 2)

            opening_value = frappe.db.get_value(
                "Asset Finance Book", {"parent": conversion.asset}, "value_after_depreciation"
            )
            make_depreciation_entry(
                schedule.name,
                date=schedule.depreciation_schedule[0].schedule_date,
            )
            asset = frappe.get_doc("Asset", conversion.asset)
            self.assertGreater(asset.finance_books[0].value_after_depreciation, 25)
            self.assertLess(asset.finance_books[0].value_after_depreciation, opening_value)
            self.assertNotEqual(asset.status, "Fully Depreciated")

    def _assert_full_depreciation_and_sale(self) -> None:
        _make_stock_receipt()
        conversion = _draft()
        conversion.insert()
        conversion.submit()

        schedule_name = frappe.db.get_value(
            "Asset Depreciation Schedule",
            {"asset": conversion.asset, "docstatus": 1, "status": "Active"},
            "name",
        )
        self.assertTrue(schedule_name)
        schedule = frappe.get_doc("Asset Depreciation Schedule", schedule_name)
        self.assertEqual(
            len(schedule.depreciation_schedule),
            1,
            msg=[row.as_dict() for row in schedule.depreciation_schedule],
        )
        make_depreciation_entry(
            schedule.name,
            date=schedule.depreciation_schedule[0].schedule_date,
        )

        asset = frappe.get_doc("Asset", conversion.asset)
        self.assertEqual(asset.finance_books[0].value_after_depreciation, 0)
        self.assertEqual(asset.status, "Fully Depreciated")

        sales_invoice = make_sales_invoice(
            asset=asset.name,
            item_code=asset.item_code,
            company=asset.company,
            sell_qty=asset.asset_quantity,
        )
        sales_invoice.customer = CUSTOMER
        sales_invoice.due_date = today()
        sales_invoice.selling_price_list = PRICE_LIST
        sales_invoice.price_list_currency = frappe.get_cached_value(
            "Company", asset.company, "default_currency"
        )
        sales_invoice.plc_conversion_rate = 1
        sales_invoice.items[0].rate = 50
        sales_invoice.insert()
        sales_invoice.submit()

        self.assertEqual(frappe.db.get_value("Asset", asset.name, "status"), "Sold")
