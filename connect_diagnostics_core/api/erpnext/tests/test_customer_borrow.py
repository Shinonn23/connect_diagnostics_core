# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast
from unittest.mock import patch

import frappe
from erpnext.stock.doctype.item.test_item import make_item
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import add_days, today

from connect_diagnostics_core.api.erpnext import customer_borrow as borrow


class FakeDocument(dict[str, Any]):
    def __init__(self, **values: Any) -> None:
        super().__init__(values)
        self.previous: FakeDocument | None = None

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def set(self, name: str, value: Any) -> None:
        self[name] = value

    def get_doc_before_save(self) -> FakeDocument | None:
        return self.previous

    def is_new(self) -> bool:
        return not bool(self.get("name"))

    def append(self, name: str, row: dict[str, Any]) -> None:
        self.setdefault(name, []).append(FakeDocument(**row))

    def set_missing_values(self) -> None:
        pass

    def as_dict(self) -> dict[str, Any]:
        return dict(self)


def doc(**values: Any) -> Document:
    return cast(Document, FakeDocument(**values))


def request() -> Document:
    return doc(
        doctype="Material Request",
        name="MR-BORROW-1",
        material_request_type="Customer Borrow",
        company="TEST",
        docstatus=1,
        status="Submitted",
        borrow_customer="CUST-1",
        borrow_employee="EMP-1",
        borrow_warehouse="Borrow-EMP-1",
        set_from_warehouse="Stores",
        set_warehouse="Borrow-EMP-1",
        items=[
            doc(
                name="MRI-1",
                item_code="ITEM-1",
                qty=2,
                stock_qty=12,
                uom="Box",
                stock_uom="Each",
                conversion_factor=6,
                from_warehouse="Stores",
                warehouse="Borrow-EMP-1",
            )
        ],
    )


def entry(*, transfer_qty: float = 6, qty: float = 1) -> Document:
    return doc(
        doctype="Stock Entry",
        name="SE-1",
        company="TEST",
        purpose="Material Transfer",
        stock_entry_type="Material Transfer",
        borrow_material_request="MR-BORROW-1",
        to_warehouse="Borrow-EMP-1",
        add_to_transit=0,
        outgoing_stock_entry=None,
        items=[
            doc(
                name="SED-1",
                item_code="ITEM-1",
                qty=qty,
                uom="Box",
                stock_uom="Each",
                conversion_factor=6,
                transfer_qty=transfer_qty,
                s_warehouse="Stores",
                t_warehouse="Borrow-EMP-1",
                material_request="MR-BORROW-1",
                material_request_item="MRI-1",
            )
        ],
    )


