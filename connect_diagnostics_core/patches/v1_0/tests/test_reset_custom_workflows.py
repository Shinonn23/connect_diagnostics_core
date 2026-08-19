# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import reset_custom_workflows as patch_module


class TestResetCustomWorkflows(UnitTestCase):
    def test_workflow_name_lists_are_complete_and_unique(self) -> None:
        self.assertEqual(len(patch_module.WORKFLOW_NAMES), 11)
        for names in (
            patch_module.WORKFLOW_NAMES,
            patch_module.WORKFLOW_STATE_NAMES,
            patch_module.WORKFLOW_ACTION_NAMES,
        ):
            self.assertEqual(len(names), len(set(names)))

    def test_deletes_present_workflows_after_deactivating_them(self) -> None:
        deleted: list[tuple[str, str]] = []
        present = {("Workflow", name) for name in patch_module.WORKFLOW_NAMES[:2]}

        def fake_exists(doctype: str, name: object) -> bool:
            # Only the first two workflows exist; no masters are present.
            return (doctype, name) in present

        def fake_delete(doctype: str, name: str, **_kwargs: object) -> None:
            deleted.append((doctype, name))
            present.discard((doctype, name))

        with (
            patch.object(patch_module.frappe.db, "exists", side_effect=fake_exists),
            patch.object(patch_module.frappe.db, "set_value") as set_value,
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(patch_module.frappe, "delete_doc", side_effect=fake_delete),
        ):
            patch_module.execute()

        self.assertEqual(deleted, [("Workflow", name) for name in patch_module.WORKFLOW_NAMES[:2]])
        for name in patch_module.WORKFLOW_NAMES[:2]:
            set_value.assert_any_call("Workflow", name, "is_active", 0)

    def test_keeps_masters_still_referenced_by_a_surviving_workflow(self) -> None:
        state = patch_module.WORKFLOW_STATE_NAMES[0]
        action = patch_module.WORKFLOW_ACTION_NAMES[0]

        def fake_exists(doctype: str, name: object) -> bool:
            if doctype == "Workflow":
                return False  # all app workflows already gone
            if doctype in ("Workflow State", "Workflow Action Master"):
                return name in (state, action)
            # Guard lookups: the state/action are still referenced elsewhere.
            if doctype == "Workflow Document State":
                return True
            if doctype == "Workflow Transition":
                return True
            return False

        with (
            patch.object(patch_module.frappe.db, "exists", side_effect=fake_exists),
            patch.object(patch_module.frappe.db, "set_value"),
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(patch_module.frappe, "delete_doc") as delete_doc,
        ):
            patch_module.execute()

        delete_doc.assert_not_called()

    def test_raises_when_a_workflow_survives_deletion(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe.db, "set_value"),
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(patch_module.frappe, "delete_doc", MagicMock()),
        ):
            with self.assertRaises(frappe.ValidationError):
                patch_module.execute()
