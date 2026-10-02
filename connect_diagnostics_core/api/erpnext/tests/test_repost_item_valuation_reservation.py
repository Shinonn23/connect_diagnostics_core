# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import repost_item_valuation_reservation as reservation
from connect_diagnostics_core.api.erpnext import stock_reconciliation_freeze


class TestRepostItemValuationReservation(UnitTestCase):
    def test_physical_scope_includes_current_source_and_old_ledger_warehouses(self) -> None:
        riv = Document(
            {
                "doctype": "Repost Item Valuation",
                "based_on": "Transaction",
                "voucher_type": "Stock Entry",
                "voucher_no": "SE-1",
                "recreate_stock_ledgers": 1,
            }
        )
        source = Document(
            {
                "doctype": "Stock Entry",
                "docstatus": 1,
                "items": [{"item_code": "ITEM-1", "s_warehouse": "CURRENT"}],
            }
        )
        with (
            patch.object(reservation, "locked_document", return_value=source),
            patch.object(reservation.frappe.db, "sql", return_value=[("OLD",)]),
            patch.object(reservation, "lock_warehouses") as lock,
            patch.object(reservation, "_check_item_level", return_value=[]),
            patch.object(reservation, "_check_warehouse_level", return_value=[]),
        ):
            self.assertEqual(reservation.physical_scope(riv), {"CURRENT", "OLD"})
        lock.assert_called_once_with({"CURRENT", "OLD"})

    def test_old_ledger_may_be_empty_when_source_has_warehouse(self) -> None:
        riv = Document(
            {
                "doctype": "Repost Item Valuation",
                "based_on": "Transaction",
                "voucher_type": "Stock Entry",
                "voucher_no": "SE-1",
                "recreate_stock_ledgers": 1,
            }
        )
        source = Document(
            {
                "doctype": "Stock Entry",
                "docstatus": 1,
                "items": [{"item_code": "ITEM-1", "t_warehouse": "NEW"}],
            }
        )
        with (
            patch.object(reservation, "locked_document", return_value=source),
            patch.object(reservation.frappe.db, "sql", return_value=[]),
            patch.object(reservation, "lock_warehouses"),
            patch.object(reservation, "_check_item_level", return_value=[]),
            patch.object(reservation, "_check_warehouse_level", return_value=[]),
        ):
            self.assertEqual(reservation.physical_scope(riv), {"NEW"})

    def test_physical_repost_refuses_active_native_count_before_replay(self) -> None:
        riv = Document(
            {
                "doctype": "Repost Item Valuation",
                "based_on": "Transaction",
                "voucher_type": "Stock Entry",
                "voucher_no": "SE-1",
                "recreate_stock_ledgers": 1,
            }
        )
        source = Document(
            {
                "doctype": "Stock Entry",
                "docstatus": 1,
                "items": [{"item_code": "ITEM-1", "t_warehouse": "NEW"}],
            }
        )
        with (
            patch.object(reservation, "locked_document", return_value=source),
            patch.object(reservation.frappe.db, "sql", return_value=[]),
            patch.object(reservation, "lock_warehouses"),
            patch.object(reservation, "_check_item_level", return_value=["Count-1"]),
            patch.object(reservation, "_check_warehouse_level", return_value=[]),
            self.assertRaisesRegex(frappe.ValidationError, "Count-1"),
        ):
            reservation.physical_scope(riv)

    def test_unsupported_physical_source_is_rejected_before_read(self) -> None:
        riv = Document(
            {
                "doctype": "Repost Item Valuation",
                "based_on": "Transaction",
                "voucher_type": "Asset Capitalization",
                "voucher_no": "AC-1",
                "recreate_stock_ledgers": 1,
            }
        )
        with (
            patch.object(reservation, "locked_document") as source,
            self.assertRaises(frappe.ValidationError),
        ):
            reservation.physical_scope(riv)
        source.assert_not_called()

    def test_current_parent_status_controls_reservation(self) -> None:
        with (
            patch.object(reservation.frappe.db, "sql", side_effect=[[("RIV-1",)], []]) as sql,
            patch.object(
                reservation.frappe.db,
                "get_values",
                return_value=[
                    frappe._dict(name="RIV-1", docstatus=1, status="In Progress", recreate_stock_ledgers=1)
                ],
            ),
        ):
            self.assertEqual(reservation.active_reposts({"A", "B"}, statuses=("In Progress",)), ["RIV-1"])
        self.assertEqual(sql.call_count, 2)
        self.assertEqual(sql.call_args_list[0].args[1][0], "A")
        self.assertEqual(sql.call_args_list[1].args[1][0], "B")

    def test_parent_statuses_are_one_batched_current_read(self) -> None:
        with (
            patch.object(reservation.frappe.db, "sql", return_value=[("RIV-2",), ("RIV-1",)]),
            patch.object(
                reservation.frappe.db,
                "get_values",
                return_value=[
                    frappe._dict(name="RIV-1", docstatus=1, status="Completed", recreate_stock_ledgers=1),
                    frappe._dict(name="RIV-2", docstatus=1, status="Queued", recreate_stock_ledgers=1),
                ],
            ) as parents,
        ):
            self.assertEqual(reservation.active_reposts({"WH-1"}), ["RIV-2"])
        parents.assert_called_once()
        self.assertEqual(parents.call_args.kwargs["filters"], {"name": ("in", ["RIV-1", "RIV-2"])})
        self.assertTrue(parents.call_args.kwargs["for_update"])
        self.assertFalse(parents.call_args.kwargs["wait"])

    def test_current_read_conflict_fails_closed_for_foreground(self) -> None:
        movement = Document(
            {
                "doctype": "Stock Entry",
                "items": [{"item_code": "ITEM-1", "s_warehouse": "WH-1"}],
            }
        )
        with (
            patch.object(
                reservation.frappe.db,
                "sql",
                side_effect=frappe.QueryDeadlockError("CHECKREAD 1020"),
            ),
            patch.object(stock_reconciliation_freeze, "lock_warehouses"),
            self.assertRaises(frappe.ValidationError),
        ):
            stock_reconciliation_freeze.validate_transaction(movement)

    def test_queued_blocks_activation_but_not_foreground(self) -> None:
        with patch.object(reservation, "active_reposts", side_effect=[[], ["RIV-1"]]) as active:
            reservation.check_foreground_repost({"A"})
            with self.assertRaises(frappe.ValidationError):
                reservation.check_count_activation({"A"})
        self.assertEqual(active.call_args_list[0].kwargs, {"statuses": ("In Progress",)})

    def test_second_physical_submit_refuses_queued_peer_before_child_publication(self) -> None:
        class Extended(reservation.RepostItemValuationReservationMixin, Document):
            pass

        riv = Extended(
            {
                "doctype": "Repost Item Valuation",
                "name": "RIV-2",
                "recreate_stock_ledgers": 1,
            }
        )
        with (
            patch.object(reservation, "physical_scope", return_value={"WH-1"}),
            patch.object(reservation, "check_count_activation", side_effect=frappe.ValidationError("busy")),
            self.assertRaises(frappe.ValidationError),
        ):
            riv.before_submit()
        self.assertFalse(riv.get("reservation_warehouses"))

    def test_reposted_source_drift_fails_before_native_effect(self) -> None:
        riv = Document({"doctype": "Repost Item Valuation", "name": "RIV-1"})
        with (
            patch.object(
                reservation.frappe.db,
                "get_value",
                return_value=frappe._dict(
                    based_on=None,
                    voucher_type=None,
                    voucher_no=None,
                    recreate_stock_ledgers=None,
                    docstatus=1,
                ),
            ),
            patch.object(reservation, "physical_scope", return_value={"NEW", "OLD"}),
            patch.object(reservation, "_persisted_scope", return_value={"NEW"}),
            self.assertRaises(frappe.ValidationError),
        ):
            reservation.assert_current_scope(riv)

    def test_parent_identity_drift_fails_before_source_read(self) -> None:
        riv = Document(
            {
                "doctype": "Repost Item Valuation",
                "name": "RIV-1",
                "based_on": "Transaction",
                "voucher_type": "Stock Entry",
                "voucher_no": "SE-1",
                "recreate_stock_ledgers": 1,
            }
        )
        with (
            patch.object(
                reservation.frappe.db,
                "get_value",
                return_value=frappe._dict(
                    based_on="Transaction",
                    voucher_type="Stock Entry",
                    voucher_no="SE-OTHER",
                    recreate_stock_ledgers=1,
                    docstatus=1,
                ),
            ),
            patch.object(reservation, "physical_scope") as scope,
            self.assertRaises(frappe.ValidationError),
        ):
            reservation.assert_current_scope(riv)
        scope.assert_not_called()

    def test_prephysical_scope_drift_prevents_native_replay(self) -> None:
        class Native:
            name = "RIV-1"

            def get(self, field: str) -> object:
                return 1 if field == "recreate_stock_ledgers" else None

            def recreate_stock_ledger_entries(self) -> None:
                raise AssertionError("native replay must not run")

        class Extended(reservation.RepostItemValuationReservationMixin, Native):
            pass

        with (
            patch.object(reservation, "assert_current_scope", side_effect=frappe.ValidationError("drift")),
            self.assertRaises(frappe.ValidationError),
        ):
            Extended().recreate_stock_ledger_entries()

    def test_prephysical_current_read_error_remains_native_recoverable(self) -> None:
        class Native:
            def get(self, field: str) -> object:
                return 1 if field == "recreate_stock_ledgers" else None

            def recreate_stock_ledger_entries(self) -> None:
                raise AssertionError("native replay must not run")

        class Extended(reservation.RepostItemValuationReservationMixin, Native):
            pass

        with (
            patch.object(
                reservation,
                "assert_current_scope",
                side_effect=frappe.QueryDeadlockError("CHECKREAD 1020"),
            ),
            self.assertRaises(frappe.QueryDeadlockError),
        ):
            Extended().recreate_stock_ledger_entries()

    def test_restart_uses_persisted_failed_source_and_persists_children_first(self) -> None:
        events: list[str] = []

        class Native:
            doctype = "Repost Item Valuation"
            name = "RIV-1"
            docstatus = 1
            status = "Failed"

            def get(self, field: str) -> object:
                return getattr(self, field, None)

            def set(self, field: str, value: object) -> None:
                setattr(self, field, value)

            def update_children(self) -> None:
                events.append("children")

            def restart_reposting(self) -> None:
                events.append("native")

        class Extended(reservation.RepostItemValuationReservationMixin, Native):
            recreate_stock_ledgers = 1

        persisted = Extended()
        forged = Extended()
        forged.status = "Queued"
        with (
            patch.object(reservation.frappe, "has_permission", return_value=True),
            patch.object(reservation.frappe.db, "get_value", return_value="RIV-1"),
            patch.object(reservation.frappe, "get_doc", return_value=persisted),
            patch.object(reservation, "physical_scope", return_value={"B", "A"}),
            patch.object(reservation, "check_count_activation"),
        ):
            forged.restart_reposting()
        self.assertEqual(events, ["children", "native"])
        rows = cast(list[dict[str, str]], persisted.get("reservation_warehouses"))
        self.assertEqual([row["warehouse"] for row in rows], ["A", "B"])

    def test_read_only_user_cannot_restart(self) -> None:
        class Native:
            doctype = "Repost Item Valuation"

        class Extended(reservation.RepostItemValuationReservationMixin, Native):
            pass

        with (
            patch.object(reservation.frappe, "has_permission", return_value=False),
            patch.object(reservation.frappe.db, "get_value") as db_read,
            self.assertRaises(frappe.PermissionError),
        ):
            Extended().restart_reposting()
        db_read.assert_not_called()

    def test_warehouse_rename_locks_existing_merge_target(self) -> None:
        class Native:
            def before_rename(self, old: str, new: str, merge: bool = False) -> None:
                del old, new, merge

        class Extended(reservation.WarehouseReservationMixin, Native):
            pass

        with (
            patch.object(reservation.frappe.db, "exists", return_value=True),
            patch.object(reservation, "lock_warehouses") as lock,
            patch.object(reservation, "check_count_activation") as check,
        ):
            Extended().before_rename("OLD", "TARGET", True)
        lock.assert_called_once_with({"OLD", "TARGET"})
        check.assert_called_once_with({"OLD", "TARGET"})

    def test_warehouse_delete_preserves_native_checks_after_reservation(self) -> None:
        events: list[str] = []

        class Native:
            name = "OLD"

            def on_trash(self) -> None:
                events.append("native")

        class Extended(reservation.WarehouseReservationMixin, Native):
            pass

        with (
            patch.object(reservation, "lock_warehouses") as lock,
            patch.object(reservation, "check_count_activation") as check,
        ):
            Extended().on_trash()
        lock.assert_called_once_with(("OLD",))
        check.assert_called_once_with({"OLD"})
        self.assertEqual(events, ["native"])

    def test_initial_install_preflight_requires_active_physical_reposts_to_drain(self) -> None:
        with (
            patch.object(reservation.frappe.db, "table_exists", side_effect=[True, False]),
            patch.object(reservation.frappe, "get_all", return_value=["RIV-1"]),
            self.assertRaises(frappe.ValidationError),
        ):
            reservation.preflight()

    def test_migration_preflight_rechecks_exact_active_scope(self) -> None:
        riv = Document({"doctype": "Repost Item Valuation", "name": "RIV-1"})
        with (
            patch.object(reservation.frappe.db, "table_exists", return_value=True),
            patch.object(reservation.frappe.db, "exists", return_value=True),
            patch.object(reservation.frappe, "get_all", return_value=["RIV-1"]),
            patch.object(reservation.frappe, "get_doc", return_value=riv),
            patch.object(reservation, "assert_current_scope") as check,
        ):
            reservation.preflight()
        check.assert_called_once_with(riv)

    def test_migration_preflight_refuses_overlapping_active_reservations(self) -> None:
        docs = {
            "RIV-1": Document({"doctype": "Repost Item Valuation", "name": "RIV-1"}),
            "RIV-2": Document({"doctype": "Repost Item Valuation", "name": "RIV-2"}),
        }
        with (
            patch.object(reservation.frappe.db, "table_exists", return_value=True),
            patch.object(reservation.frappe.db, "exists", return_value=True),
            patch.object(reservation.frappe, "get_all", return_value=["RIV-1", "RIV-2"]),
            patch.object(reservation.frappe, "get_doc", side_effect=lambda _dt, name: docs[name]),
            patch.object(reservation, "assert_current_scope", side_effect=[{"WH-1"}, {"WH-1"}]),
            self.assertRaisesRegex(frappe.ValidationError, "overlap"),
        ):
            reservation.preflight()
