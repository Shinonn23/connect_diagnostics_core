# Copyright (c) 2026, Siwat Sroisuwan and contributors

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import consolidate_stock_entry_workflow as patch_module


class TestConsolidateStockEntryWorkflow(UnitTestCase):
    def test_forward_converges_both_workflows(self) -> None:
        writes: list[tuple[str, str, int]] = []

        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(
                patch_module.frappe.db,
                "set_value",
                side_effect=lambda doctype, name, field, value, **kwargs: writes.append(
                    (doctype, name, value)
                ),
            ),
            patch.object(patch_module.frappe.db, "commit"),
        ):
            patch_module.execute()

        self.assertEqual(
            writes,
            [
                ("Workflow", patch_module.CANONICAL_WORKFLOW, 1),
                ("Workflow", patch_module.LEGACY_WORKFLOW, 0),
            ],
        )

    def test_rollback_only_reverses_expected_consolidated_state(self) -> None:
        values = iter([1, 0])
        writes: list[tuple[str, str, int]] = []

        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe.db, "get_value", side_effect=lambda *args: next(values)),
            patch.object(
                patch_module.frappe.db,
                "set_value",
                side_effect=lambda doctype, name, field, value, **kwargs: writes.append(
                    (doctype, name, value)
                ),
            ),
            patch.object(patch_module.frappe.db, "commit"),
        ):
            patch_module.rollback()

        self.assertEqual(
            writes,
            [
                ("Workflow", patch_module.CANONICAL_WORKFLOW, 0),
                ("Workflow", patch_module.LEGACY_WORKFLOW, 1),
            ],
        )

    def test_rollback_does_not_override_newer_configuration(self) -> None:
        values = iter([0, 1])
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe.db, "get_value", side_effect=lambda *args: next(values)),
            patch.object(patch_module.frappe.db, "set_value") as set_value,
            patch.object(patch_module.frappe.db, "commit") as commit,
        ):
            patch_module.rollback()

        set_value.assert_not_called()
        commit.assert_not_called()
