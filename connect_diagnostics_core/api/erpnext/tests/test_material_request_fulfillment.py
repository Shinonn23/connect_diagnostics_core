# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import today

from connect_diagnostics_core.api.erpnext import (
    dispatch as dispatch_api,
)
from connect_diagnostics_core.api.erpnext import (
    material_request_fulfillment,
    sales_invoice,
    stock_asset_conversion,
)
from connect_diagnostics_core.connect_diagnostics_stock.doctype.material_request_fulfillment.material_request_fulfillment import (
    MaterialRequestFulfillment,
)
from connect_diagnostics_core.connect_diagnostics_stock.doctype.stock_asset_conversion.test_stock_asset_conversion import (
    CUSTOMER,
    LOCATION,
    PRICE_LIST,
    WAREHOUSE,
    _ensure_test_master_data,
    _make_stock_receipt,
)


class TestMaterialRequestFulfillment(UnitTestCase):
    def test_non_demo_submit_is_ignored(self) -> None:
        doc = frappe._dict(name="MR-1", request_usage="Employee Borrow")
        with patch.object(material_request_fulfillment.frappe, "db") as db:
            self.assertIsNone(material_request_fulfillment.on_submit(cast(Document, doc), "on_submit"))
            db.get_value.assert_not_called()

    def test_direct_insert_requires_internal_handoff_flag(self) -> None:
        doc = MaterialRequestFulfillment(
            {
                "doctype": "Material Request Fulfillment",
                "source_version": 1,
                "status": "Planned",
                "allocations": [],
            }
        )
        material_request_fulfillment.frappe.flags.material_request_fulfillment_handoff = False
        with self.assertRaises(frappe.ValidationError):
            doc.before_insert()

    @patch.object(material_request_fulfillment.frappe, "get_roles", return_value=["Purchase User"])
    def test_purchase_permission_query_is_owner_scoped(self, _roles: MagicMock) -> None:
        with patch.object(material_request_fulfillment.frappe.db, "escape", return_value="owner@example.com"):
            result = material_request_fulfillment.get_permission_query_conditions("owner@example.com")
        self.assertIn("owner = owner@example.com", result)

    @patch.object(material_request_fulfillment.frappe, "get_roles", return_value=["Stock User"])
    def test_stock_permission_query_is_not_owner_scoped(self, _roles: MagicMock) -> None:
        self.assertEqual(
            material_request_fulfillment.get_permission_query_conditions("stock@example.com"), "1=1"
        )

    def test_permission_denies_mutation(self) -> None:
        doc = frappe._dict(material_request="MR-1")
        self.assertFalse(
            material_request_fulfillment.has_permission(cast(Document, doc), "write", "Administrator")
        )

    def test_returning_candidates_use_dispatch_and_expected_return_boundary(self) -> None:
        with (
            patch.object(
                material_request_fulfillment.frappe.db,
                "sql",
                return_value=[frappe._dict(name="AST-1", item_code="FA-1", status="Submitted")],
            ) as sql,
            patch.object(material_request_fulfillment, "_active_asset_names", return_value=set()),
            patch.object(
                material_request_fulfillment.frappe.db,
                "get_value",
                return_value="Submitted",
            ),
            patch.object(material_request_fulfillment, "today", return_value="2026-09-27"),
        ):
            rows = material_request_fulfillment._returning_assets("_Test Company", {"FA-1"}, "_Test Pool", 7)

        self.assertEqual([row["name"] for row in rows], ["AST-1"])
        query = sql.call_args.args[0]
        params = sql.call_args.args[1]
        self.assertIn("out_doc.delivery_status = 'Delivered'", query)
        self.assertIn("ret_row.against_dispatch_transfer", query)
        self.assertEqual(params["location"], "_Test Pool")
        self.assertEqual(params["item_codes"], ("FA-1",))


ASSET_CATEGORY = "_Test TSK512 Equipment Category"
COMPANY = "_Test Company"
NO_POSTING_DOCTYPES = (
    "Asset",
    "Stock Ledger Entry",
    "GL Entry",
    "Stock Entry",
    "Asset Movement",
    "Stock Asset Conversion",
    "Dispatch",
)


@contextmanager
def _inactive_material_request_workflows() -> Iterator[None]:
    workflows = frappe.get_all(
        "Workflow",
        filters={"document_type": "Material Request", "is_active": 1},
        pluck="name",
    )
    for workflow in workflows:
        frappe.db.set_value("Workflow", workflow, "is_active", 0, update_modified=False)
    frappe.clear_cache(doctype="Material Request")
    try:
        yield
    finally:
        for workflow in workflows:
            frappe.db.set_value("Workflow", workflow, "is_active", 1, update_modified=False)
        frappe.clear_cache(doctype="Material Request")


