# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import disable_equipment_assignment_workflow as patch_module


class TestDisableEquipmentAssignmentWorkflow(UnitTestCase):
    def test_disables_existing_workflow_without_deleting_records(self) -> None:
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
            [("Workflow", patch_module.WORKFLOW_NAME, 0)],
        )

    def test_is_idempotent_when_workflow_is_absent(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=False),
            patch.object(patch_module.frappe.db, "set_value") as set_value,
            patch.object(patch_module.frappe.db, "commit"),
        ):
            patch_module.execute()

        set_value.assert_not_called()
