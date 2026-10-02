# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Native metadata and empty indexed current-read coverage for physical reservations."""

from __future__ import annotations

from collections import defaultdict
from unittest.mock import patch
from uuid import uuid4

import frappe
from erpnext.stock.doctype.repost_item_valuation.repost_item_valuation import repost
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from frappe.model.document import Document
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from connect_diagnostics_core.api.erpnext import (
    repost_item_valuation_reservation as reservation,
)
from connect_diagnostics_core.api.erpnext import (
    stock_reconciliation_freeze,
)
from connect_diagnostics_core.api.erpnext.repost_item_valuation_reservation import (
    RepostItemValuationReservationMixin,
    WarehouseReservationMixin,
    active_reposts,
)
from connect_diagnostics_core.api.erpnext.stock_ledger_lock import lock_warehouses
from connect_diagnostics_core.api.erpnext.storage_location_ledger import snapshot_location

COMPANY = "_Test Company with perpetual inventory"
WAREHOUSE = "Stores - TCP1"
BIN_FIELDS = (
    "actual_qty",
    "reserved_qty",
    "ordered_qty",
    "indented_qty",
    "planned_qty",
    "projected_qty",
    "reserved_qty_for_production",
    "reserved_qty_for_sub_contract",
    "reserved_qty_for_production_plan",
)


class TestRepostItemValuationReservationIntegration(IntegrationTestCase):
    def test_native_extension_and_indexed_empty_scope(self) -> None:
        self.assertTrue(frappe.db.table_exists("Repost Warehouse Reservation"))
        field = frappe.get_meta("Repost Item Valuation").get_field("reservation_warehouses")
        self.assertIsNotNone(field)
        self.assertEqual(field.fieldtype, "Table")
        self.assertEqual(field.options, "Repost Warehouse Reservation")
        self.assertIsInstance(frappe.new_doc("Repost Item Valuation"), RepostItemValuationReservationMixin)
        self.assertIsInstance(frappe.new_doc("Warehouse"), WarehouseReservationMixin)
        indexes = frappe.db.sql("show index from `tabRepost Warehouse Reservation`", as_dict=True)
        ordered = [
            str(row.Column_name)
            for row in sorted(indexes, key=lambda row: int(row.Seq_in_index))
            if row.Key_name == "warehouse_parent"
        ]
        self.assertEqual(ordered, ["warehouse", "parent"])
        self.assertEqual(active_reposts({"_Test Empty RIV Reservation"}), [])


