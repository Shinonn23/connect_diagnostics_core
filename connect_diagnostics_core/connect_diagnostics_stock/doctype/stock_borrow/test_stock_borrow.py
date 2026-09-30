# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from erpnext.stock.utils import get_stock_balance
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import add_days, today

from connect_diagnostics_core.api.erpnext import stock_borrow
from connect_diagnostics_core.connect_diagnostics_stock.doctype.stock_borrow.stock_borrow import (
    StockBorrow,
    derive_status,
)

COMPANY = "_Test Company"
ITEM = "_Test Item"
SOURCE_WAREHOUSE = "_Test Warehouse - _TC"
BORROW_WAREHOUSE = "_Test Warehouse 1 - _TC"
RETURN_HOLD_WAREHOUSE = "Finished Goods - _TC"


class TestStockBorrow(UnitTestCase):
    def test_direct_insert_is_rejected(self) -> None:
        doc = MagicMock(flags={})

        with self.assertRaises(frappe.ValidationError):
            StockBorrow.before_insert(doc)

    def test_direct_identity_mutation_is_rejected(self) -> None:
        doc = MagicMock()
        doc.items = [
            frappe._dict(
                material_request_item="MRI-1",
                item_code=ITEM,
                uom="_Test UOM",
                requested_qty=1,
                issued_qty=0,
                returned_qty=0,
                pending_issue_qty=1,
                outstanding_qty=0,
            )
        ]
        doc.flags = frappe._dict()
        doc.is_new.return_value = False
        doc.get.side_effect = lambda fieldname: {"material_request": "MR-CHANGED"}.get(fieldname)

        with (
            patch.object(
                frappe.db,
                "get_value",
                return_value=frappe._dict(material_request="MR-ORIGINAL"),
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            StockBorrow.validate(doc)

    def test_status_distinguishes_partial_issue_from_return(self) -> None:
        self.assertEqual(
            derive_status(issued=2, returned=0, pending_issue=2, outstanding=2),
            "Partially Issued",
        )
        self.assertEqual(
            derive_status(issued=4, returned=1, pending_issue=0, outstanding=3),
            "Partially Returned",
        )
        self.assertEqual(
            derive_status(issued=4, returned=4, pending_issue=0, outstanding=0),
            "Returned",
        )


class TestStockBorrowIntegration(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self._disable_workflows("Material Request")
        self._disable_workflows("Stock Entry")

        frappe.db.set_value(
            "Item",
            ITEM,
            {"allow_borrow": 1, "has_serial_no": 0, "has_batch_no": 0},
            update_modified=False,
        )
        frappe.db.set_value(
            "Company",
            COMPANY,
            "return_qa_hold_warehouse",
            RETURN_HOLD_WAREHOUSE,
            update_modified=False,
        )
        employment_type = frappe.db.get_value("Employment Type", {}, "name")
        department = frappe.db.get_value("Department", {"company": COMPANY}, "name")
        self.employee = (
            frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": "_Test Borrow Custodian",
                    "company": COMPANY,
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2026-01-01",
                    "department": department,
                    "gender": "Female",
                    "status": "Active",
                    "employment_type": employment_type,
                    "borrow_warehouse": BORROW_WAREHOUSE,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _disable_workflows(self, doctype: str) -> None:
        for name in frappe.get_all(
            "Workflow",
            filters={"document_type": doctype, "is_active": 1},
            pluck="name",
        ):
            frappe.db.set_value("Workflow", name, "is_active", 0, update_modified=False)
        frappe.clear_cache(doctype=doctype)

    def _make_request(self, qty: float = 4) -> Document:
        request = frappe.get_doc(
            {
                "doctype": "Material Request",
                "material_request_type": "Material Issue",
                "company": COMPANY,
                "purchase_reason": "Borrow prototype integration test",
                "request_usage": "Employee Borrow",
                "destination_type": "Employee",
                "responsible_employee": self.employee,
                "expected_return_date": add_days(today(), 7),
                "items": [
                    {
                        "item_code": ITEM,
                        "qty": qty,
                        "uom": "_Test UOM",
                        "conversion_factor": 1,
                        "warehouse": SOURCE_WAREHOUSE,
                        "schedule_date": today(),
                        "fulfillment_route": "Stock Entry",
                    }
                ],
            }
        )
        request.insert()
        request.submit()
        return request

    def _submit_transfer(self, name: str) -> Document:
        entry = frappe.get_doc("Stock Entry", name)
        entry.workflow_state = "Stock Transfer Submitted"
        entry.submit()
        return entry

    def test_native_partial_issue_return_and_cancellation_lifecycle(self) -> None:
        make_stock_entry(
            item_code=ITEM,
            qty=5,
            company=COMPANY,
            to_warehouse=SOURCE_WAREHOUSE,
            rate=100,
        )
        request = self._make_request()

        first = stock_borrow.create_stock_borrow(request.name)
        second = stock_borrow.create_stock_borrow(request.name)
        self.assertEqual(first["message"], second["message"])
        self.assertEqual(frappe.db.count("Stock Borrow", {"material_request": request.name}), 1)

        borrow = frappe.get_doc("Stock Borrow", first["message"])
        borrow_item = borrow.items[0]
        outbound_result = stock_borrow.prepare_outbound(
            borrow.name,
            [{"stock_borrow_item": borrow_item.name, "qty": 2}],
            SOURCE_WAREHOUSE,
            BORROW_WAREHOUSE,
        )
        outbound = self._submit_transfer(outbound_result["data"]["name"])

        borrow.reload()
        self.assertEqual(borrow.issued_qty, 2)
        self.assertEqual(borrow.pending_issue_qty, 2)
        self.assertEqual(borrow.outstanding_qty, 2)
        self.assertEqual(borrow.status, "Partially Issued")
        self.assertEqual(get_stock_balance(ITEM, BORROW_WAREHOUSE), 2)

        with self.assertRaises(frappe.ValidationError):
            stock_borrow.prepare_outbound(
                borrow.name,
                [{"stock_borrow_item": borrow_item.name, "qty": 3}],
                SOURCE_WAREHOUSE,
                BORROW_WAREHOUSE,
            )

        tampered_result = stock_borrow.prepare_outbound(
            borrow.name,
            [{"stock_borrow_item": borrow_item.name, "qty": 1}],
            SOURCE_WAREHOUSE,
            BORROW_WAREHOUSE,
        )
        tampered = frappe.get_doc("Stock Entry", tampered_result["data"]["name"])
        tampered.items[0].t_warehouse = RETURN_HOLD_WAREHOUSE
        tampered.workflow_state = "Stock Transfer Submitted"
        with self.assertRaises(frappe.ValidationError):
            tampered.submit()

        return_result = stock_borrow.prepare_exact_return(
            borrow.name,
            [{"stock_borrow_item": borrow_item.name, "qty": 1}],
            BORROW_WAREHOUSE,
            RETURN_HOLD_WAREHOUSE,
        )
        return_entry = frappe.get_doc("Stock Entry", return_result["data"]["name"])
        return_entry.workflow_state = "Stock Transfer Submitted"
        with self.assertRaises(frappe.ValidationError):
            return_entry.submit()

        stock_borrow.confirm_physical_receipt(return_entry.name)
        return_entry.reload()
        return_entry.workflow_state = "Stock Transfer Submitted"
        return_entry.submit()

        borrow.reload()
        self.assertEqual(borrow.returned_qty, 1)
        self.assertEqual(borrow.outstanding_qty, 1)
        self.assertEqual(get_stock_balance(ITEM, BORROW_WAREHOUSE), 1)
        self.assertEqual(get_stock_balance(ITEM, RETURN_HOLD_WAREHOUSE), 1)

        return_entry.cancel()
        borrow.reload()
        self.assertEqual(borrow.returned_qty, 0)
        self.assertEqual(borrow.outstanding_qty, 2)
        self.assertEqual(get_stock_balance(ITEM, RETURN_HOLD_WAREHOUSE), 0)

        outbound.cancel()
        borrow.reload()
        self.assertEqual(borrow.issued_qty, 0)
        self.assertEqual(borrow.pending_issue_qty, 4)
        self.assertEqual(borrow.outstanding_qty, 0)
        self.assertEqual(borrow.status, "Pending Issue")
