# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import material_request


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
    @patch.object(material_request, "_validate_downstream_lock")
    @patch.object(material_request, "_validate_controlled_field_access")
    def test_validate_hook_runs_all_route_guards(
        self, access: MagicMock, lock: MagicMock, routes: MagicMock
    ) -> None:
        doc = FakeMaterialRequest()

        material_request.validate(cast(Document, doc))

        access.assert_called_once_with(doc)
        lock.assert_called_once_with(doc)
        routes.assert_called_once_with(doc)

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