class TestBorrowWarehouse(UnitTestCase):
    def test_existing_mapping_reuses_only_unique_valid_warehouse(self) -> None:
        with (
            patch.object(borrow.frappe.db, "get_value", return_value="locked"),
            patch.object(
                borrow, "_employee", return_value=frappe._dict(customer_borrow_warehouse="Borrow-EMP-1")
            ),
            patch.object(borrow, "_warehouse") as warehouse,
            patch.object(borrow.frappe.db, "exists", return_value=None),
        ):
            self.assertEqual(borrow._ensure_warehouse("EMP-1", "TEST", may_create=False), "Borrow-EMP-1")
            warehouse.assert_called_once_with("Borrow-EMP-1", "TEST", group=False)

    def test_unmapped_employee_requires_explicit_creation(self) -> None:
        with (
            patch.object(borrow.frappe.db, "get_value", return_value="locked"),
            patch.object(borrow, "_employee", return_value=frappe._dict(customer_borrow_warehouse=None)),
            self.assertRaises(frappe.ValidationError),
        ):
            borrow._ensure_warehouse("EMP-1", "TEST", may_create=False)

    def test_api_checks_request_permission_before_employee_lookup(self) -> None:
        with (
            patch.object(borrow.frappe.db, "get_value", return_value=None),
            patch.object(borrow.frappe, "has_permission", side_effect=frappe.PermissionError),
            patch.object(borrow, "_employee") as employee,
            self.assertRaises(frappe.PermissionError),
        ):
            borrow.ensure_employee_borrow_warehouse("EMP-1", "TEST")
            employee.assert_not_called()

    def test_api_returns_existing_mapping_without_create_permission(self) -> None:
        with (
            patch.object(borrow.frappe, "has_permission", return_value=True),
            patch.object(borrow, "_employee"),
            patch.object(borrow, "_ensure_warehouse", return_value="Borrow-EMP-1") as ensure,
        ):
            result = borrow.ensure_employee_borrow_warehouse("EMP-1", "TEST")
            self.assertEqual(result["data"], {"warehouse": "Borrow-EMP-1"})
            ensure.assert_called_once_with("EMP-1", "TEST", may_create=True)

    def test_employee_mapping_cannot_be_changed_by_form_save(self) -> None:
        employee = doc(name="EMP-1", company="TEST", customer_borrow_warehouse="Other")
        with (
            patch.object(borrow.frappe.db, "get_value", return_value=None),
            patch.object(
                borrow.frappe.db,
                "get_value",
                return_value=frappe._dict(company="TEST", customer_borrow_warehouse="Borrow-EMP-1"),
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            borrow.validate_employee(employee, "validate")

    def test_employee_company_cannot_change_after_assignment(self) -> None:
        employee = doc(name="EMP-1", company="OTHER", customer_borrow_warehouse="Borrow-EMP-1")
        with (
            patch.object(
                borrow.frappe.db,
                "get_value",
                return_value=frappe._dict(company="TEST", customer_borrow_warehouse="Borrow-EMP-1"),
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            borrow.validate_employee(employee, "validate")


class TestBorrowMaterialRequest(UnitTestCase):
    def test_before_validate_sets_only_missing_targets(self) -> None:
        mr = doc(
            material_request_type="Customer Borrow",
            borrow_warehouse="Borrow-EMP-1",
            items=[doc(warehouse=None), doc(warehouse="Forged")],
        )
        borrow.before_validate_material_request(mr, "before_validate")
        self.assertEqual(mr.get("set_warehouse"), "Borrow-EMP-1")
        self.assertEqual([row.get("warehouse") for row in mr.get("items")], ["Borrow-EMP-1", "Forged"])

    def test_validates_stock_items_source_and_target(self) -> None:
        mr = request()
        with (
            patch.object(borrow.frappe.db, "exists", return_value=True),
            patch.object(borrow.frappe, "has_permission", return_value=True),
            patch.object(
                borrow, "_employee", return_value=frappe._dict(customer_borrow_warehouse="Borrow-EMP-1")
            ),
            patch.object(borrow, "_warehouse"),
            patch.object(
                borrow.frappe,
                "get_all",
                return_value=[frappe._dict(name="ITEM-1", is_stock_item=1, stock_uom="Each")],
            ),
        ):
            borrow.validate_material_request(mr, "validate")
            mr.get("items")[0].set("warehouse", "Other")
            with self.assertRaises(frappe.ValidationError):
                borrow.validate_material_request(mr, "validate")

    def test_submitted_snapshot_blocks_borrower_change(self) -> None:
        mr = cast(FakeDocument, request())
        old = cast(FakeDocument, request())
        mr.previous = old
        mr.set("borrow_customer", "CUST-2")
        with self.assertRaises(frappe.ValidationError):
            borrow.before_update_after_submit_material_request(mr, "before_update_after_submit")

    def test_on_submit_initializes_status(self) -> None:
        with patch.object(borrow.frappe.db, "set_value") as set_value:
            borrow.on_submit_material_request(request(), "on_submit")
            set_value.assert_called_once_with(
                "Material Request",
                "MR-BORROW-1",
                "borrow_fulfillment_status",
                "Not Sent",
                update_modified=False,
            )

    def test_cancel_rejects_submitted_outbound(self) -> None:
        with (
            patch.object(borrow.frappe.db, "get_value"),
            patch.object(borrow.frappe.db, "exists", return_value="SE-1"),
            self.assertRaises(frappe.ValidationError),
        ):
            borrow.before_cancel_material_request(request(), "before_cancel")


class TestBorrowStockEntry(UnitTestCase):
    def test_linked_request_permission_is_checked_before_type_lookup(self) -> None:
        with (
            patch.object(borrow.frappe, "has_permission", side_effect=frappe.PermissionError),
            patch.object(
                borrow.frappe,
                "get_all",
                return_value=[frappe._dict(name="MR-BORROW-1", material_request_type="Customer Borrow")],
            ),
            patch.object(borrow.frappe, "get_doc") as get_doc,
            self.assertRaises(frappe.PermissionError),
        ):
            borrow.validate_stock_entry(entry(), "validate")
            get_doc.assert_not_called()

    def test_non_borrow_request_links_do_not_add_permission_requirements(self) -> None:
        ordinary = entry()
        ordinary.set("borrow_material_request", None)
        ordinary.get("items")[0].set("material_request", "MR-TRANSFER-1")
        with (
            patch.object(
                borrow.frappe,
                "get_all",
                return_value=[frappe._dict(name="MR-TRANSFER-1", material_request_type="Material Transfer")],
            ),
            patch.object(borrow.frappe, "has_permission") as permission,
        ):
            borrow.validate_stock_entry(ordinary, "validate")
            permission.assert_not_called()

    def test_rejects_forged_target_and_request_rows(self) -> None:
        se = entry()
        with patch.object(
            borrow, "_employee", return_value=frappe._dict(customer_borrow_warehouse="Borrow-EMP-1")
        ):
            borrow._validate_stock_entry_rows(se, request())
            se.get("items")[0].set("t_warehouse", "Other")
            with self.assertRaises(frappe.ValidationError):
                borrow._validate_stock_entry_rows(se, request())

    def test_review_freezes_borrow_header_and_rows(self) -> None:
        se = cast(FakeDocument, entry())
        old = cast(FakeDocument, entry())
        old.set("workflow_state", "Stock Transfer Pending Approval")
        se.previous = old
        se.get("items")[0].set("material_request_item", "MRI-FORGED")
        with (
            patch.object(borrow, "_request_for_stock_entry", return_value=request()),
            self.assertRaises(frappe.ValidationError),
        ):
            borrow.validate_stock_entry(se, "validate")

    def test_before_submit_caps_aggregate_in_stock_uom(self) -> None:
        se = entry(transfer_qty=6)
        with (
            patch.object(borrow, "_request_for_stock_entry", return_value=request()),
            patch.object(
                borrow.frappe.db,
                "get_value",
                return_value=frappe._dict(
                    docstatus=1, status="Submitted", material_request_type="Customer Borrow"
                ),
            ),
            patch.object(borrow.frappe, "get_doc", return_value=request()),
            patch.object(borrow, "_validate_stock_entry_rows"),
            patch.object(borrow, "_submitted_quantities", return_value={"MRI-1": 7}),
            self.assertRaises(frappe.ValidationError),
        ):
            borrow.before_submit_stock_entry(se, "before_submit")

    def test_status_uses_submitted_quantities(self) -> None:
        with (
            patch.object(
                borrow.frappe.db,
                "get_value",
                return_value=frappe._dict(docstatus=1, material_request_type="Customer Borrow"),
            ),
            patch.object(borrow.frappe, "get_doc", return_value=request()),
            patch.object(borrow, "_submitted_quantities", return_value={"MRI-1": 6}),
            patch.object(borrow.frappe.db, "set_value") as set_value,
        ):
            borrow.on_submit_stock_entry(entry(), "on_submit")
            self.assertEqual(set_value.call_args.args[2], "Partially Sent")

    def test_cancel_excludes_cancelled_entry_from_reconciliation(self) -> None:
        with (
            patch.object(
                borrow.frappe.db,
                "get_value",
                return_value=frappe._dict(docstatus=1, material_request_type="Customer Borrow"),
            ),
            patch.object(borrow.frappe, "get_doc", return_value=request()),
            patch.object(borrow, "_submitted_quantities", return_value={}) as quantities,
            patch.object(borrow.frappe.db, "set_value") as set_value,
        ):
            borrow.before_cancel_stock_entry(entry(), "before_cancel")
            borrow.on_cancel_stock_entry(entry(), "on_cancel")
            quantities.assert_called_once_with("MR-BORROW-1", exclude_entry="SE-1", for_update=True)
            self.assertEqual(set_value.call_args.args[2], "Not Sent")

    def test_draft_api_requires_read_permission(self) -> None:
        with (
            patch.object(borrow.frappe, "has_permission", side_effect=frappe.PermissionError),
            patch.object(borrow.frappe, "get_doc") as get_doc,
            self.assertRaises(frappe.PermissionError),
        ):
            borrow.get_customer_borrow_stock_entry_draft("MR-BORROW-1")
            get_doc.assert_not_called()

    def test_draft_api_uses_remaining_stock_qty_and_request_links(self) -> None:
        stock_entry = FakeDocument(doctype="Stock Entry", items=[])
        with (
            patch.object(borrow.frappe, "has_permission", return_value=True),
            patch.object(borrow.frappe, "get_doc", return_value=request()),
            patch.object(
                borrow, "_employee", return_value=frappe._dict(customer_borrow_warehouse="Borrow-EMP-1")
            ),
            patch.object(borrow, "_submitted_quantities", return_value={"MRI-1": 6}),
            patch.object(borrow.frappe, "new_doc", return_value=stock_entry),
        ):
            result = borrow.get_customer_borrow_stock_entry_draft("MR-BORROW-1")
        self.assertEqual(result["data"]["purpose"], "Material Transfer")
        self.assertEqual(result["data"]["items"][0]["qty"], 1)
        self.assertEqual(result["data"]["items"][0]["transfer_qty"], 6)
        self.assertEqual(result["data"]["items"][0]["material_request_item"], "MRI-1")


class TestCustomerBorrowDocuments(IntegrationTestCase):
    """Exercise actual ERPNext documents and DB state on the dedicated test site."""

    def setUp(self) -> None:
        super().setUp()
        self.company = "_Test Company"
        self.source = "_Test Warehouse - _TC"
        suffix = frappe.generate_hash(length=10)
        self.employee = frappe.get_doc(
            {
                "doctype": "Employee",
                "naming_series": "EMP-",
                "first_name": f"_Test Borrow {suffix}",
                "company": self.company,
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
                "gender": "Female",
                "status": "Active",
            }
        ).insert()
        self.customer = frappe.get_doc(
            {"doctype": "Customer", "customer_name": f"_Test Borrow {suffix}", "customer_type": "Individual"}
        ).insert()
        self.item = make_item(
            f"_Test Borrow Item {suffix}", properties={"is_stock_item": 1, "stock_uom": "Nos"}
        )
        self.target = borrow.ensure_employee_borrow_warehouse(self.employee.name, self.company)["data"][
            "warehouse"
        ]

    def _request(self) -> Document:
        request_doc = frappe.get_doc(
            {
                "doctype": "Material Request",
                "material_request_type": "Customer Borrow",
                "company": self.company,
                "transaction_date": today(),
                "schedule_date": add_days(today(), 7),
                "borrow_customer": self.customer.name,
                "borrow_employee": self.employee.name,
                "borrow_warehouse": self.target,
                "set_from_warehouse": self.source,
                "set_warehouse": self.target,
                "items": [
                    {
                        "item_code": self.item.name,
                        "item_name": self.item.item_name,
                        "qty": 12,
                        "stock_qty": 12,
                        "uom": "Nos",
                        "stock_uom": "Nos",
                        "conversion_factor": 1,
                        "from_warehouse": self.source,
                        "warehouse": self.target,
                        "schedule_date": add_days(today(), 7),
                    }
                ],
            }
        ).insert()
        request_doc.submit()
        return request_doc

    def test_native_request_and_draft_preserve_borrow_identity(self) -> None:
        self.assertEqual(
            borrow.ensure_employee_borrow_warehouse(self.employee.name, self.company)["data"]["warehouse"],
            self.target,
        )
        self.assertEqual(
            frappe.db.get_value("Employee", self.employee.name, "customer_borrow_warehouse"), self.target
        )
        request_doc = self._request()
        self.assertEqual(request_doc.docstatus, 1)
        self.assertEqual(
            frappe.db.get_value("Material Request", request_doc.name, "borrow_fulfillment_status"), "Not Sent"
        )
        stock_entry = frappe.get_doc(borrow.get_customer_borrow_stock_entry_draft(request_doc.name)["data"])
        self.assertEqual(stock_entry.borrow_material_request, request_doc.name)
        self.assertEqual(stock_entry.items[0].material_request_item, request_doc.items[0].name)
        self.assertEqual(stock_entry.items[0].transfer_qty, 12)
        self.assertEqual(stock_entry.items[0].t_warehouse, self.target)
        stock_entry.insert()
        self.assertEqual(stock_entry.docstatus, 0)
        with self.assertRaises(frappe.ValidationError):
            stock_entry.submit()  # Native Stock Transfer approval is required.

    def test_native_draft_rejects_wrong_target_and_excess_stock_qty(self) -> None:
        request_doc = self._request()
        stock_entry = frappe.get_doc(borrow.get_customer_borrow_stock_entry_draft(request_doc.name)["data"])
        stock_entry.items[0].t_warehouse = self.source
        with self.assertRaises(frappe.ValidationError):
            stock_entry.insert()

        stock_entry = frappe.get_doc(borrow.get_customer_borrow_stock_entry_draft(request_doc.name)["data"])
        stock_entry.items[0].qty = 13
        stock_entry.items[0].transfer_qty = 13
        stock_entry.insert()
        with self.assertRaises(frappe.ValidationError):
            borrow.before_submit_stock_entry(stock_entry, "before_submit")

    def test_warehouse_name_collision_requires_owner_resolution(self) -> None:
        suffix = frappe.generate_hash(length=10)
        other = frappe.get_doc(
            {
                "doctype": "Employee",
                "naming_series": "EMP-",
                "first_name": f"_Test Borrow {suffix}",
                "company": self.company,
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
                "gender": "Female",
                "status": "Active",
            }
        ).insert()
        frappe.db.set_value("Employee", other.name, "customer_borrow_warehouse", self.target)
        with self.assertRaises(frappe.ValidationError):
            borrow.ensure_employee_borrow_warehouse(self.employee.name, self.company)