class TestNativePhysicalRepostReservation(IntegrationTestCase):
    """Retain exact canceled native history on the disposable test site."""

    def setUp(self) -> None:
        super().setUp()
        previous_user = frappe.session.user
        self.addCleanup(frappe.set_user, previous_user)
        frappe.set_user("Administrator")
        self.owned: dict[str, str] = {}
        self.effect_ids: dict[str, set[str]] = {}
        self.thai_tax_baseline_rows: dict[str, dict[str, object]] = {}
        self.thai_tax_existing_row: str | None = None
        self.thai_tax_created_row: str | None = None
        self.addCleanup(self._close_owned_history)
        suffix = uuid4().hex
        item_name = f"_Test RIV physical {suffix}"
        location_name = f"_Test RIV location {suffix}"
        item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
        if not item_group:
            self.fail("A native leaf Item Group is required for physical repost proof")
        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": item_name,
                "item_name": item_name,
                "item_group": item_group,
                "stock_uom": "Nos",
                "is_stock_item": 1,
            }
        ).insert()
        self.owned["item"] = str(item.name)
        location = frappe.get_doc(
            {
                "doctype": "Storage Location",
                "location_code": location_name,
                "warehouse": WAREHOUSE,
            }
        ).insert()
        self.owned["location"] = str(location.name)
        merge_target = frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": f"_Test RIV merge target {suffix}",
                "company": COMPANY,
                "is_group": 0,
            }
        ).insert()
        self.owned["merge_target"] = str(merge_target.name)
        source = make_stock_entry(
            item_code=str(item.name),
            company=COMPANY,
            to_warehouse=WAREHOUSE,
            qty=1,
            rate=10,
            do_not_save=True,
        )
        source.items[0].to_storage_location = str(location.name)
        source.insert()
        self.owned["source"] = str(source.name)
        self._ensure_thai_tax_settings()
        source = apply_workflow(source, "Submit Stock Entry")
        self.assertEqual(source.docstatus, 1)
        self.assertEqual(source.purpose, "Material Receipt")
        self.assertEqual(source.get("workflow_state"), "Stock Entry Submitted")
        self.effect_ids["initial_sle"] = {str(row.name) for row in self._sle_rows()}
        self._assert_sle_provenance()
        self.effect_ids["initial_gl"] = {str(row.name) for row in self._gl_rows()}
        self.effect_ids["initial_actions"] = set(self._action_names())
        self.assertTrue(self.effect_ids["initial_sle"])
        self.assertTrue(self.effect_ids["initial_gl"])
        self.owned["first_riv"] = self._queued_riv(source)
        self.effect_ids["reservation_children"] = set(
            frappe.db.get_values(
                "Repost Warehouse Reservation",
                filters={"parent": self.owned["first_riv"], "parentfield": "reservation_warehouses"},
                fieldname="name",
                pluck=True,
            )
        )
        self.assertEqual(len(self.effect_ids["reservation_children"]), 1)
        # Publish the source and first reservation for the independent DB session.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit
        self.assertEqual(
            set(
                frappe.db.get_values(
                    "Repost Warehouse Reservation",
                    filters={"parent": self.owned["first_riv"]},
                    fieldname="name",
                    pluck=True,
                )
            ),
            self.effect_ids["reservation_children"],
        )

    def _new_riv(self, source: Document) -> Document:
        return frappe.get_doc(
            {
                "doctype": "Repost Item Valuation",
                "based_on": "Transaction",
                "voucher_type": "Stock Entry",
                "voucher_no": source.name,
                "posting_date": source.get("posting_date"),
                "posting_time": source.get("posting_time"),
                "recreate_stock_ledgers": 1,
            }
        ).insert()

    def _queued_riv(self, source: Document) -> str:
        riv = self._new_riv(source)
        riv.flags.dont_run_in_test = True
        riv.submit()
        self.assertEqual(riv.get("status"), "Queued")
        self.assertEqual({row.warehouse for row in riv.get("reservation_warehouses")}, {WAREHOUSE})
        return str(riv.name)

    def _gl_rows(self) -> list[frappe._dict]:
        return frappe.get_all(
            "GL Entry",
            filters={"voucher_type": "Stock Entry", "voucher_no": self.owned["source"]},
            fields=["name", "account", "debit", "credit", "is_cancelled"],
        )

    def _sle_rows(self) -> list[frappe._dict]:
        return frappe.get_all(
            "Stock Ledger Entry",
            filters={"voucher_type": "Stock Entry", "voucher_no": self.owned["source"]},
            fields=["name", "item_code", "warehouse", "actual_qty", "storage_location", "is_cancelled"],
        )

    def _assert_sle_provenance(self) -> None:
        for row in self._sle_rows():
            self.assertEqual(row.item_code, self.owned["item"], row)
            self.assertEqual(row.warehouse, WAREHOUSE, row)
            self.assertEqual(row.storage_location, self.owned["location"], row)

    def _action_names(self) -> list[str]:
        return frappe.get_all(
            "Workflow Action",
            filters={"reference_doctype": "Stock Entry", "reference_name": self.owned["source"]},
            pluck="name",
        )

    @staticmethod
    def _thai_tax_rows(settings: Document) -> dict[str, dict[str, object]]:
        return {
            str(row.name): {
                field: value
                for field, value in row.get_valid_dict().items()
                if field not in {"modified", "modified_by"}
            }
            for row in settings.get("company_accounts", [])
        }

    def _ensure_thai_tax_settings(self) -> None:
        settings = frappe.get_doc("Thai Tax Settings", "Thai Tax Settings", for_update=True)
        self.thai_tax_baseline_rows = self._thai_tax_rows(settings)
        if existing := next((row for row in settings.company_accounts if row.company == COMPANY), None):
            self.thai_tax_existing_row = str(existing.name)
            return
        row = settings.append("company_accounts", {"company": COMPANY})
        settings.save()
        self.thai_tax_created_row = str(row.name)

    def _restore_thai_tax_settings(self) -> None:
        settings = frappe.get_doc("Thai Tax Settings", "Thai Tax Settings", for_update=True)
        current = self._thai_tax_rows(settings)
        for name, baseline in self.thai_tax_baseline_rows.items():
            self.assertEqual(current.get(name), baseline, f"Existing Thai Tax Settings row changed: {name}")
        if self.thai_tax_created_row:
            owned_row = next(
                (row for row in settings.company_accounts if row.name == self.thai_tax_created_row),
                None,
            )
            if owned_row:
                self.assertEqual(owned_row.company, COMPANY)
                settings.remove(owned_row)
                settings.save()
                settings = frappe.get_doc("Thai Tax Settings", "Thai Tax Settings", for_update=True)
            self.assertNotIn(self.thai_tax_created_row, self._thai_tax_rows(settings))
        restored = self._thai_tax_rows(settings)
        for name, baseline in self.thai_tax_baseline_rows.items():
            self.assertEqual(restored.get(name), baseline, name)
        if self.thai_tax_existing_row:
            self.assertIn(self.thai_tax_existing_row, restored)
        # Persist exact fixture-owned settings removal after native history closes.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit

    def _run_native_repost(self, riv: Document) -> None:
        previous_flag = getattr(frappe.flags, "through_repost_item_valuation", None)
        previous_write_limit = frappe.db.MAX_WRITES_PER_TRANSACTION
        try:
            with patch.object(frappe, "in_test", False):
                repost(riv)
        finally:
            frappe.flags.through_repost_item_valuation = previous_flag
            frappe.db.MAX_WRITES_PER_TRANSACTION = previous_write_limit

    def _close_owned_history(self) -> None:
        frappe.local.db = self._primary_connection
        self._primary_connection.rollback()
        if self._secondary_connection is not None:
            self._secondary_connection.rollback()
        if "source" not in self.owned or not frappe.db.exists("Stock Entry", self.owned["source"]):
            for key, doctype in (
                ("item", "Item"),
                ("location", "Storage Location"),
                ("merge_target", "Warehouse"),
            ):
                if name := self.owned.get(key):
                    self.assertFalse(
                        frappe.db.exists(doctype, name), f"Uncommitted {doctype} survived rollback: {name}"
                    )
            self._restore_thai_tax_settings()
            return
        try:
            for key in ("first_riv", "second_riv"):
                name = self.owned.get(key)
                if not name:
                    continue
                riv = frappe.get_doc("Repost Item Valuation", name)
                if riv.docstatus != 1:
                    continue
                if riv.status == "Failed":
                    riv.restart_reposting()
                    riv.reload()
                if riv.status in {"Queued", "In Progress"}:
                    self._run_native_repost(riv)
                    riv.reload()
                if riv.status not in {"Completed", "Skipped"}:
                    self.fail(f"Native RIV did not reach a terminal state: {name}: {riv.status}")
                riv.cancel()
            source = frappe.get_doc("Stock Entry", self.owned["source"])
            self.effect_ids["pre_cancel_sle"] = {str(row.name) for row in self._sle_rows()}
            self.effect_ids["pre_cancel_gl"] = {str(row.name) for row in self._gl_rows()}
            if source.docstatus == 1:
                apply_workflow(source, "Cancel Stock Entry")
            if frappe.db.exists("Warehouse", self.owned["merge_target"]):
                frappe.delete_doc("Warehouse", self.owned["merge_target"])
            # Preserve native reversal even if a later evidence assertion fails.
            frappe.db.commit()
            self.assertEqual(frappe.db.get_value("Stock Entry", source.name, "docstatus"), 2)
            self.assertEqual(
                frappe.db.get_value("Stock Entry", source.name, "workflow_state"),
                "Stock Entry Cancelled",
            )
            self.assertTrue(frappe.db.exists("Item", self.owned["item"]))
            self.assertTrue(frappe.db.exists("Storage Location", self.owned["location"]))
            self.assertFalse(frappe.db.exists("Warehouse", self.owned["merge_target"]))
            self.assertTrue(frappe.db.exists("Repost Item Valuation", self.owned["first_riv"]))
            self.assertEqual(
                frappe.db.get_value("Repost Item Valuation", self.owned["first_riv"], "docstatus"),
                2,
            )
            for key, evidence_key in (
                ("first_riv", "reservation_children"),
                ("second_riv", "second_reservation_children"),
            ):
                if name := self.owned.get(key):
                    self.assertEqual(
                        set(
                            frappe.db.get_values(
                                "Repost Warehouse Reservation",
                                filters={"parent": name},
                                fieldname="name",
                                pluck=True,
                            )
                        ),
                        self.effect_ids.get(evidence_key, set()),
                    )
            final_sle = {str(row.name) for row in self._sle_rows()}
            final_gl = {str(row.name) for row in self._gl_rows()}
            self.assertTrue(self.effect_ids["pre_cancel_sle"].issubset(final_sle))
            self.assertTrue(self.effect_ids["pre_cancel_gl"].issubset(final_gl))
            self.effect_ids["final_sle"] = final_sle
            self.effect_ids["final_gl"] = final_gl
            self._assert_sle_provenance()
            bins = frappe.get_all(
                "Bin",
                filters={"item_code": self.owned["item"], "warehouse": WAREHOUSE},
                fields=["name", *BIN_FIELDS],
            )
            for row in bins:
                self.assertTrue(all(float(row.get(field) or 0) == 0 for field in BIN_FIELDS), row)
            self.assertEqual(
                snapshot_location(
                    company=COMPANY,
                    item_code=self.owned["item"],
                    warehouse=WAREHOUSE,
                    storage_location=self.owned["location"],
                    cutoff=now_datetime(),
                ).quantity,
                0,
            )
            gl_rows = self._gl_rows()
            self.assertTrue(gl_rows)
            totals: dict[str, float] = defaultdict(float)
            for row in gl_rows:
                totals[str(row.account)] += float(row.debit or 0) - float(row.credit or 0)
            self.assertTrue(all(abs(total) < 0.000001 for total in totals.values()), totals)
            self.assertFalse(
                frappe.get_all(
                    "Repost Item Valuation",
                    filters={
                        "voucher_type": "Stock Entry",
                        "voucher_no": source.name,
                        "docstatus": 1,
                        "recreate_stock_ledgers": 1,
                        "status": ("in", ["Queued", "In Progress"]),
                    },
                    pluck="name",
                )
            )
            final_actions = set(self._action_names())
            self.assertTrue(self.effect_ids["initial_actions"].issubset(final_actions))
            self.effect_ids["final_actions"] = final_actions
            self.assertFalse(
                frappe.get_all(
                    "Workflow Action",
                    filters={
                        "reference_doctype": "Stock Entry",
                        "reference_name": source.name,
                        "status": "Open",
                    },
                    pluck="name",
                )
            )
            frappe.db.commit()
        except Exception as exc:
            frappe.db.rollback()
            raise AssertionError(
                f"Native RIV fixture cleanup failed for {self.owned}; effects {self.effect_ids}; "
                f"Thai Tax Settings prerequisite retained as {self.thai_tax_created_row}"
            ) from exc
        self._restore_thai_tax_settings()

    def test_two_sessions_reserve_and_replay_only_one_physical_source(self) -> None:
        first = self.owned["first_riv"]
        with self.primary_connection():
            riv = frappe.get_doc("Repost Item Valuation", first)
            self.effect_ids["original_reservation_children"] = set(self.effect_ids["reservation_children"])
            riv.set_status("Failed")
            self.assertEqual(frappe.db.get_value(riv.doctype, riv.name, "status"), "Failed")
            riv.restart_reposting()
            rebuilt = set(
                frappe.db.get_values(
                    "Repost Warehouse Reservation",
                    filters={"parent": first},
                    fieldname="name",
                    pluck=True,
                )
            )
            self.assertEqual(len(rebuilt), 1)
            self.assertTrue(rebuilt.isdisjoint(self.effect_ids["original_reservation_children"]))
            self.effect_ids["reservation_children"] = rebuilt
            self.assertEqual(frappe.db.get_value(riv.doctype, riv.name, "status"), "Queued")
            # Publish the rebuilt queued reservation before the second session probes it.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
        with self.primary_connection():
            rename_target = f"_Test RIV denied rename {uuid4().hex}"
            for operation in (
                lambda: frappe.rename_doc("Warehouse", WAREHOUSE, rename_target),
                lambda: frappe.rename_doc("Warehouse", WAREHOUSE, self.owned["merge_target"], merge=True),
                lambda: frappe.delete_doc("Warehouse", WAREHOUSE),
            ):
                with self.assertRaisesRegex(frappe.ValidationError, "queued or in progress"):
                    operation()
                frappe.db.rollback()
                self.assertTrue(frappe.db.exists("Warehouse", WAREHOUSE))
                self.assertTrue(frappe.db.exists("Warehouse", self.owned["merge_target"]))
                frappe.db.rollback()
        with self.primary_connection():
            lock_warehouses((WAREHOUSE,))
            with self.secondary_connection():
                candidate = self._new_riv(frappe.get_doc("Stock Entry", self.owned["source"]))
                candidate_name = str(candidate.name)
                candidate.flags.dont_run_in_test = True
                with self.assertRaisesRegex(frappe.ValidationError, "retry"):
                    candidate.submit()
                frappe.db.rollback()
                self.assertFalse(frappe.db.exists("Repost Item Valuation", candidate_name))
                frappe.db.rollback()
            self._primary_connection.rollback()
        with self.secondary_connection():
            candidate = self._new_riv(frappe.get_doc("Stock Entry", self.owned["source"]))
            candidate_name = str(candidate.name)
            candidate.flags.dont_run_in_test = True
            with self.assertRaisesRegex(frappe.ValidationError, "queued or in progress"):
                candidate.submit()
            frappe.db.rollback()
            self.assertFalse(frappe.db.exists("Repost Item Valuation", candidate_name))
            frappe.db.rollback()
        with self.primary_connection():
            self.assertEqual(
                frappe.db.count(
                    "Repost Warehouse Reservation",
                    {"warehouse": WAREHOUSE, "parent": first},
                ),
                1,
            )
        with self.secondary_connection():
            self.assertEqual(frappe.db.get_value("Repost Item Valuation", first, "status"), "Queued")
        with self.primary_connection():
            riv = frappe.get_doc("Repost Item Valuation", first)
            riv.set_status("In Progress")
            # Expose the native in-progress state to the foreground second session.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
        with self.secondary_connection():
            with self.assertRaisesRegex(frappe.ValidationError, "retry|repost is in progress"):
                stock_reconciliation_freeze.validate_transaction(
                    Document(
                        {
                            "doctype": "Stock Entry",
                            "items": [{"item_code": self.owned["item"], "t_warehouse": WAREHOUSE}],
                        }
                    )
                )
            frappe.db.rollback()
            self.assertEqual(active_reposts({WAREHOUSE}, statuses=("In Progress",)), [first])
            frappe.db.rollback()
        with self.primary_connection():
            riv = frappe.get_doc("Repost Item Valuation", first)
            with patch.object(
                reservation, "assert_current_scope", wraps=reservation.assert_current_scope
            ) as check:
                self._run_native_repost(riv)
            self.assertGreaterEqual(check.call_count, 2)
            self.assertEqual(frappe.db.get_value(riv.doctype, riv.name, "status"), "Completed")
            self.effect_ids["repost_sle"] = {str(row.name) for row in self._sle_rows()}
            self.effect_ids["repost_gl"] = {str(row.name) for row in self._gl_rows()}
            self.assertTrue(self.effect_ids["repost_sle"])
            self.assertTrue(self.effect_ids["repost_gl"])
            self._assert_sle_provenance()
            source = frappe.get_doc("Stock Entry", self.owned["source"])
            self.owned["second_riv"] = self._queued_riv(source)
            self.effect_ids["second_reservation_children"] = set(
                frappe.db.get_values(
                    "Repost Warehouse Reservation",
                    filters={"parent": self.owned["second_riv"]},
                    fieldname="name",
                    pluck=True,
                )
            )
            self.assertEqual(len(self.effect_ids["second_reservation_children"]), 1)
            # Persist the successor reservation so cleanup can close its native history.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
            self.assertEqual(active_reposts({WAREHOUSE}), [self.owned["second_riv"]])