@contextmanager
def _inactive_asset_movement_workflows() -> Iterator[None]:
    workflows = frappe.get_all(
        "Workflow",
        filters={"document_type": "Asset Movement", "is_active": 1},
        pluck="name",
    )
    for workflow in workflows:
        frappe.db.set_value("Workflow", workflow, "is_active", 0, update_modified=False)
    frappe.clear_cache(doctype="Asset Movement")
    try:
        yield
    finally:
        for workflow in workflows:
            frappe.db.set_value("Workflow", workflow, "is_active", 1, update_modified=False)
        frappe.clear_cache(doctype="Asset Movement")


def _invoke_handoff_in_separate_transaction(
    site: str,
    sites_path: str,
    barrier: threading.Barrier,
    material_request: str,
) -> str:
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect(set_admin_as_user=True)
    try:
        request = frappe.get_doc("Material Request", material_request)
        barrier.wait(timeout=10)
        result = material_request_fulfillment.on_submit(request, "on_submit")
        frappe.db.commit()  # nosemgrep - publish the independent handoff transaction
        if not result:
            raise AssertionError("Demo handoff did not return a Fulfillment")
        return result
    finally:
        frappe.destroy()


def _invoke_available_planner_in_separate_transaction(
    site: str,
    sites_path: str,
    barrier: threading.Barrier,
    fulfillment: str,
) -> str:
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect(set_admin_as_user=True)
    try:
        barrier.wait(timeout=10)
        try:
            result = material_request_fulfillment.use_available_assets(fulfillment)
            frappe.db.commit()  # nosemgrep - publish the independent planner transaction
            return cast(str, result["data"])
        except (frappe.ValidationError, frappe.QueryDeadlockError):
            frappe.db.rollback()
            return "conflict"
    finally:
        frappe.destroy()


def _invoke_conversion_handoff_in_separate_transaction(
    site: str,
    sites_path: str,
    barrier: threading.Barrier,
    fulfillment: str,
    allocation: str,
) -> str:
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect(set_admin_as_user=True)
    try:
        barrier.wait(timeout=10)
        result = material_request_fulfillment.create_stock_asset_conversion(
            fulfillment, allocation, WAREHOUSE
        )
        frappe.db.commit()  # nosemgrep - publish the independent handoff transaction
        return cast(str, result["data"])
    finally:
        frappe.destroy()


