# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import add_stock_transfer_approval_controls as patch_module


class TestAddStockTransferApprovalControls(UnitTestCase):
    def test_collision_stops_only_the_owned_route(self) -> None:
        with (
            patch.object(
                patch_module.frappe,
                "get_all",
                return_value=["Unrelated Stock Entry Workflow"],
            ),
            patch.object(patch_module.frappe, "throw", side_effect=RuntimeError) as throw,
            self.assertRaises(RuntimeError),
        ):
            patch_module._validate_workflow_collision()

        throw.assert_called_once()

    @patch.object(patch_module, "create_custom_fields")
    def test_execute_is_additive_and_creates_exact_transition_tasks(
        self, create_custom_fields: MagicMock
    ) -> None:
        inserted: list[dict] = []

        def get_doc(value, *args):
            del args
            doc = MagicMock()
            doc.insert.side_effect = lambda **kwargs: inserted.append(value)
            return doc

        with (
            patch.object(patch_module.frappe, "get_all", return_value=[]),
            patch.object(patch_module.frappe.db, "exists", return_value=False),
            patch.object(patch_module.frappe.db, "get_value", return_value=None),
            patch.object(patch_module.frappe, "get_doc", side_effect=get_doc),
        ):
            patch_module.execute()

        create_custom_fields.assert_called_once()
        self.assertEqual(
            [row["name"] for row in inserted],
            list(patch_module.TASKS),
        )
        self.assertEqual(
            [row["tasks"][0]["task"] for row in inserted],
            list(patch_module.TASKS.values()),
        )
        create_custom_fields.assert_called_once_with(
            {"Stock Entry": patch_module.CUSTOM_FIELDS["Stock Entry"][-3:]},
            update=False,
            ignore_validate=True,
        )

    def test_incompatible_existing_custom_field_stops_migration(self) -> None:
        field = patch_module.CUSTOM_FIELDS["Stock Entry"][-3]
        existing = {property_name: field.get(property_name) for property_name in patch_module.FIELD_PROPERTIES}
        existing["fieldtype"] = "Long Text"
        with (
            patch.object(patch_module.frappe.db, "get_value", return_value=existing),
            patch.object(patch_module.frappe, "throw", side_effect=RuntimeError) as throw,
            self.assertRaises(RuntimeError),
        ):
            patch_module._validate_custom_field_collisions([field])

        throw.assert_called_once()

    def test_existing_exact_tasks_are_reused(self) -> None:
        task_doc = MagicMock()
        task_doc.tasks = [MagicMock(task="Capture Print Action: Checked", enabled=1, asynchronous=0)]
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe, "get_doc", return_value=task_doc),
        ):
            patch_module._ensure_transition_task(
                "Connect Stock Transfer Review Snapshot",
                "Capture Print Action: Checked",
            )

        task_doc.insert.assert_not_called()

    def test_conflicting_task_is_not_overwritten(self) -> None:
        task_doc = MagicMock()
        task_doc.tasks = [MagicMock(task="Different Task", enabled=1, asynchronous=0)]
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe, "get_doc", return_value=task_doc),
            patch.object(patch_module.frappe, "throw", side_effect=RuntimeError) as throw,
            self.assertRaises(RuntimeError),
        ):
            patch_module._ensure_transition_task(
                "Connect Stock Transfer Review Snapshot",
                "Capture Print Action: Checked",
            )

        throw.assert_called_once()

    def test_rollback_is_intentionally_non_destructive(self) -> None:
        self.assertIsNone(patch_module.rollback())
