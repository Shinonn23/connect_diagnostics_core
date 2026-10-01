# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import cast

import frappe
from frappe.tests import IntegrationTestCase

from connect_diagnostics_core.connect_diagnostics_stock.doctype.equipment_model.equipment_model import (
    EquipmentModel,
    get_eligible_demo_stock_items,
)

COMPANY = "_Test Company"
ASSET_CATEGORY = "_Test TSK512 Equipment Category"
IGNORE_TEST_RECORD_DEPENDENCIES = ["Asset Category", "Company", "Item", "UOM"]


def _make_item(
    item_code: str,
    *,
    is_stock_item: int,
    is_fixed_asset: int,
    disabled: int = 0,
) -> None:
    frappe.get_doc(
        {
            "doctype": "Item",
            "item_code": item_code,
            "item_name": item_code,
            "item_group": "All Item Groups",
            "stock_uom": "_Test UOM",
            "is_stock_item": is_stock_item,
            "is_fixed_asset": is_fixed_asset,
            "asset_category": ASSET_CATEGORY if is_fixed_asset else None,
            "disabled": disabled,
        }
    ).insert()


def _model(
    model_code: str,
    stock_item: str,
    fixed_asset_item: str,
    **overrides: object,
) -> EquipmentModel:
    values: dict[str, object] = {
        "doctype": "Equipment Model",
        "model_code": model_code,
        "model_name": model_code,
        "stock_item": stock_item,
        "fixed_asset_item": fixed_asset_item,
        "allow_demo": 1,
        "allow_stock_to_asset_conversion": 1,
    }
    values.update(overrides)
    return cast(EquipmentModel, frappe.get_doc(values))


def _insert_model_in_separate_transaction(
    site: str,
    sites_path: str,
    barrier: threading.Barrier,
    model_code: str,
    stock_item: str,
    fixed_asset_item: str,
) -> str:
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect(set_admin_as_user=True)
    try:
        barrier.wait(timeout=10)
        _model(model_code, stock_item, fixed_asset_item).insert()
        frappe.db.commit()  # nosemgrep - separate connection must publish its concurrency result
        return "inserted"
    except (frappe.QueryDeadlockError, frappe.ValidationError):
        # A simultaneous insert may be selected as the database deadlock victim;
        # either outcome must leave exactly one committed active owner.
        frappe.db.rollback()
        return "conflict"
    finally:
        frappe.destroy()


class TestEquipmentModel(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        if not frappe.db.exists("Asset Category", ASSET_CATEGORY):
            frappe.get_doc(
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
            ).insert()
        suffix = frappe.generate_hash(length=8)
        self.stock_item = f"_Test TSK512 Stock {suffix}"
        self.stock_item_2 = f"_Test TSK512 Stock 2 {suffix}"
        self.fixed_asset_item = f"_Test TSK512 Asset {suffix}"
        self.fixed_asset_item_2 = f"_Test TSK512 Asset 2 {suffix}"
        self.disabled_stock_item = f"_Test TSK512 Disabled {suffix}"
        self.model_prefix = f"_Test TSK512 EM {suffix}"

        _make_item(self.stock_item, is_stock_item=1, is_fixed_asset=0)
        _make_item(self.stock_item_2, is_stock_item=1, is_fixed_asset=0)
        _make_item(self.fixed_asset_item, is_stock_item=0, is_fixed_asset=1)
        _make_item(self.fixed_asset_item_2, is_stock_item=0, is_fixed_asset=1)
        _make_item(self.disabled_stock_item, is_stock_item=1, is_fixed_asset=0, disabled=1)

    def test_invalid_stock_and_fixed_asset_items_are_rejected(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "Stock Item must be a stock Item"):
            _model(
                f"{self.model_prefix} Invalid Stock",
                self.fixed_asset_item,
                self.fixed_asset_item_2,
            ).insert()

        with self.assertRaisesRegex(frappe.ValidationError, "Fixed Asset Item must be"):
            _model(
                f"{self.model_prefix} Invalid Asset",
                self.stock_item,
                self.stock_item_2,
            ).insert()

    def test_same_item_is_rejected_explicitly(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "must be different records"):
            _model(
                f"{self.model_prefix} Same Item",
                self.stock_item,
                self.stock_item,
            ).insert()

    def test_duplicate_active_stock_item_mapping_is_rejected(self) -> None:
        _model(
            f"{self.model_prefix} Stock Owner",
            self.stock_item,
            self.fixed_asset_item,
        ).insert()

        with self.assertRaisesRegex(frappe.ValidationError, "already uses.*Stock Item"):
            _model(
                f"{self.model_prefix} Stock Conflict",
                self.stock_item,
                self.fixed_asset_item_2,
            ).insert()

    def test_duplicate_active_fixed_asset_item_mapping_is_rejected(self) -> None:
        _model(
            f"{self.model_prefix} Asset Owner",
            self.stock_item,
            self.fixed_asset_item,
        ).insert()

        with self.assertRaisesRegex(frappe.ValidationError, "already uses.*Fixed Asset Item"):
            _model(
                f"{self.model_prefix} Asset Conflict",
                self.stock_item_2,
                self.fixed_asset_item,
            ).insert()

    def test_concurrent_active_mapping_creation_keeps_one_owner(self) -> None:
        site = str(frappe.local.site)
        sites_path = str(frappe.local.sites_path)
        frappe.db.commit()  # nosemgrep - worker connections must see the test's Item rows
        barrier = threading.Barrier(2)

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        _insert_model_in_separate_transaction,
                        site,
                        sites_path,
                        barrier,
                        f"{self.model_prefix} Concurrent {number}",
                        self.stock_item,
                        fixed_asset_item,
                    )
                    for number, fixed_asset_item in enumerate(
                        (self.fixed_asset_item, self.fixed_asset_item_2), start=1
                    )
                ]
                results = [future.result(timeout=15) for future in futures]

            self.assertCountEqual(results, ["inserted", "conflict"])
            self.assertEqual(
                frappe.db.count(
                    "Equipment Model",
                    {"stock_item": self.stock_item, "disabled": 0},
                ),
                1,
            )
        finally:
            frappe.db.delete(
                "Equipment Model",
                {"model_code": ["like", f"{self.model_prefix} Concurrent%"]},
            )
            frappe.db.commit()  # nosemgrep - remove records committed by worker connections

    def test_disabled_item_cannot_enable_demo_or_conversion(self) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "both mapped Items to be enabled"):
            _model(
                f"{self.model_prefix} Disabled Demo",
                self.disabled_stock_item,
                self.fixed_asset_item,
                allow_demo=1,
                allow_stock_to_asset_conversion=0,
            ).insert()

        with self.assertRaisesRegex(frappe.ValidationError, "both mapped Items to be enabled"):
            _model(
                f"{self.model_prefix} Disabled Conversion",
                self.disabled_stock_item,
                self.fixed_asset_item,
                allow_demo=0,
                allow_stock_to_asset_conversion=1,
            ).insert()

    def test_demo_eligibility_excludes_disabled_models_and_items(self) -> None:
        allowed = _model(
            f"{self.model_prefix} Allowed",
            self.stock_item,
            self.fixed_asset_item,
            company=None,
        ).insert()
        _model(
            f"{self.model_prefix} Disabled Model",
            self.stock_item_2,
            self.fixed_asset_item_2,
            company=COMPANY,
            disabled=1,
        ).insert()

        eligible_items = get_eligible_demo_stock_items(COMPANY)

        self.assertIn(allowed.stock_item, eligible_items)
        self.assertNotIn(self.stock_item_2, eligible_items)
