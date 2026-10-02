# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Exact Location snapshot authorization and native bundle evidence tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext.storage_location_ledger import (
    LocationSnapshot,
    snapshot_location,
)


class TestStorageLocationLedger(UnitTestCase):
    def _snapshot(
        self,
        *,
        ledger: list[frappe._dict],
        bundles: list[frappe._dict] | None = None,
        entries: list[frappe._dict] | None = None,
        serial: bool = False,
        batch: bool = False,
        rounding_failure: bool = False,
        locking_read: bool = False,
    ) -> LocationSnapshot:
        docs = {
            "Company": frappe._dict(name="Test Company"),
            "Item": frappe._dict(name="TEST-ITEM", has_serial_no=serial, has_batch_no=batch),
            "Warehouse": frappe._dict(name="Test Warehouse", company="Test Company"),
            "Storage Location": frappe._dict(name="Rack A", warehouse="Test Warehouse"),
        }

        def get_all(doctype: str, **kwargs: object) -> list[frappe._dict]:
            if doctype == "Stock Ledger Entry":
                filters = cast(dict[str, object], kwargs["filters"])
                self.assertEqual(filters["docstatus"], 1)
                self.assertEqual(filters["is_cancelled"], 0)
                self.assertEqual(filters["posting_datetime"], ("<=", datetime(2026, 10, 1, 12)))
                return ledger
            if doctype == "Serial and Batch Bundle":
                return bundles or []
            if doctype == "Serial and Batch Entry":
                return entries or []
            raise AssertionError(doctype)

        def get_values(
            doctype: str, filters: dict[str, object], fields: list[str], **kwargs: object
        ) -> list[frappe._dict]:
            self.assertEqual(kwargs, {"as_dict": True, "for_update": True, "wait": False, "order_by": "name"})
            if doctype == "Serial and Batch Bundle":
                self.assertEqual(filters, {"name": ("in", ["BUNDLE-1"])})
            elif doctype == "Serial and Batch Entry":
                self.assertEqual(
                    filters,
                    {"parent": ("in", ["BUNDLE-1"]), "parenttype": "Serial and Batch Bundle"},
                )
            return get_all(doctype, filters=filters, fields=fields)

        with (
            patch("frappe.db.exists", return_value=True),
            patch("frappe.db.get_value", side_effect=lambda doctype, name, fieldname, **kwargs: name),
            patch("frappe.get_doc", side_effect=lambda doctype, name, **kwargs: docs[doctype]),
            patch("frappe.has_permission", return_value=True),
            patch("connect_diagnostics_core.api.erpnext.storage_location_ledger.lock_warehouses"),
            patch(
                "connect_diagnostics_core.api.erpnext.storage_location_ledger.require_operational_warehouse"
            ),
            patch("connect_diagnostics_core.api.erpnext.storage_location_ledger.require_location_warehouse"),
            patch("frappe.get_all", side_effect=get_all),
            patch("frappe.db.get_values", side_effect=get_values) as locked_values,
            patch("frappe.get_meta") as meta,
            patch(
                "frappe.get_system_settings",
                return_value="Banker's Rounding",
                side_effect=RuntimeError("Rounding setting unavailable") if rounding_failure else None,
            ),
            patch(
                "connect_diagnostics_core.api.erpnext.storage_location_ledger.get_field_precision",
                return_value=6,
            ),
        ):
            meta.return_value.get_field.return_value.precision = 6
            snapshot = snapshot_location(
                company="Test Company",
                item_code="TEST-ITEM",
                warehouse="Test Warehouse",
                storage_location="Rack A",
                cutoff="2026-10-01 12:00:00",
                locking_read=locking_read,
            )
            if locking_read:
                self.assertEqual(
                    [call.args[0] for call in locked_values.call_args_list],
                    ["Stock Ledger Entry"]
                    + (["Serial and Batch Bundle", "Serial and Batch Entry"] if serial or batch else []),
                )
            else:
                locked_values.assert_not_called()
            return snapshot

    def test_untracked_decimal_quantity_uses_each_active_leg_once(self) -> None:
        ledger = [frappe._dict(actual_qty=value) for value in ("0.1", "0.2", "-0.1", "0")]
        result = self._snapshot(ledger=ledger)
        self.assertEqual(result.quantity, Decimal("0.2"))
        self.assertEqual(result.identities, ())

    def test_locking_read_uses_current_parents_then_sorted_nowait_dict_filters(self) -> None:
        calls: list[tuple[str, str]] = []
        docs = {
            "Company": frappe._dict(name="Test Company"),
            "Item": frappe._dict(name="TEST-ITEM", has_serial_no=0, has_batch_no=0),
            "Warehouse": frappe._dict(name="Test Warehouse", company="Test Company", is_group=0, disabled=0),
            "Storage Location": frappe._dict(name="Rack A", warehouse="Test Warehouse"),
        }

        def lock_warehouses(names: tuple[str, ...]) -> None:
            self.assertEqual(names, ("Test Warehouse",))
            calls.append(("warehouse_mutex", names[0]))

        def get_value(doctype: str, name: str, fieldname: str, **kwargs: object) -> str:
            self.assertEqual((fieldname, kwargs), ("name", {"for_update": True, "wait": False}))
            calls.append(("prelock", doctype))
            return name

        def get_doc(doctype: str, name: str, **kwargs: object) -> frappe._dict:
            self.assertEqual(kwargs, {"for_update": True})
            self.assertEqual(name, docs[doctype].name)
            calls.append(("current_doc", doctype))
            return docs[doctype]

        def get_values(
            doctype: str, filters: dict[str, object], fields: list[str], **kwargs: object
        ) -> list[frappe._dict]:
            self.assertEqual(doctype, "Stock Ledger Entry")
            self.assertEqual(kwargs, {"as_dict": True, "for_update": True, "wait": False, "order_by": "name"})
            self.assertEqual(filters["storage_location"], "Rack A")
            self.assertEqual(filters["is_cancelled"], 0)
            self.assertEqual(filters["posting_datetime"], ("<=", datetime(2026, 10, 1, 12)))
            self.assertIn("actual_qty", fields)
            calls.append(("rows", doctype))
            return [frappe._dict(actual_qty="2")]

        with (
            patch(
                "connect_diagnostics_core.api.erpnext.storage_location_ledger.lock_warehouses",
                side_effect=lock_warehouses,
            ),
            patch("frappe.db.get_value", side_effect=get_value),
            patch("frappe.get_doc", side_effect=get_doc),
            patch("frappe.has_permission", return_value=True),
            patch("frappe.db.get_values", side_effect=get_values),
            patch("frappe.get_all") as get_all,
            patch(
                "connect_diagnostics_core.api.erpnext.storage_location_ledger.require_operational_warehouse"
            ) as legacy_warehouse,
            patch(
                "connect_diagnostics_core.api.erpnext.storage_location_ledger.require_location_warehouse"
            ) as legacy_location,
        ):
            snapshot = snapshot_location(
                company="Test Company",
                item_code="TEST-ITEM",
                warehouse="Test Warehouse",
                storage_location="Rack A",
                cutoff="2026-10-01 12:00:00",
                locking_read=True,
            )
        self.assertEqual(snapshot, LocationSnapshot(Decimal(2), ()))
        self.assertEqual(
            calls,
            [
                ("warehouse_mutex", "Test Warehouse"),
                ("prelock", "Company"),
                ("prelock", "Item"),
                ("prelock", "Warehouse"),
                ("prelock", "Storage Location"),
                ("current_doc", "Company"),
                ("current_doc", "Item"),
                ("current_doc", "Warehouse"),
                ("current_doc", "Storage Location"),
                ("rows", "Stock Ledger Entry"),
            ],
        )
        get_all.assert_not_called()
        legacy_warehouse.assert_not_called()
        legacy_location.assert_not_called()

    def test_locking_read_maps_warehouse_contention_before_ledger_read(self) -> None:
        with (
            patch(
                "connect_diagnostics_core.api.erpnext.storage_location_ledger.lock_warehouses",
                side_effect=frappe.QueryTimeoutError("held"),
            ),
            patch(
                "connect_diagnostics_core.api.erpnext.storage_location_ledger.lock_conflict",
                side_effect=frappe.ValidationError("retry"),
            ) as conflict,
            patch("frappe.db.get_values") as rows,
            patch("frappe.get_all") as legacy_rows,
        ):
            with self.assertRaisesRegex(frappe.ValidationError, "retry"):
                snapshot_location(
                    company="Test Company",
                    item_code="TEST-ITEM",
                    warehouse="Test Warehouse",
                    storage_location="Rack A",
                    cutoff="2026-10-01 12:00:00",
                    locking_read=True,
                )
        conflict.assert_called_once_with()
        rows.assert_not_called()
        legacy_rows.assert_not_called()

    def test_composite_serial_batch_identity_and_zero_valuation_leg(self) -> None:
        leg = frappe._dict(
            name="SLE-1",
            item_code="TEST-ITEM",
            warehouse="Test Warehouse",
            voucher_type="Stock Entry",
            voucher_no="STE-1",
            voucher_detail_no="ROW-1",
            actual_qty="1",
            serial_and_batch_bundle="BUNDLE-1",
        )
        bundle = frappe._dict(
            name="BUNDLE-1",
            docstatus=1,
            is_cancelled=0,
            company="Test Company",
            item_code="TEST-ITEM",
            warehouse="Test Warehouse",
            voucher_type="Stock Entry",
            voucher_no="STE-1",
            voucher_detail_no="ROW-1",
            type_of_transaction="Inward",
            total_qty="1",
        )
        child = frappe._dict(
            parent="BUNDLE-1",
            docstatus=1,
            is_cancelled=0,
            item_code="TEST-ITEM",
            warehouse="Test Warehouse",
            voucher_type="Stock Entry",
            voucher_no="STE-1",
            voucher_detail_no="ROW-1",
            type_of_transaction="Inward",
            serial_no="SER-1",
            batch_no="BAT-1",
            qty="1",
        )
        zero = frappe._dict(actual_qty="0", serial_and_batch_bundle=None)
        result = self._snapshot(
            ledger=[leg, zero], bundles=[bundle], entries=[child], serial=True, batch=True
        )
        self.assertEqual(result.quantity, Decimal(1))
        self.assertEqual(result.identities, (("SER-1", "BAT-1", Decimal(1)),))
        self.assertEqual(
            self._snapshot(
                ledger=[leg, zero],
                bundles=[bundle],
                entries=[child],
                serial=True,
                batch=True,
                locking_read=True,
            ),
            result,
        )
        child.qty = "2"
        with self.assertRaises(frappe.ValidationError):
            self._snapshot(ledger=[leg], bundles=[bundle], entries=[child], serial=True, batch=True)
        child.qty = "1"
        for field, invalid in (
            ("docstatus", 0),
            ("is_cancelled", 1),
            ("company", "Other Company"),
            ("voucher_detail_no", "OTHER-ROW"),
            ("type_of_transaction", "Outward"),
            ("total_qty", "2"),
        ):
            original = bundle[field]
            bundle[field] = invalid
            with self.subTest(bundle_field=field), self.assertRaises(frappe.ValidationError):
                self._snapshot(ledger=[leg], bundles=[bundle], entries=[child], serial=True, batch=True)
            bundle[field] = original
        for field, invalid in (
            ("docstatus", 0),
            ("is_cancelled", 1),
            ("item_code", "OTHER-ITEM"),
            ("voucher_no", "OTHER-STE"),
            ("type_of_transaction", "Outward"),
            ("serial_no", None),
            ("batch_no", None),
            ("qty", "-1"),
        ):
            original = child[field]
            setattr(child, field, invalid)
            with self.subTest(child_field=field), self.assertRaises(frappe.ValidationError):
                self._snapshot(ledger=[leg], bundles=[bundle], entries=[child], serial=True, batch=True)
            setattr(child, field, original)
        child.qty = "NaN"
        with self.assertRaises(frappe.ValidationError):
            self._snapshot(ledger=[leg], bundles=[bundle], entries=[child], serial=True, batch=True)
        child.qty = "1e999"
        with self.assertRaises(frappe.ValidationError):
            self._snapshot(ledger=[leg], bundles=[bundle], entries=[child], serial=True, batch=True)
        child.qty = "1"
        with self.assertRaisesRegex(RuntimeError, "Rounding setting unavailable"):
            self._snapshot(
                ledger=[leg],
                bundles=[bundle],
                entries=[child],
                serial=True,
                batch=True,
                rounding_failure=True,
            )

    def test_missing_and_reused_bundle_fail_closed(self) -> None:
        leg = frappe._dict(actual_qty="1", serial_and_batch_bundle=None)
        with self.assertRaises(frappe.ValidationError):
            self._snapshot(ledger=[leg], serial=True)
        leg.serial_and_batch_bundle = "BUNDLE-1"
        with self.assertRaises(frappe.ValidationError):
            self._snapshot(ledger=[leg, leg], serial=True)

    def test_company_permission_precedes_ledger_read(self) -> None:
        with (
            patch("frappe.db.exists", return_value=True),
            patch("frappe.get_doc", return_value=frappe._dict(name="Test Company")),
            patch("frappe.has_permission", return_value=False),
            patch("frappe.get_all") as get_all,
        ):
            with self.assertRaises(frappe.PermissionError):
                snapshot_location(
                    company="Test Company",
                    item_code="TEST-ITEM",
                    warehouse="Test Warehouse",
                    storage_location="Rack A",
                    cutoff="2026-10-01 12:00:00",
                )
            self.assertFalse(
                any(
                    call.args[0]
                    in {"Stock Ledger Entry", "Serial and Batch Bundle", "Serial and Batch Entry"}
                    for call in get_all.call_args_list
                )
            )

    def test_item_warehouse_and_location_permission_precede_ledger_read(self) -> None:
        docs = {
            "Company": frappe._dict(name="Test Company"),
            "Item": frappe._dict(name="TEST-ITEM"),
            "Warehouse": frappe._dict(name="Test Warehouse", company="Test Company"),
        }
        for denied in ("Item", "Warehouse"):
            with (
                self.subTest(denied=denied),
                patch("frappe.db.exists", return_value=True),
                patch("frappe.get_doc", side_effect=lambda doctype, name: docs[doctype]),
                patch("frappe.has_permission", side_effect=lambda doctype, **kwargs: doctype != denied),
                patch(
                    "connect_diagnostics_core.api.erpnext.storage_location_ledger.require_operational_warehouse"
                ),
                patch("frappe.get_all") as get_all,
            ):
                with self.assertRaises(frappe.PermissionError):
                    snapshot_location(
                        company="Test Company",
                        item_code="TEST-ITEM",
                        warehouse="Test Warehouse",
                        storage_location="Rack A",
                        cutoff="2026-10-01 12:00:00",
                    )
                self.assertFalse(any(call.args[0] == "Stock Ledger Entry" for call in get_all.call_args_list))
        with (
            patch("frappe.db.exists", return_value=True),
            patch("frappe.get_doc", side_effect=lambda doctype, name: docs[doctype]),
            patch("frappe.has_permission", return_value=True),
            patch(
                "connect_diagnostics_core.api.erpnext.storage_location_ledger.require_operational_warehouse"
            ),
            patch(
                "connect_diagnostics_core.api.erpnext.storage_location_ledger.require_location_warehouse",
                side_effect=frappe.PermissionError,
            ),
            patch("frappe.get_all") as get_all,
        ):
            with self.assertRaises(frappe.PermissionError):
                snapshot_location(
                    company="Test Company",
                    item_code="TEST-ITEM",
                    warehouse="Test Warehouse",
                    storage_location="Rack A",
                    cutoff="2026-10-01 12:00:00",
                )
            self.assertFalse(any(call.args[0] == "Stock Ledger Entry" for call in get_all.call_args_list))

    def test_cutoff_rejects_missing_and_offset_datetime(self) -> None:
        from datetime import timezone

        with self.assertRaises(frappe.ValidationError):
            snapshot_location(
                company="",
                item_code="TEST-ITEM",
                warehouse="Test Warehouse",
                storage_location="Rack A",
                cutoff="2026-10-01 12:00:00",
            )
        docs = {
            "Company": frappe._dict(name="Test Company"),
            "Item": frappe._dict(name="TEST-ITEM"),
            "Warehouse": frappe._dict(name="Test Warehouse", company="Test Company"),
        }
        with (
            patch("frappe.db.exists", return_value=True),
            patch("frappe.get_doc", side_effect=lambda doctype, name: docs[doctype]),
            patch("frappe.has_permission", return_value=True),
            patch(
                "connect_diagnostics_core.api.erpnext.storage_location_ledger.require_operational_warehouse"
            ),
            patch("connect_diagnostics_core.api.erpnext.storage_location_ledger.require_location_warehouse"),
            patch("frappe.get_all") as get_all,
        ):
            for cutoff in ("", datetime(2026, 10, 1, tzinfo=UTC)):
                with self.subTest(cutoff=cutoff), self.assertRaises(frappe.ValidationError):
                    snapshot_location(
                        company="Test Company",
                        item_code="TEST-ITEM",
                        warehouse="Test Warehouse",
                        storage_location="Rack A",
                        cutoff=cutoff,
                    )
            self.assertFalse(any(call.args[0] == "Stock Ledger Entry" for call in get_all.call_args_list))
