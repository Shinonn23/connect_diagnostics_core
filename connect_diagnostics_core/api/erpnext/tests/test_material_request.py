# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import material_request
from connect_diagnostics_core.connect_diagnostics_stock.report.outstanding_borrowed_items import (
    outstanding_borrowed_items,
)

MATERIAL_REQUEST_JS = Path(__file__).parents[3] / "public/js/custom/material_request/doctype.js"


class FakeMaterialRequest(frappe._dict):
    def get_doc_before_save(self):
        return self.get("before")

    def save(self) -> None:
        self.saved = True

    def check_permission(self, _permission: str) -> None:
        return None


class FakeRow(frappe._dict):
    def set(self, key: str, value: object) -> None:
        self[key] = value


class TestMaterialRequest(UnitTestCase):
    def test_client_query_preserves_every_native_purpose_result(self) -> None:
        native_results: list[dict[str, Any]] = [
            {"query": "erpnext.controllers.queries.item_query", "filters": {"is_stock_item": 1}},
            {"query": "erpnext.controllers.queries.item_query", "filters": {"is_purchase_item": 1}},
            {
                "query": "erpnext.controllers.queries.item_query",
                "filters": {"include_item_in_manufacturing": 1},
            },
            {
                "query": "erpnext.controllers.queries.item_query",
                "filters": {"is_stock_item": 1, "customer": "CUST-1"},
            },
        ]

        for native_result in native_results:
            with self.subTest(native_result=native_result):
                result = self._run_client_query(native_result, "Employee Borrow", ["DEMO-1"])
                self.assertEqual(result, native_result)

    def test_client_query_adds_only_demo_item_constraint(self) -> None:
        native_result: dict[str, Any] = {
            "query": "erpnext.controllers.queries.item_query",
            "filters": {"is_stock_item": 1},
        }

        result = self._run_client_query(native_result, "Customer Demo", ["DEMO-1", "DEMO-2"])

        self.assertEqual(result["query"], native_result["query"])
        filters = cast(dict[str, Any], result["filters"])
        self.assertEqual(filters["is_stock_item"], 1)
        self.assertEqual(filters["name"], ["in", ["DEMO-1", "DEMO-2"]])

    def _run_client_query(
        self,
        native_result: dict[str, Any],
        request_usage: str,
        eligible_items: list[str],
    ) -> dict[str, Any]:
        script = """
const vm = require("node:vm");
const fs = require("node:fs");
const source = fs.readFileSync(0, "utf8");
const context = { frappe: { ui: { form: { on() {} } } } };
vm.createContext(context);
vm.runInContext(source, context);
const result = vm.runInContext(
    `build_demo_item_query(${process.argv[1]}, ${process.argv[2]}, ${process.argv[3]})`,
    context,
);
process.stdout.write(JSON.stringify(result));
"""
        completed = subprocess.run(
            [
                "node",
                "-e",
                script,
                json.dumps(native_result),
                json.dumps(request_usage),
                json.dumps(eligible_items),
            ],
            input=MATERIAL_REQUEST_JS.read_text(),
            check=True,
            capture_output=True,
            text=True,
        )
        return cast(dict[str, Any], json.loads(completed.stdout))

    @patch.object(material_request, "rounded", side_effect=lambda value, precision: round(value, precision))
    @patch.object(material_request, "get_currency_precision", return_value=2)
    def test_demo_cost_boundary_uses_strictly_greater_than_ten_thousand(
        self, _precision: MagicMock, _rounded: MagicMock
    ) -> None:
        self.assertEqual(material_request._demo_cost_route(9_999.99), "Stock Entry")
        self.assertEqual(material_request._demo_cost_route(10_000.00), "Stock Entry")
        self.assertEqual(material_request._demo_cost_route(10_000.01), "Stock Capitalization")

    @patch.object(material_request, "_validate_asset")
    @patch.object(material_request, "rounded", side_effect=lambda value, precision: round(value, precision))
    @patch.object(material_request, "get_currency_precision", return_value=2)
    def test_demo_allows_mixed_stock_and_asset_routes(
        self, _precision: MagicMock, _rounded: MagicMock, _asset: MagicMock
    ) -> None:
        doc = FakeMaterialRequest(
            request_usage="Customer Demo",
            items=[
                frappe._dict(
                    idx=1,
                    fulfillment_route="Stock Entry",
                    unit_cost_ex_vat=10_000,
                    cost_source="Stock Ledger Entry SLE-1",
                ),
                frappe._dict(
                    idx=2,
                    fulfillment_route="Existing Asset",
                    allocated_asset="AST-1",
                ),
                frappe._dict(
                    idx=3,
                    fulfillment_route="Stock Capitalization",
                    unit_cost_ex_vat=10_000.01,
                    cost_source="Purchase Receipt PR-1",
                ),
            ],
        )

        material_request._validate_routes(cast(Document, doc))

    def test_demo_rejects_purchase_route(self) -> None:
        doc = FakeMaterialRequest(
            request_usage="Customer Demo",
            items=[frappe._dict(idx=1, fulfillment_route="Purchase")],
        )

        with self.assertRaises(frappe.ValidationError):
            material_request._validate_routes(cast(Document, doc))

    @patch.object(material_request, "_validate_responsible_employee")
    def test_employee_borrow_requires_responsible_employee_and_return_date(
        self, _employee: MagicMock
    ) -> None:
        doc = FakeMaterialRequest(request_usage="Employee Borrow")

        with self.assertRaises(frappe.ValidationError):
            material_request.validate_submit_for_approval(cast(Document, doc))

    @patch.object(material_request.frappe.db, "get_value", return_value="_Test Company")
    @patch.object(material_request, "now", return_value="2026-09-07 09:00:00")
    @patch.object(
        material_request,
        "get_previous_sle",
        return_value=frappe._dict(name="SLE-1", valuation_rate=10_000.005),
    )
    @patch.object(material_request, "rounded", return_value=10_000.00)
    @patch.object(material_request, "get_currency_precision", return_value=2)
    def test_stock_ledger_cost_is_snapshotted_per_stock_unit(
        self,
        _precision: MagicMock,
        _rounded: MagicMock,
        _sle: MagicMock,
        _now: MagicMock,
        _warehouse: MagicMock,
    ) -> None:
        doc = FakeMaterialRequest(company="_Test Company", transaction_date="2026-09-01")
        row = FakeRow(idx=1, item_code="ITEM-1", from_warehouse="Stores - TC")

        cost, source = material_request._resolve_unit_cost(cast(Document, doc), cast(Document, row))

        self.assertEqual(cost, 10_000.00)
        self.assertIn("SLE-1", source)

    @patch.object(material_request.frappe.db, "get_value", return_value="_Test Company")
    @patch.object(material_request.frappe.db, "sql")
    @patch.object(material_request, "now", return_value="2026-09-07 09:00:00")
    @patch.object(
        material_request,
        "get_previous_sle",
        return_value=frappe._dict(
            name="SLE-PR-1",
            valuation_rate=12_000,
            actual_qty=2,
            voucher_type="Purchase Receipt",
            voucher_no="PR-1",
            voucher_detail_no="PRI-1",
        ),
    )
    @patch.object(material_request, "rounded", side_effect=lambda value, precision: round(value, precision))
    @patch.object(material_request, "get_currency_precision", return_value=2)
    def test_latest_purchase_receipt_uses_net_cost_instead_of_warehouse_valuation(
        self,
        _precision: MagicMock,
        _rounded: MagicMock,
        _sle: MagicMock,
        _now: MagicMock,
        sql: MagicMock,
        _warehouse: MagicMock,
    ) -> None:
        sql.return_value = [
            frappe._dict(
                row_name="PRI-1",
                purchase_receipt="PR-1",
                base_net_amount=20_000,
                stock_qty=2,
                posting_date="2026-09-01",
            )
        ]
        doc = FakeMaterialRequest(company="_Test Company", transaction_date="2026-09-01")
        row = FakeRow(idx=1, item_code="ITEM-1", from_warehouse="Stores - TC")

        cost, source = material_request._resolve_unit_cost(cast(Document, doc), cast(Document, row))

        self.assertEqual(cost, 10_000.00)
        self.assertIn("net cost excluding VAT per stock UOM", source)
        self.assertIn("PR-1", source)

    @patch.object(material_request.frappe.db, "get_value", return_value="_Test Company")
    @patch.object(material_request.frappe.db, "sql")
    @patch.object(material_request, "now", return_value="2026-09-07 09:00:00")
    @patch.object(material_request, "get_previous_sle", return_value={})
    @patch.object(material_request, "rounded", side_effect=lambda value, precision: round(value, precision))
    @patch.object(material_request, "get_currency_precision", return_value=2)
    def test_purchase_receipt_cost_uses_net_amount_per_stock_unit_excluding_vat(
        self,
        _precision: MagicMock,
        _rounded: MagicMock,
        _sle: MagicMock,
        _now: MagicMock,
        sql: MagicMock,
        _warehouse: MagicMock,
    ) -> None:
        sql.return_value = [
            frappe._dict(
                row_name="PRI-1",
                purchase_receipt="PR-1",
                base_net_amount=20_000,
                stock_qty=2,
                posting_date="2026-09-01",
            )
        ]
        doc = FakeMaterialRequest(company="_Test Company", transaction_date="2026-09-01")
        row = FakeRow(idx=1, item_code="ITEM-1", from_warehouse="Stores - TC")

        cost, source = material_request._resolve_unit_cost(cast(Document, doc), cast(Document, row))

        self.assertEqual(cost, 10_000.00)
        self.assertIn("net cost excluding VAT per stock UOM", source)

    @patch.object(material_request, "_has_fulfillment_role", return_value=True)
    @patch.object(material_request, "_row_has_active_downstream", return_value=False)
    @patch.object(material_request, "_resolve_unit_cost", return_value=(10_000.01, "source"))
    @patch.object(material_request.frappe, "has_permission", return_value=True)
    @patch.object(material_request.frappe.db, "get_value", return_value="MR-1")
    def test_refresh_unit_cost_clears_a_stale_demo_route(
        self,
        _get_value: MagicMock,
        _permission: MagicMock,
        _resolve: MagicMock,
        _downstream: MagicMock,
        _role: MagicMock,
    ) -> None:
        row = FakeRow(
            name="MRI-1",
            idx=1,
            fulfillment_route="Stock Entry",
            allocated_asset=None,
        )
        doc = FakeMaterialRequest(
            name="MR-1",
            docstatus=1,
            request_usage="Customer Demo",
            items=[row],
        )
        with patch.object(material_request.frappe, "get_doc", return_value=doc):
            result = material_request.refresh_unit_cost("MR-1")

        self.assertIsNone(row.fulfillment_route)
        self.assertEqual(row.unit_cost_ex_vat, 10_000.01)
        self.assertTrue(doc.saved)
        self.assertEqual(result["data"][0]["material_request_item"], "MRI-1")

    @patch.object(material_request, "_has_fulfillment_role", return_value=False)
    def test_requester_cannot_set_accounts_controlled_route(self, _role: MagicMock) -> None:
        doc = FakeMaterialRequest(items=[FakeRow(name="NEW-ROW", fulfillment_route="Stock Entry")])

        with self.assertRaises(frappe.PermissionError):
            material_request._validate_controlled_field_access(cast(Document, doc))

    @patch.object(material_request, "_has_fulfillment_role", return_value=False)
    def test_requester_cannot_clear_accounts_controlled_route(self, _role: MagicMock) -> None:
        previous = FakeRow(name="MRI-1", fulfillment_route="Stock Entry")
        doc = FakeMaterialRequest(
            before=FakeMaterialRequest(items=[previous]),
            items=[FakeRow(name="MRI-1", fulfillment_route=None)],
        )

        with self.assertRaises(frappe.PermissionError):
            material_request._validate_controlled_field_access(cast(Document, doc))

    @patch.object(material_request, "_row_has_active_downstream", return_value=True)
    def test_route_change_is_locked_after_downstream_document(self, _downstream: MagicMock) -> None:
        previous = FakeRow(name="MRI-1", fulfillment_route="Stock Entry")
        doc = FakeMaterialRequest(
            name="MR-1",
            before=FakeMaterialRequest(items=[previous]),
            items=[FakeRow(name="MRI-1", idx=1, fulfillment_route="Stock Capitalization")],
        )

        with self.assertRaises(frappe.ValidationError):
            material_request._validate_downstream_lock(cast(Document, doc))

    @patch.object(material_request, "_validate_routes")
    @patch.object(material_request, "_validate_demo_item_eligibility")
    @patch.object(material_request, "_validate_downstream_lock")
    @patch.object(material_request, "_validate_controlled_field_access")
    def test_validate_hook_runs_all_route_guards(
        self, access: MagicMock, lock: MagicMock, demo: MagicMock, routes: MagicMock
    ) -> None:
        doc = FakeMaterialRequest()

        material_request.validate(cast(Document, doc))

        access.assert_called_once_with(doc)
        lock.assert_called_once_with(doc)
        demo.assert_called_once_with(doc)
        routes.assert_called_once_with(doc)

    @patch.object(material_request, "get_eligible_demo_stock_items", return_value=["DEMO-ITEM"])
    def test_demo_item_validation_accepts_only_configured_items(self, eligible: MagicMock) -> None:
        doc = FakeMaterialRequest(
            request_usage="Customer Demo",
            company="_Test Company",
            items=[FakeRow(idx=1, item_code="DEMO-ITEM")],
        )

        material_request._validate_demo_item_eligibility(cast(Document, doc))

        eligible.assert_called_once_with("_Test Company")

    @patch.object(material_request, "get_eligible_demo_stock_items", return_value=[])
    def test_demo_item_validation_rejects_an_api_bypass(self, _eligible: MagicMock) -> None:
        doc = FakeMaterialRequest(
            request_usage="Customer Demo",
            company="_Test Company",
            items=[FakeRow(idx=1, item_code="UNMAPPED")],
        )

        with self.assertRaisesRegex(frappe.ValidationError, "not enabled for Customer Demo"):
            material_request._validate_demo_item_eligibility(cast(Document, doc))

    @patch.object(material_request, "get_eligible_demo_stock_items")
    def test_non_demo_usage_does_not_query_equipment_models(self, eligible: MagicMock) -> None:
        doc = FakeMaterialRequest(
            request_usage="Employee Borrow",
            company="_Test Company",
            items=[FakeRow(idx=1, item_code="ANY-ITEM")],
        )

        material_request._validate_demo_item_eligibility(cast(Document, doc))

        eligible.assert_not_called()

    @patch.object(material_request, "_validate_customer_address")
    @patch.object(material_request, "get_eligible_demo_stock_items", return_value=[])
    def test_approval_rechecks_stale_demo_mapping(self, _eligible: MagicMock, _address: MagicMock) -> None:
        doc = FakeMaterialRequest(
            request_usage="Customer Demo",
            company="_Test Company",
            destination_type="Customer",
            destination_customer="_Test Customer",
            destination_address="_Test Address",
            responsible_employee="_Test Employee",
            expected_return_date="2026-12-01",
            items=[FakeRow(idx=1, item_code="NO-LONGER-ELIGIBLE")],
        )

        with self.assertRaisesRegex(frappe.ValidationError, "not enabled for Customer Demo"):
            material_request.validate_submit_for_approval(cast(Document, doc))

    @patch.object(material_request.frappe, "has_permission", side_effect=[True, False, True])
    @patch.object(material_request.frappe, "get_doc")
    @patch.object(material_request, "get_eligible_demo_stock_items", return_value=["DEMO-ITEM"])
    def test_demo_eligible_endpoint_checks_company_and_returns_envelope(
        self,
        eligible: MagicMock,
        get_doc: MagicMock,
        _permission: MagicMock,
    ) -> None:
        get_doc.return_value = FakeMaterialRequest(name="_Test Company", is_group=0)

        result = material_request.get_demo_eligible_items("_Test Company")

        self.assertEqual(result["data"], ["DEMO-ITEM"])
        self.assertTrue(result["message"])
        eligible.assert_called_once_with("_Test Company")

    @patch.object(material_request.frappe, "has_permission", side_effect=[True, False])
    @patch.object(
        material_request.frappe,
        "get_doc",
        return_value=FakeMaterialRequest(name="All Companies", is_group=1),
    )
    def test_demo_eligible_endpoint_rejects_group_company(
        self, _get_doc: MagicMock, _permission: MagicMock
    ) -> None:
        with self.assertRaisesRegex(frappe.ValidationError, "non-group Company"):
            material_request.get_demo_eligible_items("All Companies")

    @patch.object(material_request.frappe, "has_permission", side_effect=[False, False])
    def test_demo_eligible_endpoint_requires_material_request_access(self, _permission: MagicMock) -> None:
        with self.assertRaises(frappe.PermissionError):
            material_request.get_demo_eligible_items("_Test Company")

    @patch.object(material_request.frappe, "has_permission", return_value=True)
    @patch.object(material_request, "get_eligible_demo_stock_items")
    def test_demo_eligible_endpoint_fails_closed_without_company(
        self, eligible: MagicMock, _permission: MagicMock
    ) -> None:
        result = material_request.get_demo_eligible_items()

        self.assertEqual(result["data"], [])
        eligible.assert_not_called()

    def test_internal_permanent_use_requires_a_warehouse_or_asset_location(self) -> None:
        doc = FakeMaterialRequest(
            request_usage="Internal Permanent Use",
            items=[frappe._dict(idx=1, fulfillment_route=None)],
        )

        with self.assertRaises(frappe.ValidationError):
            material_request._validate_internal_destination(cast(Document, doc))

    @patch.object(material_request.frappe, "get_all", return_value=["AST-ALLOCATED"])
    @patch.object(
        material_request.frappe.db,
        "get_value",
        return_value=frappe._dict(company="_Test Company", docstatus=1),
    )
    def test_asset_movement_requires_allocation_on_the_linked_request(
        self, _request: MagicMock, _allocated_assets: MagicMock
    ) -> None:
        movement = frappe._dict(
            company="_Test Company",
            material_request="MR-1",
            assets=[frappe._dict(idx=1, asset="AST-OTHER")],
        )

        with self.assertRaises(frappe.ValidationError):
            material_request.validate_asset_movement(cast(Document, movement))

    def test_demo_asset_movement_requires_every_allocation_exactly_once(self) -> None:
        movement = frappe._dict(
            company="_Test Company",
            material_request="MR-DEMO",
            purpose="Issue",
            reference_doctype="Material Request Fulfillment",
            reference_name="MRF-1",
            assets=[frappe._dict(idx=1, asset="AST-1", source_location="POOL")],
        )
        allocations = [
            frappe._dict(name="ALLOC-1", resolved_asset="AST-1"),
            frappe._dict(name="ALLOC-2", resolved_asset="AST-2"),
        ]
        with (
            patch.object(material_request.frappe.db, "get_value", return_value="MRF-1"),
            patch.object(material_request.frappe, "get_all", return_value=allocations),
            self.assertRaisesRegex(frappe.ValidationError, "every active allocation Asset"),
        ):
            material_request._validate_demo_asset_movement(cast(Document, movement), "MR-DEMO")

    @patch.object(material_request.frappe, "get_all", return_value=["MR-1"])
    def test_quality_inspection_inherits_material_request_from_stock_entry(
        self, _material_requests: MagicMock
    ) -> None:
        inspection = FakeRow(
            reference_type="Stock Entry",
            reference_name="SE-RETURN",
            child_row_reference="SED-1",
            item_code="ITEM-1",
        )

        material_request.validate_quality_inspection(cast(Document, inspection))

        self.assertEqual(inspection.material_request, "MR-1")

    def test_dashboard_adds_fulfillment_connections(self) -> None:
        data = material_request.get_dashboard_data({"transactions": []})

        items = data["transactions"][0]["items"]
        self.assertIn("Dispatch", items)
        self.assertIn("Borrowed Asset Return Inspection", items)
        self.assertIn("Quality Inspection", items)

    @patch.object(outstanding_borrowed_items, "get_outstanding_rows", return_value=[])
    @patch.object(material_request, "_has_downstream_document", return_value=True)
    @patch.object(material_request, "_validate_routes")
    @patch.object(material_request.frappe.db, "exists", return_value=True)
    def test_returnable_request_can_close_after_settlement_or_write_off_without_qa_acceptance(
        self,
        _exists: MagicMock,
        _routes: MagicMock,
        _downstream: MagicMock,
        _outstanding: MagicMock,
    ) -> None:
        for resolution_type in ("Settlement", "Write-off"):
            doc = FakeMaterialRequest(
                name="MR-1",
                company="_Test Company",
                request_usage="Customer Demo",
                items=[frappe._dict(idx=1, fulfillment_route="Stock Entry")],
                resolution_type=resolution_type,
            )

            material_request.validate_close(cast(Document, doc))

    @patch.object(material_request.frappe.db, "exists", return_value=False)
    @patch.object(material_request.frappe, "get_all")
    @patch.object(material_request.frappe.db, "get_value")
    def test_failed_outbound_recovery_end_transit_returns_each_row_to_source(
        self, get_value: MagicMock, get_all: MagicMock, _exists: MagicMock
    ) -> None:
        def values(doctype: str, _name: str, fields: object, **_kwargs: object) -> object:
            if doctype == "Stock Entry":
                return frappe._dict(
                    docstatus=1,
                    company="_Test Company",
                    add_to_transit=1,
                    return_dispatch_transfer=None,
                    to_warehouse="Transit - TC",
                )
            if doctype == "Company":
                return "Transit - TC"
            if doctype == "Dispatch Transfer":
                return frappe._dict(parent="DSP-OUT", material_request="MR-1")
            if doctype == "Dispatch":
                return frappe._dict(
                    dispatch_type="Outbound", delivery_status="Failed", material_request="MR-1"
                )
            return None

        get_value.side_effect = values
        get_all.return_value = [
            frappe._dict(
                name="SED-1", material_request_item="MRI-1", transfer_qty=2, s_warehouse="Stores - TC"
            )
        ]
        doc = FakeMaterialRequest(
            company="_Test Company",
            outgoing_stock_entry="SE-RECOVERY",
            return_dispatch_transfer="ROW-OUT",
            to_warehouse="Stores - TC",
            items=[
                FakeRow(
                    ste_detail="SED-1",
                    transfer_qty=2,
                    s_warehouse="Transit - TC",
                    t_warehouse="Stores - TC",
                )
            ],
        )

        material_request._validate_end_transit_entry(doc, "MR-1")