class TestMaterialRequestFulfillmentIntegration(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        _ensure_test_master_data()

    def _make_submitted_demo_request(self, qty: int = 2) -> tuple[Document, str, str, str]:
        suffix = frappe.generate_hash(length=8)
        stock_item = f"_Test TSK512 MRF Stock {suffix}"
        asset_item = f"_Test TSK512 MRF Asset {suffix}"
        model_code = f"_Test TSK512 MRF Model {suffix}"
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": stock_item,
                "item_name": stock_item,
                "item_group": "All Item Groups",
                "stock_uom": "Nos",
                "is_stock_item": 1,
                "is_fixed_asset": 0,
            }
        ).insert()
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": asset_item,
                "item_name": asset_item,
                "item_group": "All Item Groups",
                "stock_uom": "Nos",
                "is_stock_item": 0,
                "is_fixed_asset": 1,
                "asset_category": ASSET_CATEGORY,
            }
        ).insert()
        frappe.get_doc(
            {
                "doctype": "Equipment Model",
                "model_code": model_code,
                "model_name": model_code,
                "stock_item": stock_item,
                "fixed_asset_item": asset_item,
                "allow_demo": 1,
                "company": COMPANY,
            }
        ).insert()
        request = frappe.get_doc(
            {
                "doctype": "Material Request",
                "company": COMPANY,
                "transaction_date": today(),
                "schedule_date": today(),
                "material_request_type": "Purchase",
                "request_usage": "Customer Demo",
                "purchase_reason": "_Test TSK512 Demo",
                "items": [
                    {
                        "item_code": stock_item,
                        "qty": qty,
                        "uom": "Nos",
                        "stock_uom": "Nos",
                        "warehouse": "_Test Warehouse - _TC",
                        "schedule_date": today(),
                    }
                ],
            }
        ).insert()
        with _inactive_material_request_workflows():
            request.submit()
        return request, stock_item, asset_item, model_code

    def test_demo_asset_outbound_and_return_use_draft_native_movements_and_exact_dispatch(self) -> None:
        request, _stock_item, asset_item, _model_code = self._make_submitted_demo_request(qty=2)
        suffix = frappe.generate_hash(length=8)
        employee = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": f"_Test TSK512 Demo {suffix}",
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": today(),
                "company": COMPANY,
                "status": "Active",
                "employment_type": "Contract",
            }
        ).insert()
        frappe.db.set_value("Material Request", request.name, "responsible_employee", employee.name)
        pool = frappe.get_doc(
            {
                "doctype": "Location",
                "location_name": f"_Test TSK512 Demo Pool {suffix}",
                "is_group": 0,
            }
        ).insert()
        qa_hold = frappe.get_doc(
            {
                "doctype": "Location",
                "location_name": f"_Test TSK512 Demo QA {suffix}",
                "is_group": 0,
            }
        ).insert()
        frappe.db.set_value(
            "Company",
            COMPANY,
            {
                "demo_asset_pool_location": pool.name,
                "return_qa_hold_location": qa_hold.name,
                "demo_return_reuse_window_days": 7,
            },
        )
        assets = []
        for index in range(2):
            asset = frappe.get_doc(
                {
                    "doctype": "Asset",
                    "asset_name": f"_Test TSK512 Demo Asset {suffix} {index}",
                    "asset_category": ASSET_CATEGORY,
                    "item_code": asset_item,
                    "company": COMPANY,
                    "purchase_date": today(),
                    "available_for_use_date": today(),
                    "calculate_depreciation": 0,
                    "net_purchase_amount": 1000,
                    "purchase_amount": 1000,
                    "location": pool.name,
                    "asset_owner": "Company",
                    "asset_type": "Existing Asset",
                    "asset_quantity": 1,
                }
            ).insert()
            asset.submit()
            assets.append(asset)
        first_plan = cast(
            str,
            frappe.db.get_value(
                "Material Request Fulfillment",
                {"material_request": request.name, "status": "Planned"},
                "name",
            ),
        )
        plan = cast(str, material_request_fulfillment.use_available_assets(first_plan)["data"])
        allocations = frappe.get_all(
            "Material Request Fulfillment Allocation",
            filters={"parent": plan},
            fields=["name", "resolved_asset", "lifecycle_state", "asset_reservation"],
            order_by="idx asc",
        )
        self.assertEqual(len(allocations), 2)
        self.assertEqual({row.resolved_asset for row in allocations}, {asset.name for asset in assets})
        self.assertEqual({row.lifecycle_state for row in allocations}, {"Ready"})
        allocation_by_asset = {row.resolved_asset: row for row in allocations}
        sold_asset = assets[0]
        returned_asset = assets[1]
        allocation = allocation_by_asset[sold_asset.name]
        returned_allocation = allocation_by_asset[returned_asset.name]

        outbound_movement = material_request_fulfillment.prepare_demo_outbound_movement(plan)["data"]
        self.assertEqual(
            material_request_fulfillment.prepare_demo_outbound_movement(plan)["data"],
            outbound_movement,
        )
        movement = frappe.get_doc("Asset Movement", outbound_movement)
        self.assertEqual((movement.docstatus, movement.purpose), (0, "Issue"))
        with _inactive_asset_movement_workflows():
            movement.submit()

        outbound = material_request_fulfillment.prepare_demo_outbound_dispatch(
            plan, "_Test Customer Demo Address"
        )["data"]
        self.assertEqual(
            material_request_fulfillment.prepare_demo_outbound_dispatch(plan, "_Test Customer Demo Address")[
                "data"
            ],
            outbound,
        )
        outbound_doc = frappe.get_doc("Dispatch", outbound)
        self.assertEqual(len(outbound_doc.transfers), 2)
        self.assertEqual(
            {row.fulfillment_allocation for row in outbound_doc.transfers},
            {allocation.name, returned_allocation.name},
        )
        outbound_doc.submit()
        self.assertEqual(
            set(
                frappe.get_all(
                    "Material Request Fulfillment Allocation",
                    filters={"parent": plan},
                    pluck="lifecycle_state",
                )
            ),
            {"Dispatched"},
        )
        dispatch_api.confirm_dispatch_delivery(
            outbound_doc.name,
            COMPANY,
            "_Test Receiver",
            "_Test Signature",
        )
        for row in allocations:
            self.assertEqual(
                frappe.db.get_value("Material Request Fulfillment Allocation", row.name, "lifecycle_state"),
                "Delivered",
            )
            self.assertEqual(
                frappe.db.get_value("Demo Asset Reservation", row.asset_reservation, "status"),
                "Consumed",
            )

        sale = sales_invoice.create_demo_sales_invoice(allocation.name, CUSTOMER)["data"]
        self.assertEqual(
            sales_invoice.create_demo_sales_invoice(allocation.name, CUSTOMER)["data"],
            sale,
        )
        sale_doc = frappe.get_doc("Sales Invoice", sale)
        self.assertEqual((sale_doc.docstatus, sale_doc.update_stock), (0, 0))
        self.assertEqual(sale_doc.demo_sale_attempt, 1)
        self.assertEqual(sale_doc.demo_outbound_dispatch, outbound_doc.name)
        self.assertEqual(frappe.db.get_value("Asset", sold_asset.name, "status"), "Submitted")
        sale_doc.due_date = today()
        sale_doc.selling_price_list = PRICE_LIST
        sale_doc.price_list_currency = frappe.get_cached_value("Company", COMPANY, "default_currency")
        sale_doc.plc_conversion_rate = 1
        sale_doc.items[0].rate = 50
        sale_doc.save()
        sale_doc.submit()
        self.assertEqual(frappe.db.get_value("Asset", sold_asset.name, "status"), "Sold")
        sale_ledger = frappe.get_all(
            "GL Entry",
            filters={"voucher_type": "Sales Invoice", "voucher_no": sale_doc.name},
            fields=["debit", "credit"],
        )
        self.assertTrue(sale_ledger)
        self.assertAlmostEqual(
            sum(float(row.debit or 0) for row in sale_ledger),
            sum(float(row.credit or 0) for row in sale_ledger),
            places=2,
        )
        self.assertEqual(
            frappe.db.get_value(
                "Material Request Fulfillment Allocation", allocation.name, "lifecycle_state"
            ),
            "Sold",
        )
        return_movement = material_request_fulfillment.prepare_demo_return_movement(outbound)["data"]
        self.assertEqual(
            material_request_fulfillment.prepare_demo_return_movement(outbound)["data"],
            return_movement,
        )
        movement = frappe.get_doc("Asset Movement", return_movement)
        self.assertEqual((movement.docstatus, movement.purpose), (0, "Receipt"))
        self.assertEqual([row.asset for row in movement.assets], [returned_asset.name])
        with _inactive_asset_movement_workflows():
            movement.submit()
        return_dispatch = material_request_fulfillment.prepare_demo_return_dispatch(outbound)["data"]
        self.assertEqual(
            material_request_fulfillment.prepare_demo_return_dispatch(outbound)["data"],
            return_dispatch,
        )
        return_doc = frappe.get_doc("Dispatch", return_dispatch)
        self.assertEqual(len(return_doc.transfers), 1)
        self.assertEqual(return_doc.transfers[0].asset, returned_asset.name)
        return_doc.submit()
        dispatch_api.confirm_dispatch_delivery(
            return_doc.name,
            COMPANY,
            "_Test Warehouse Receiver",
            "_Test Return Signature",
        )
        self.assertEqual(
            frappe.db.get_value(
                "Material Request Fulfillment Allocation", returned_allocation.name, "lifecycle_state"
            ),
            "Returned",
        )
        self.assertEqual(frappe.db.get_value("Asset", returned_asset.name, "location"), qa_hold.name)
        self.assertEqual(
            frappe.db.get_value(
                "Material Request Fulfillment Allocation", allocation.name, "lifecycle_state"
            ),
            "Sold",
        )

        sale_doc.cancel()
        self.assertNotEqual(frappe.db.get_value("Asset", sold_asset.name, "status"), "Sold")
        restored = frappe.db.get_value(
            "Material Request Fulfillment Allocation",
            allocation.name,
            ["lifecycle_state", "current_sales_invoice", "sale_attempt"],
            as_dict=True,
        )
        self.assertEqual((restored.lifecycle_state, restored.current_sales_invoice), ("Delivered", None))
        self.assertEqual(restored.sale_attempt, 1)
        retry_name = sales_invoice.create_demo_sales_invoice(allocation.name, CUSTOMER)["data"]
        retry = frappe.get_doc("Sales Invoice", retry_name)
        self.assertEqual(retry.demo_sale_attempt, 2)
        self.assertEqual(retry.demo_sale_operation_id, f"demo-sale:{allocation.name}:2")

    def test_submitted_demo_request_creates_one_snapshot_without_posting(self) -> None:
        before_counts = {doctype: frappe.db.count(doctype) for doctype in NO_POSTING_DOCTYPES}
        request, stock_item, asset_item, model_code = self._make_submitted_demo_request()

        plan_name = frappe.db.get_value(
            "Material Request Fulfillment", {"material_request": request.name}, "name"
        )
        self.assertIsNotNone(plan_name)
        plan = frappe.get_doc("Material Request Fulfillment", plan_name)
        self.assertEqual(plan.source_version, 1)
        self.assertEqual(plan.operation_id, f"material-request:{request.name}:submitted")
        self.assertEqual(len(plan.allocations), 1)
        allocation = plan.allocations[0]
        self.assertEqual(
            (
                allocation.item_code,
                allocation.qty,
                allocation.equipment_model,
                allocation.fixed_asset_item,
            ),
            (stock_item, 2, model_code, asset_item),
        )
        self.assertEqual(
            (
                allocation.source_type,
                allocation.selected_source,
                allocation.downstream_doctype,
                allocation.downstream_reference,
            ),
            ("Unplanned", None, None, None),
        )
        rows = frappe.get_all(
            "Material Request Item",
            filters={"parent": request.name},
            fields=["name", "item_code", "item_name", "qty", "uom", "stock_uom"],
            order_by="idx asc",
        )
        rows = [
            {key: row.get(key) for key in ("name", "item_code", "item_name", "qty", "uom", "stock_uom")}
            for row in rows
        ]
        source = {
            "material_request": request.name,
            "company": request.get("company"),
            "request_usage": request.get("request_usage"),
            "items": rows,
        }
        expected_digest = hashlib.sha256(json.dumps(source, sort_keys=True, default=str).encode()).hexdigest()
        self.assertEqual(plan.source_digest, expected_digest)
        self.assertEqual(
            {doctype: frappe.db.count(doctype) for doctype in NO_POSTING_DOCTYPES},
            before_counts,
        )

    def test_available_asset_then_stock_now_appends_revisions_without_posting(self) -> None:
        request, _stock_item, asset_item, _model_code = self._make_submitted_demo_request()
        plan_name = cast(
            str,
            frappe.db.get_value("Material Request Fulfillment", {"material_request": request.name}, "name"),
        )
        location_name = f"_Test TSK512 Pool {frappe.generate_hash(length=8)}"
        location = frappe.get_doc(
            {"doctype": "Location", "location_name": location_name, "is_group": 0}
        ).insert()
        frappe.db.set_value(
            "Company",
            COMPANY,
            {
                "demo_asset_pool_location": location.name,
                "demo_return_reuse_window_days": 7,
            },
        )
        asset = frappe.get_doc(
            {
                "doctype": "Asset",
                "asset_name": f"_Test TSK512 Pool Asset {frappe.generate_hash(length=8)}",
                "asset_category": ASSET_CATEGORY,
                "item_code": asset_item,
                "company": COMPANY,
                "purchase_date": today(),
                "available_for_use_date": today(),
                "calculate_depreciation": 0,
                "net_purchase_amount": 1000,
                "purchase_amount": 1000,
                "location": location.name,
                "asset_owner": "Company",
                "asset_type": "Existing Asset",
                "asset_quantity": 1,
            }
        ).insert()
        asset.submit()
        before_counts = {
            doctype: frappe.db.count(doctype) for doctype in NO_POSTING_DOCTYPES if doctype != "Asset"
        }

        revision_2 = material_request_fulfillment.use_available_assets(plan_name)["data"]
        plan_2 = frappe.get_doc("Material Request Fulfillment", revision_2)
        self.assertEqual(plan_2.plan_revision, 2)
        self.assertEqual(
            frappe.db.get_value("Material Request Fulfillment", plan_name, "status"), "Superseded"
        )
        asset_rows = [row for row in plan_2.allocations if row.source_type == "Existing Asset"]
        self.assertEqual(len(asset_rows), 1)
        self.assertEqual(asset_rows[0].selected_source, asset.name)
        hold = frappe.db.get_value(
            "Demo Asset Reservation",
            {"active_asset_key": asset.name},
            ["name", "status"],
            as_dict=True,
        )
        self.assertEqual(hold.status, "Active")

        revision_3 = material_request_fulfillment.use_stock_now(revision_2)["data"]
        plan_3 = frappe.get_doc("Material Request Fulfillment", revision_3)
        self.assertEqual(plan_3.plan_revision, 3)
        self.assertEqual(
            sorted(row.source_type for row in plan_3.allocations),
            ["Existing Asset", "Stock Conversion"],
        )
        self.assertEqual(frappe.db.get_value("Demo Asset Reservation", hold.name, "status"), "Active")

        revision_4 = material_request_fulfillment.release_asset_reservation(revision_3, hold.name)["data"]
        plan_4 = frappe.get_doc("Material Request Fulfillment", revision_4)
        self.assertEqual(plan_4.plan_revision, 4)
        self.assertEqual(
            sorted(row.source_type for row in plan_4.allocations),
            ["Stock Conversion", "Unplanned"],
        )
        self.assertEqual(frappe.db.get_value("Demo Asset Reservation", hold.name, "status"), "Released")
        self.assertIsNone(frappe.db.get_value("Demo Asset Reservation", hold.name, "active_asset_key"))
        self.assertEqual(
            {doctype: frappe.db.count(doctype) for doctype in before_counts},
            before_counts,
        )

    def test_stock_allocation_creates_one_linked_conversion_and_tracks_lifecycle(self) -> None:
        request, stock_item, _asset_item, _model_code = self._make_submitted_demo_request()
        frappe.db.set_value(
            "Company",
            COMPANY,
            {
                "demo_asset_pool_location": LOCATION,
                "demo_low_value_asset_threshold": 1000,
            },
        )
        plan_name = cast(
            str,
            frappe.db.get_value(
                "Material Request Fulfillment",
                {"material_request": request.name, "status": "Planned"},
                "name",
            ),
        )
        stock_plan_name = cast(
            str,
            material_request_fulfillment.use_stock_now(plan_name)["data"],
        )
        stock_plan = frappe.get_doc("Material Request Fulfillment", stock_plan_name)
        stock_rows = [row for row in stock_plan.allocations if row.source_type == "Stock Conversion"]
        self.assertEqual(len(stock_rows), 2)
        self.assertTrue(all(row.qty == 1 for row in stock_rows))
        allocation = stock_rows[0]
        _make_stock_receipt(stock_item)

        first = material_request_fulfillment.create_stock_asset_conversion(
            stock_plan.name, allocation.name, WAREHOUSE
        )
        second = material_request_fulfillment.create_stock_asset_conversion(
            stock_plan.name, allocation.name, WAREHOUSE
        )
        self.assertEqual(first["data"], second["data"])
        self.assertEqual(
            frappe.db.count(
                "Stock Asset Conversion",
                {"fulfillment_allocation": allocation.name},
            ),
            1,
        )

        conversion = frappe.get_doc("Stock Asset Conversion", first["data"])
        self.assertEqual(conversion.material_request_fulfillment, stock_plan.name)
        self.assertEqual(
            conversion.operation_id, f"fulfillment-allocation:{allocation.name}:stock-asset-conversion"
        )
        conversion.items[0].qty = 2
        with self.assertRaisesRegex(frappe.ValidationError, "source cannot be changed"):
            conversion.save()
        conversion.reload()

        frappe.db.set_value("Equipment Model", allocation.equipment_model, "disabled", 1)
        with self.assertRaisesRegex(frappe.ValidationError, "Equipment Model is no longer eligible"):
            conversion.save()
        frappe.db.set_value("Equipment Model", allocation.equipment_model, "disabled", 0)
        conversion.reload()

        frappe.db.set_value("Company", COMPANY, "demo_asset_pool_location", None)
        with self.assertRaisesRegex(frappe.ValidationError, "active Demo asset pool"):
            conversion.save()
        frappe.db.set_value("Company", COMPANY, "demo_asset_pool_location", LOCATION)
        conversion.reload()

        before_preview = {
            doctype: frappe.db.count(doctype)
            for doctype in ("Stock Ledger Entry", "GL Entry", "Asset", "Journal Entry")
        }
        conversion.accounting_treatment = "Normal Depreciation"
        conversion.save()
        with self.assertRaisesRegex(frappe.ValidationError, "Override Reason"):
            stock_asset_conversion.approve_preview(conversion.name)
        conversion.treatment_override_reason = "Accounts approved normal treatment for this unit."
        conversion.save()
        override_preview = stock_asset_conversion.approve_preview(conversion.name)["data"]["facts"]
        self.assertEqual(override_preview["recommendation"], "Full Depreciation — Single Entry")
        self.assertEqual(override_preview["treatment"], "Normal Depreciation")
        conversion.reload()
        conversion.accounting_treatment = "Full Depreciation — Single Entry"
        conversion.treatment_override_reason = None
        conversion.save()
        self.assertIsNone(conversion.preview_hash)

        preview = stock_asset_conversion.approve_preview(conversion.name)["data"]["facts"]
        conversion.reload()
        self.assertEqual(preview["stock_value"], 125.5)
        self.assertEqual(preview["recommendation"], "Full Depreciation — Single Entry")
        self.assertEqual(
            {doctype: frappe.db.count(doctype) for doctype in before_preview},
            before_preview,
        )

        approved_hash = conversion.preview_hash
        stale_facts = conversion.build_preview_facts(stock_value=999, valuation_rate=999)
        frappe.db.set_value(
            "Stock Asset Conversion",
            conversion.name,
            {
                "preview_stock_value": 999,
                "preview_valuation_rate": 999,
                "preview_hash": stale_facts["preview_hash"],
            },
        )
        conversion.reload()
        frappe.db.savepoint("before_stale_preview_submit")
        with self.assertRaisesRegex(frappe.ValidationError, "Accounts review is required again"):
            conversion.submit()
        frappe.db.rollback(save_point="before_stale_preview_submit")
        self.assertFalse(
            frappe.db.exists(
                "Stock Ledger Entry",
                {"voucher_type": conversion.doctype, "voucher_no": conversion.name},
            )
        )
        frappe.db.set_value(
            "Stock Asset Conversion",
            conversion.name,
            {
                "preview_stock_value": preview["stock_value"],
                "preview_valuation_rate": preview["valuation_rate"],
                "preview_hash": approved_hash,
            },
        )
        conversion.reload()

        conversion.submit()
        self.assertEqual(
            frappe.db.get_value(
                "Material Request Fulfillment Allocation", allocation.name, "conversion_state"
            ),
            "Ready",
        )
        self.assertTrue(conversion.asset)
        actual_gl = frappe.get_all(
            "GL Entry",
            filters={
                "voucher_type": conversion.doctype,
                "voucher_no": conversion.name,
                "is_cancelled": 0,
            },
            fields=["account", "debit", "credit"],
        )
        actual_gl = sorted(actual_gl, key=lambda row: row.account)
        preview_gl = sorted(preview["general_ledger"], key=lambda row: row["account"])
        self.assertEqual(
            [(row.account, row.debit, row.credit) for row in actual_gl],
            [(row["account"], row["debit"], row["credit"]) for row in preview_gl],
        )

        conversion.cancel()
        self.assertEqual(
            frappe.db.get_value(
                "Material Request Fulfillment Allocation", allocation.name, "conversion_state"
            ),
            "Cancelled",
        )

    def test_concurrent_stock_conversion_handoffs_return_one_draft(self) -> None:
        request, stock_item, _asset_item, _model_code = self._make_submitted_demo_request()
        frappe.db.set_value(
            "Company",
            COMPANY,
            {
                "demo_asset_pool_location": LOCATION,
                "demo_low_value_asset_threshold": 1000,
            },
        )
        plan_name = cast(
            str,
            frappe.db.get_value(
                "Material Request Fulfillment",
                {"material_request": request.name, "status": "Planned"},
                "name",
            ),
        )
        stock_plan_name = cast(
            str,
            material_request_fulfillment.use_stock_now(plan_name)["data"],
        )
        allocation = cast(
            str,
            frappe.db.get_value(
                "Material Request Fulfillment Allocation",
                {"parent": stock_plan_name, "source_type": "Stock Conversion"},
                "name",
            ),
        )
        _make_stock_receipt(stock_item)
        frappe.db.commit()  # nosemgrep - worker connections require committed race fixtures

        site = str(frappe.local.site)
        sites_path = str(frappe.local.sites_path)
        barrier = threading.Barrier(2)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        _invoke_conversion_handoff_in_separate_transaction,
                        site,
                        sites_path,
                        barrier,
                        stock_plan_name,
                        allocation,
                    )
                    for _ in range(2)
                ]
                results = [future.result(timeout=20) for future in futures]
            frappe.db.rollback()
            self.assertEqual(results[0], results[1])
            self.assertEqual(
                frappe.db.count(
                    "Stock Asset Conversion",
                    {"fulfillment_allocation": allocation},
                ),
                1,
            )
        finally:
            conversion = frappe.db.get_value(
                "Stock Asset Conversion", {"fulfillment_allocation": allocation}, "name"
            )
            if conversion:
                frappe.delete_doc("Stock Asset Conversion", conversion, force=True, ignore_permissions=True)
            frappe.db.commit()  # nosemgrep - remove the committed race result

    def test_two_fulfillments_cannot_reserve_the_same_asset(self) -> None:
        request_1, stock_item, asset_item, model_code = self._make_submitted_demo_request()
        request_2 = frappe.get_doc(
            {
                "doctype": "Material Request",
                "company": COMPANY,
                "transaction_date": today(),
                "schedule_date": today(),
                "material_request_type": "Purchase",
                "request_usage": "Customer Demo",
                "purchase_reason": "_Test TSK512 Demo Race",
                "items": [
                    {
                        "item_code": stock_item,
                        "qty": 1,
                        "uom": "Nos",
                        "stock_uom": "Nos",
                        "warehouse": "_Test Warehouse - _TC",
                        "schedule_date": today(),
                    }
                ],
            }
        ).insert()
        with _inactive_material_request_workflows():
            request_2.submit()
        plans = frappe.get_all(
            "Material Request Fulfillment",
            filters={"material_request": ("in", [request_1.name, request_2.name]), "status": "Planned"},
            pluck="name",
            order_by="material_request asc",
        )
        self.assertEqual(len(plans), 2)

        location_name = f"_Test TSK512 Race Pool {frappe.generate_hash(length=8)}"
        location = frappe.get_doc(
            {"doctype": "Location", "location_name": location_name, "is_group": 0}
        ).insert()
        previous_settings = frappe.db.get_value(
            "Company",
            COMPANY,
            ["demo_asset_pool_location", "demo_return_reuse_window_days"],
            as_dict=True,
        )
        frappe.db.set_value(
            "Company",
            COMPANY,
            {"demo_asset_pool_location": location.name, "demo_return_reuse_window_days": 7},
        )
        asset = frappe.get_doc(
            {
                "doctype": "Asset",
                "asset_name": f"_Test TSK512 Race Asset {frappe.generate_hash(length=8)}",
                "asset_category": ASSET_CATEGORY,
                "item_code": asset_item,
                "company": COMPANY,
                "purchase_date": today(),
                "available_for_use_date": today(),
                "calculate_depreciation": 0,
                "net_purchase_amount": 1000,
                "purchase_amount": 1000,
                "location": location.name,
                "asset_owner": "Company",
                "asset_type": "Existing Asset",
                "asset_quantity": 1,
            }
        ).insert()
        asset.submit()
        frappe.db.commit()  # nosemgrep - worker connections require committed race fixtures

        site = str(frappe.local.site)
        sites_path = str(frappe.local.sites_path)
        barrier = threading.Barrier(2)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        _invoke_available_planner_in_separate_transaction,
                        site,
                        sites_path,
                        barrier,
                        plan,
                    )
                    for plan in plans
                ]
                results = [future.result(timeout=20) for future in futures]
            frappe.db.rollback()
            self.assertEqual(results.count("conflict"), 1)
            self.assertEqual(
                frappe.db.count(
                    "Demo Asset Reservation",
                    {"active_asset_key": asset.name, "status": "Active"},
                ),
                1,
            )
        finally:
            all_plans = frappe.get_all(
                "Material Request Fulfillment",
                filters={"material_request": ("in", [request_1.name, request_2.name])},
                pluck="name",
            )
            frappe.db.delete("Demo Asset Reservation", {"fulfillment": ("in", all_plans)})
            frappe.db.delete("Material Request Fulfillment Allocation", {"parent": ("in", all_plans)})
            frappe.db.delete("Material Request Fulfillment", {"name": ("in", all_plans)})
            frappe.db.delete("Material Request Item", {"parent": ("in", [request_1.name, request_2.name])})
            frappe.db.delete("Material Request", {"name": ("in", [request_1.name, request_2.name])})
            frappe.db.delete("Asset", {"name": asset.name})
            frappe.db.delete("Equipment Model", {"name": model_code})
            frappe.db.delete("Item", {"name": ("in", [stock_item, asset_item])})
            frappe.db.delete("Location", {"name": location.name})
            frappe.db.set_value("Company", COMPANY, previous_settings)
            frappe.db.commit()  # nosemgrep - remove fixtures committed for concurrent workers

    def test_concurrent_handoffs_return_one_plan(self) -> None:
        request, stock_item, asset_item, model_code = self._make_submitted_demo_request()
        existing_plans = frappe.get_all(
            "Material Request Fulfillment", filters={"material_request": request.name}, pluck="name"
        )
        frappe.db.delete("Material Request Fulfillment Allocation", {"parent": ["in", existing_plans]})
        frappe.db.delete("Material Request Fulfillment", {"name": ["in", existing_plans]})
        frappe.db.commit()  # nosemgrep - worker connections require committed submitted fixtures

        site = str(frappe.local.site)
        sites_path = str(frappe.local.sites_path)
        request_name = cast(str, request.name)
        barrier = threading.Barrier(2)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        _invoke_handoff_in_separate_transaction,
                        site,
                        sites_path,
                        barrier,
                        request_name,
                    )
                    for _ in range(2)
                ]
                results = [future.result(timeout=20) for future in futures]

            frappe.db.rollback()
            self.assertEqual(results[0], results[1])
            self.assertEqual(
                frappe.db.count("Material Request Fulfillment", {"material_request": request.name}),
                1,
            )
        finally:
            plans = frappe.get_all(
                "Material Request Fulfillment", filters={"material_request": request.name}, pluck="name"
            )
            frappe.db.delete("Material Request Fulfillment Allocation", {"parent": ["in", plans]})
            frappe.db.delete("Material Request Fulfillment", {"name": ["in", plans]})
            frappe.db.delete("Material Request Item", {"parent": request.name})
            frappe.db.delete("Material Request", {"name": request.name})
            frappe.db.delete("Equipment Model", {"name": model_code})
            frappe.db.delete("Item", {"name": ["in", [stock_item, asset_item]]})
            frappe.db.commit()  # nosemgrep - remove fixtures committed for concurrent workers
