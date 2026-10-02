# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Sales generation group, authority and one-use target proof checks."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import auto_invoice_generation as generation
from connect_diagnostics_core.api.erpnext import sales_order_workflow as order_workflow
from connect_diagnostics_core.connect_diagnostics_core.doctype.sales_invoice_generation.sales_invoice_generation import (
    SalesInvoiceGeneration,
)


class TestSalesAutoInvoiceGeneration(UnitTestCase):
    def test_unsupported_accounting_controls_stop_automatic_invoice(self) -> None:
        invoice = Document({"doctype": "Sales Invoice"})
        for field, value in (
            ("allocate_advances_automatically", 1),
            ("redeem_loyalty_points", 1),
            ("loyalty_amount", 10),
            ("is_cash_or_non_trade_discount", 1),
            ("additional_discount_account", "DISCOUNT - CO"),
        ):
            invoice.set(field, value)
            with self.assertRaises(frappe.ValidationError):
                generation._reject_unsupported_invoice_features(invoice)
            invoice.set(field, None)
        invoice.set("payments", [{"amount": 10}])
        with self.assertRaises(frappe.ValidationError):
            generation._reject_unsupported_invoice_features(invoice)

    def test_delivery_invoice_header_dimension_comes_from_signed_sales_order(self) -> None:
        so = Document(
            {
                "doctype": "Sales Order",
                "name": "SO-1",
                "department": "SIGNED-DEPARTMENT",
                "billing_receivable_account": "AR - CO",
                "items": [{"name": "SO-ROW", "item_code": "ITEM-1", "qty": 1, "conversion_factor": 1}],
            }
        )
        trusted = Document(
            {
                "doctype": "Sales Invoice",
                "items": [{"so_detail": "SO-ROW", "item_code": "ITEM-1", "qty": 1}],
            }
        )
        target = Document(
            {
                "doctype": "Sales Invoice",
                "department": "UNAPPROVED-DEPARTMENT",
                "items": [
                    {
                        "so_detail": "SO-ROW",
                        "item_code": "ITEM-1",
                        "qty": 1,
                        "delivery_note": "DN-1",
                        "dn_detail": "DN-ROW",
                    }
                ],
            }
        )
        selected = [{"sales_order_item": "SO-ROW"}]
        with (
            patch.object(generation, "from_sales_order", return_value=trusted),
            patch.object(generation, "billing_dimension_fields", return_value=("department",)),
            patch.object(generation, "_invoice_payload", return_value={"items": []}),
            patch.object(Document, "run_method"),
        ):
            generation._trusted_delivery_invoice(target, so, selected)
        self.assertEqual(target.get("department"), "SIGNED-DEPARTMENT")
        self.assertEqual(target.get("debit_to"), "AR - CO")
        self.assertEqual(target.get("items")[0].get("dn_detail"), "DN-ROW")

    def test_delivery_invoice_projection_discards_dn_billing_values(self) -> None:
        dimensions = ("department",)
        so_header: dict[str, Any] = {
            field: f"SIGNED:{field}" for field in generation.SO_APPROVED_INVOICE_HEADER_FIELDS
        }
        so_header.update({"name": "SO-1", "billing_receivable_account": "AR - CO", "department": "SO-D"})
        so_item: dict[str, Any] = {
            field: f"SIGNED:{field}" for field in generation.SO_APPROVED_INVOICE_ITEM_FIELDS
        }
        so_item.update(
            {
                "name": "SO-ROW",
                "item_code": "ITEM-1",
                "uom": "Each",
                "stock_uom": "Each",
                "conversion_factor": 1,
                "rate": 125,
                "price_list_rate": 125,
                "discount_percentage": 0,
                "discount_amount": 0,
                "income_account": "Sales - CO",
                "department": "SO-ITEM-D",
            }
        )
        so_tax: dict[str, Any] = {field: f"SIGNED:TAX:{field}" for field in generation.INVOICE_TAX_FIELDS}
        so_tax.update(
            {
                "rate": 7,
                "tax_amount": 10,
                "total": 150,
                "included_in_print_rate": 0,
                "included_in_paid_amount": 0,
                "base_tax_amount": 10,
                "tax_amount_after_discount_amount": 10,
                "base_tax_amount_after_discount_amount": 10,
                "base_total": 150,
            }
        )
        so_taxes = [so_tax]
        so = Document(
            {
                "doctype": "Sales Order",
                **so_header,
                "items": [so_item],
                "taxes": so_taxes,
            }
        )
        trusted_header: dict[str, Any] = {
            field: f"MAPPED:{field}" for field in generation.INVOICE_HEADER_FIELDS
        }
        trusted_header.update(
            {
                "is_pos": 0,
                "update_stock": 0,
                "paid_amount": 0,
                "change_amount": 0,
                "write_off_amount": 0,
                "department": "MAPPED-D",
            }
        )
        trusted_item: dict[str, Any] = {field: f"MAPPED:{field}" for field in generation.INVOICE_ITEM_FIELDS}
        trusted_item.update(
            {
                "so_detail": "SO-ROW",
                "item_code": "ITEM-1",
                "qty": 1,
                "conversion_factor": 1,
                "stock_qty": 1,
                "warehouse": "SO-WH",
                "department": "MAPPED-ITEM-D",
            }
        )
        trusted_item["department"] = "SO-ITEM-D"
        trusted = Document(
            {
                "doctype": "Sales Invoice",
                **trusted_header,
                "items": [trusted_item],
                "taxes": [{field: f"MAPPED:TAX:{field}" for field in generation.INVOICE_TAX_FIELDS}],
                "payment_schedule": [
                    {
                        **{field: f"MAPPED:SCHEDULE:{field}" for field in generation.INVOICE_SCHEDULE_FIELDS},
                        "due_date": "2026-10-02",
                        "invoice_portion": 100,
                        "payment_amount": 250,
                    }
                ],
            }
        )
        tampered_item: dict[str, Any] = {
            field: f"DN:TAMPERED:{field}" for field in generation.INVOICE_ITEM_FIELDS
        }
        tampered_item.update(
            {
                "so_detail": "SO-ROW",
                "item_code": "ITEM-1",
                "qty": 2,
                "stock_qty": 2,
                "conversion_factor": 1,
                "delivery_note": "DN-1",
                "dn_detail": "DN-ROW",
                "warehouse": "DN-WH",
                "department": "DN-ITEM-D",
            }
        )
        tampered_header: dict[str, Any] = {
            field: f"DN:TAMPERED:{field}" for field in generation.INVOICE_HEADER_FIELDS
        }
        tampered_header.update(
            {
                "is_pos": 0,
                "update_stock": 0,
                "paid_amount": 0,
                "change_amount": 0,
                "write_off_amount": 0,
                "department": "DN-D",
            }
        )
        target = Document(
            {
                "doctype": "Sales Invoice",
                **tampered_header,
                "items": [tampered_item],
                "taxes": [
                    {
                        **{field: f"DN:TAMPERED:TAX:{field}" for field in generation.INVOICE_TAX_FIELDS},
                        "rate": 99,
                        "tax_amount": 99,
                        "total": 999,
                        "included_in_print_rate": 0,
                        "included_in_paid_amount": 0,
                        "base_tax_amount": 99,
                        "tax_amount_after_discount_amount": 99,
                        "base_tax_amount_after_discount_amount": 99,
                        "base_total": 999,
                    }
                ],
                "payment_schedule": [
                    {
                        **{
                            field: f"DN:TAMPERED:SCHEDULE:{field}"
                            for field in generation.INVOICE_SCHEDULE_FIELDS
                        },
                        "due_date": "2026-10-02",
                        "invoice_portion": 50,
                        "payment_amount": 100,
                    }
                ],
            }
        )

        def comparable_payload(doc: Document) -> dict[str, object]:
            payload = generation._invoice_payload(doc)
            payload["items"].sort(key=lambda row: str(row.get("so_detail") or ""))
            for row in payload["items"]:
                for field in ("delivery_note", "dn_detail", "warehouse"):
                    row.pop(field, None)
            return payload

        with (
            patch.object(generation, "from_sales_order", return_value=trusted) as mapper,
            patch.object(generation, "billing_dimension_fields", return_value=dimensions),
            patch.object(Document, "run_method"),
        ):
            generation._trusted_delivery_invoice(
                target,
                so,
                [{"sales_order_item": "SO-ROW"}],
            )

        mapper.assert_called_once_with(
            "SO-1", ignore_permissions=True, args={"filtered_children": ["SO-ROW"]}
        )
        self.assertEqual(comparable_payload(target), comparable_payload(trusted))
        self.assertEqual(target.get("items")[0].get("delivery_note"), "DN-1")
        self.assertEqual(target.get("items")[0].get("dn_detail"), "DN-ROW")
        self.assertEqual(target.get("items")[0].get("warehouse"), "DN-WH")
        self.assertEqual(target.get("items")[0].get("qty"), 2)

        target.get("items")[0].set("rate", "POST-COMPOSITION-TAMPER")
        self.assertNotEqual(comparable_payload(target), comparable_payload(trusted))

    def test_allocation_failure_exposes_fixed_recovery_status(self) -> None:
        run = frappe._dict(
            {
                "name": "RUN-1",
                "generation_status": "Queued",
                "target_sales_invoice": None,
            }
        )
        with (
            patch.object(generation, "_lock_authority_then_run", return_value=run),
            patch.object(generation, "_generate", side_effect=generation._AllocationRequiredError()),
            patch.object(generation.frappe.db, "rollback") as rollback,
            patch.object(generation, "_mark") as mark,
        ):
            self.assertIsNone(generation.process_sales_invoice_generation("RUN-1"))
        rollback.assert_called_once_with()
        mark.assert_called_once_with(
            run,
            "Failed",
            error=generation.ALLOCATION_REQUIRED_STATUS,
            failure_code="Allocation Required",
        )

    def test_numeric_seals_are_stable_across_native_number_types(self) -> None:
        self.assertEqual(generation._scalar(1), generation._scalar(1.0))
        self.assertEqual(generation._scalar(1), generation._scalar(Decimal("1.000")))
        self.assertEqual(order_workflow._billing_value(1), order_workflow._billing_value(1.0))

    def test_partial_group_fails_closed_for_native_fixed_charges_and_discounts(self) -> None:
        source = Document(
            {
                "doctype": "Sales Order",
                "name": "SO-1",
                "items": [
                    {"name": "SERVICE", "item_code": "SERVICE-ITEM", "qty": 1},
                    {"name": "STOCK", "item_code": "STOCK-ITEM", "qty": 1},
                ],
                "taxes": [{"charge_type": "Actual", "tax_amount": 100}],
            }
        )
        selected = [{"source_row": "SERVICE", "sales_order_item": "SERVICE", "authorized_qty": 1}]
        with self.assertRaises(frappe.ValidationError):
            generation._reject_unallocated_fixed_amounts(source, source, selected)
        source.set("taxes", [])
        source.set("discount_amount", 25)
        with self.assertRaises(frappe.ValidationError):
            generation._reject_unallocated_fixed_amounts(source, source, selected)
        source.set("discount_amount", 0)
        source.set("additional_discount_percentage", 10)
        source.set("discount_amount", 20)
        generation._reject_unallocated_fixed_amounts(source, source, selected)
        source.set("additional_discount_percentage", 0)
        source.set("discount_amount", 0)
        source.set("loyalty_amount", 5)
        with self.assertRaises(frappe.ValidationError):
            generation._reject_unallocated_fixed_amounts(source, source, selected)
        source.set("loyalty_amount", 0)
        source.set("payment_schedule", [{"invoice_portion": 0, "payment_amount": 100}])
        with self.assertRaises(frappe.ValidationError):
            generation._reject_unallocated_fixed_amounts(source, source, selected)
        source.set("payment_schedule", [{"invoice_portion": 100, "payment_amount": 100}])
        generation._reject_unallocated_fixed_amounts(source, source, selected)
        source.set("taxes", [{"charge_type": "Actual", "tax_amount": 100}])
        with patch.object(
            generation,
            "_item_identities",
            return_value={"SERVICE-ITEM": {"is_stock_item": 0}, "STOCK-ITEM": {"is_stock_item": 1}},
        ):
            self.assertTrue(
                generation._reject_unallocated_fixed_amounts(
                    source,
                    source,
                    [
                        {"source_row": "SERVICE", "sales_order_item": "SERVICE", "authorized_qty": 1},
                        {"source_row": "STOCK", "sales_order_item": "STOCK", "authorized_qty": 1},
                    ],
                )
            )

    def test_each_whole_one_row_delivery_is_partial_to_signed_order(self) -> None:
        order = Document(
            {
                "doctype": "Sales Order",
                "name": "SO-STOCK",
                "items": [{"name": "SO-ROW", "item_code": "STOCK", "qty": 2}],
                "taxes": [{"charge_type": "Actual", "tax_amount": 100}],
                "discount_amount": 50,
            }
        )
        for dn_name in ("DN-1", "DN-2"):
            delivery = Document(
                {
                    "doctype": "Delivery Note",
                    "name": dn_name,
                    "items": [{"name": f"{dn_name}-ROW", "item_code": "STOCK", "qty": 1}],
                    "taxes": [{"charge_type": "Actual", "tax_amount": 100}],
                    "discount_amount": 50,
                }
            )
            selected = [
                {
                    "source_row": f"{dn_name}-ROW",
                    "sales_order_item": "SO-ROW",
                    "authorized_qty": 1,
                }
            ]
            with (
                patch.object(generation, "_item_identities", return_value={"STOCK": {"is_fixed_asset": 0}}),
                self.assertRaises(generation._AllocationRequiredError),
            ):
                generation._reject_unallocated_fixed_amounts(delivery, order, selected)

    def test_document_fixed_charge_spanning_asset_row_has_no_ordinary_invoice_pool(self) -> None:
        order = Document(
            {
                "doctype": "Sales Order",
                "items": [
                    {"name": "S", "item_code": "SERVICE", "qty": 1},
                    {"name": "A", "item_code": "ASSET", "qty": 1, "asset": "ASSET-1"},
                ],
                "taxes": [{"charge_type": "Actual", "tax_amount": 100}],
            }
        )
        selected = [
            {"source_row": row.name, "sales_order_item": row.name, "authorized_qty": 1}
            for row in order.get("items") or []
        ]
        with (
            patch.object(
                generation,
                "_item_identities",
                return_value={"SERVICE": {"is_stock_item": 0}, "ASSET": {"is_fixed_asset": 1}},
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            generation._reject_unallocated_fixed_amounts(order, order, selected)

    def test_legacy_sales_order_digest_ignores_new_billing_authority_fields(self) -> None:
        order = Document({"doctype": "Sales Order", "customer": "CUST-1", "items": []})
        with patch.object(order_workflow, "_credit_inputs", return_value={}):
            original = order_workflow.approval_digest(order)
            for field in order_workflow._BILLING_AUTHORITY_FIELDS:
                order.set(field, "")
            self.assertEqual(original, order_workflow.approval_digest(order))
            order.set("billing_authority_digest", "later-seal")
            self.assertEqual(original, order_workflow.approval_digest(order))

    def test_billing_seal_changes_on_current_item_classification(self) -> None:
        order = Document(
            {
                "doctype": "Sales Order",
                "customer": "CUST-1",
                "company": "CO-1",
                "approval_approver_user": "finance@example.invalid",
                "authorized_signature": "signed",
                "items": [{"name": "ROW-1", "item_code": "ITEM-1", "qty": 1, "rate": 10}],
            }
        )
        identity = frappe._dict(
            {"name": "ITEM-1", "is_stock_item": 0, "is_fixed_asset": 0, "item_group": "Services"}
        )
        with (
            patch.object(order_workflow, "billing_dimension_fields", return_value=()),
            patch.object(order_workflow.frappe, "get_all", return_value=[identity]),
        ):
            service = order_workflow.billing_authority_digest(order)
            identity["is_fixed_asset"] = 1
            fixed = order_workflow.billing_authority_digest(order)
        self.assertNotEqual(service, fixed)

    def test_finance_approval_seals_without_queuing_invoice(self) -> None:
        order = Document(
            {
                "doctype": "Sales Order",
                "workflow_state": "Sales Order Approved",
                "approval_digest": "review",
                "approval_maker_user": "maker",
                "approval_reviewer_user": "reviewer",
                "checked_signature": "reviewed",
                "authorized_by": "EMP-FINANCE",
                "authorized_at": "2026-10-01 10:00:00",
                "authorized_signature": "signed",
                "items": [],
            }
        )
        with (
            patch.object(order_workflow, "approval_digest", return_value="review"),
            patch.object(order_workflow, "_employee_signature", return_value=("EMP-FINANCE", "signed")),
            patch.object(order_workflow, "billing_authority_digest", return_value="billing-digest"),
            patch.object(order_workflow, "get_party_account", return_value="AR - CO"),
            patch.object(order_workflow, "now_datetime", return_value="2026-10-01 10:00:00"),
            patch.object(order_workflow.frappe, "session", user="finance@example.invalid"),
            patch.object(generation, "_queue") as queue,
        ):
            order_workflow.capture_sales_order_final_approval(order)
        self.assertEqual(order.get("billing_authority_digest"), "billing-digest")
        self.assertEqual(order.get("billing_authorized_by"), "finance@example.invalid")
        self.assertEqual(order.get("billing_receivable_account"), "AR - CO")
        queue.assert_not_called()

    def test_service_and_stock_groups_exclude_fixed_assets_and_asset_links(self) -> None:
        rows = [
            Document({"doctype": "Sales Order Item", "name": "SERVICE", "item_code": "S"}),
            Document({"doctype": "Sales Order Item", "name": "STOCK", "item_code": "K"}),
            Document({"doctype": "Sales Order Item", "name": "FIXED", "item_code": "F"}),
            Document({"doctype": "Sales Order Item", "name": "ASSET", "item_code": "S", "asset": "A-1"}),
        ]
        identities = {
            "S": {"is_stock_item": 0, "is_fixed_asset": 0},
            "K": {"is_stock_item": 1, "is_fixed_asset": 0},
            "F": {"is_stock_item": 0, "is_fixed_asset": 1},
        }
        self.assertEqual(
            [
                row.name
                for row in rows
                if generation._ordinary(row, identities[str(row.get("item_code"))], stock=False)
            ],
            ["SERVICE"],
        )
        self.assertEqual(
            [
                row.name
                for row in rows
                if generation._ordinary(row, identities[str(row.get("item_code"))], stock=True)
            ],
            ["STOCK"],
        )

    def test_group_key_is_stable_for_replay_and_changes_for_distinct_delivery(self) -> None:
        so = Document(
            {
                "doctype": "Sales Order",
                "name": "SO-1",
                "company": "CO",
                "customer": "CU",
                "billing_authority_digest": "sealed",
            }
        )
        item = Document(
            {
                "doctype": "Delivery Note Item",
                "name": "DNROW-1",
                "item_code": "K",
                "qty": 2,
                "so_detail": "SOROW-1",
            }
        )
        first = Document(
            {
                "doctype": "Delivery Note",
                "name": "DN-1",
                "docstatus": 1,
                "company": "CO",
                "customer": "CU",
                "items": [item],
            }
        )
        second = Document(
            {
                "doctype": "Delivery Note",
                "name": "DN-2",
                "docstatus": 1,
                "company": "CO",
                "customer": "CU",
                "items": [item],
            }
        )
        with (
            patch.object(generation, "billing_dimension_fields", return_value=()),
            patch.object(generation.frappe, "session", user="sales@example.invalid"),
        ):
            a = generation._group(first, so, "DN Stock", [item])
            b = generation._group(first, so, "DN Stock", [item])
            c = generation._group(second, so, "DN Stock", [item])
        assert a is not None and b is not None and c is not None
        self.assertEqual(a["group_key"], b["group_key"])
        self.assertNotEqual(a["group_key"], c["group_key"])

    def test_target_stage_is_object_bound_and_one_use(self) -> None:
        target = Document({"doctype": "Sales Invoice", "items": []})
        other = Document({"doctype": "Sales Invoice", "items": []})
        run = cast(
            SalesInvoiceGeneration,
            frappe._dict(
                {
                    "doctype": generation.RUN_DOCTYPE,
                    "name": "RUN-1",
                    "source_doctype": "Sales Order",
                    "source_name": "SO-1",
                    "billing_authority_digest": "sealed",
                    "source_digest": "group",
                }
            ),
        )
        with patch.object(generation, "billing_dimension_fields", return_value=()):
            digest = generation._digest(generation._invoice_payload(target))
            for field, value in {
                "connect_invoice_generation_run": run.name,
                "connect_generation_payload_digest": digest,
                "connect_invoice_source_doctype": "Sales Order",
                "connect_invoice_source_name": "SO-1",
                "connect_billing_authority_digest": "sealed",
                "connect_source_group_digest": "group",
                "connect_generated_by_actor": "sales@example.invalid",
                "connect_generated_at": "2026-10-01 10:00:00",
            }.items():
                target.set(field, value)
            other.set("connect_invoice_generation_run", run.name)
            other.set("connect_generation_payload_digest", digest)
            with patch.object(generation.frappe, "session", user="sales@example.invalid"):
                with generation._target_stage(target, run, "insert", digest):
                    self.assertTrue(target.flags.ignore_permissions)
                    nonce = target.flags.get("_connect_generation_nonce")
                    self.assertTrue(nonce)
                    with self.assertRaises(frappe.PermissionError):
                        generation._require_stage(other, "insert")
                    target.flags._connect_generation_nonce = "forged"
                    with self.assertRaises(frappe.PermissionError):
                        generation._require_stage(target, "insert")
                    target.flags._connect_generation_nonce = nonce
                    generation._require_stage(target, "insert", consume=True)
                    target.set("connect_source_group_digest", "tampered")
                    with self.assertRaises(frappe.PermissionError):
                        generation._require_stage(target, "insert", allow_consumed=True)
                    with self.assertRaises(frappe.PermissionError):
                        generation._require_stage(target, "insert", consume=True)
        self.assertFalse(bool(target.flags.ignore_permissions))
        self.assertFalse(target.flags.get("_connect_generation_nonce"))

    def test_target_prior_permission_flag_restored_after_mapper_failure(self) -> None:
        target = Document({"doctype": "Sales Invoice"})
        target.flags.ignore_permissions = "prior"
        run = cast(SalesInvoiceGeneration, frappe._dict({"doctype": generation.RUN_DOCTYPE, "name": "RUN-1"}))
        with self.assertRaises(RuntimeError):
            with generation._target_stage(target, run, "map", ""):
                target.flags.ignore_permissions = True
                raise RuntimeError("native mapper failed")
        self.assertEqual(target.flags.ignore_permissions, "prior")

    def test_direct_source_linked_invoice_is_denied(self) -> None:
        invoice = Document(
            {
                "doctype": "Sales Invoice",
                "items": [{"sales_order": "SO-1", "so_detail": "ROW-1"}],
            }
        )
        with self.assertRaises(frappe.ValidationError):
            generation.before_insert_sales_invoice_generation(invoice)

    def test_status_and_retry_require_current_source_and_company_access(self) -> None:
        run = frappe._dict(
            {
                "doctype": generation.RUN_DOCTYPE,
                "name": "RUN-1",
                "source_doctype": "Sales Order",
                "source_name": "SO-1",
                "sales_order": "SO-1",
                "generation_status": "Failed",
                "attempt_count": 1,
                "last_error": "ValidationError",
                "target_sales_invoice": None,
                "generated_at": None,
            }
        )
        source = Document({"doctype": "Sales Order", "name": "SO-1", "company": "CO-1"})
        company = Document({"doctype": "Company", "name": "CO-1"})

        def get_doc(doctype: str, name: str) -> object:
            return {generation.RUN_DOCTYPE: run, "Sales Order": source, "Company": company}[doctype]

        with (
            patch.object(generation.frappe.db, "exists", return_value=True),
            patch.object(generation.frappe, "get_doc", side_effect=get_doc),
            patch.object(generation.frappe, "session", user="sales@example.invalid"),
            patch.object(generation.frappe, "has_permission", return_value=True) as has_permission,
            patch.object(generation, "_queue") as queue,
        ):
            status = generation.get_sales_invoice_generation_status("RUN-1")
            self.assertEqual(status["data"]["generation_status"], "Failed")
            self.assertEqual(generation.retry_sales_invoice_generation("RUN-1")["data"]["name"], "RUN-1")
            queue.assert_called_once_with("RUN-1")
            has_permission.return_value = False
            with self.assertRaises(frappe.PermissionError):
                generation.retry_sales_invoice_generation("RUN-1")

    def test_list_endpoint_filters_runs_by_native_sales_order_visibility(self) -> None:
        source = Document({"doctype": "Delivery Note", "name": "DN-1", "company": "CO-1"})
        company = Document({"doctype": "Company", "name": "CO-1"})
        rows = [
            frappe._dict({"name": "RUN-1", "sales_order": "SO-ALLOWED", "generation_status": "Failed"}),
            frappe._dict({"name": "RUN-2", "sales_order": "SO-DENIED", "generation_status": "Failed"}),
        ]

        def get_doc(doctype: str, name: str) -> Document:
            return {"Delivery Note": source, "Company": company}[doctype]

        with (
            patch.object(generation.frappe, "session", user="sales@example.invalid"),
            patch.object(generation.frappe, "get_doc", side_effect=get_doc),
            patch.object(generation.frappe, "has_permission", return_value=True),
            patch.object(generation.frappe, "get_all", return_value=rows),
            patch.object(generation.frappe, "get_list", return_value=["SO-ALLOWED"]),
        ):
            result = generation.list_sales_invoice_generations("Delivery Note", "DN-1", "0")
        self.assertEqual([row["name"] for row in result["data"]], ["RUN-1"])
