# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import remove_legacy_workflow_revise_actions as patch_module


class TestRemoveLegacyWorkflowReviseActions(UnitTestCase):
    def test_deletes_only_retired_action_masters(self) -> None:
        deleted: list[tuple[str, dict[str, str]]] = []

        with (
            patch.object(
                patch_module.frappe.db,
                "delete",
                side_effect=lambda doctype, filters: deleted.append((doctype, filters)),
            ),
            patch.object(patch_module.frappe.db, "commit"),
        ):
            patch_module.execute()

        self.assertEqual(
            deleted,
            [("Workflow Action Master", {"name": name}) for name in patch_module.WORKFLOW_ACTION_NAMES],
        )

    def test_action_names_are_unique(self) -> None:
        self.assertEqual(
            len(patch_module.WORKFLOW_ACTION_NAMES), len(set(patch_module.WORKFLOW_ACTION_NAMES))
        )
