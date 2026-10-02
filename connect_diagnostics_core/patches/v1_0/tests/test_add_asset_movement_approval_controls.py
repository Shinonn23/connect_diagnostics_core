# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import add_asset_movement_approval_controls as migration


def _doc(value: dict) -> frappe._dict:
    result = frappe._dict(value)
    for fieldname in ("states", "transitions", "tasks"):
        if result.get(fieldname):
            result[fieldname] = [frappe._dict(row) for row in result[fieldname]]
    return result


class TestAssetMovementApprovalMigration(UnitTestCase):
    def test_declared_legacy_shape_is_exact(self) -> None:
        states = migration.LEGACY_WORKFLOW["states"]
        transitions = migration.LEGACY_WORKFLOW["transitions"]
        assert isinstance(states, list)
        assert isinstance(transitions, list)
        self.assertEqual(len(states), 6)
        self.assertEqual(len(transitions), 7)
        self.assertEqual(
            (
                transitions[-2][0],
                transitions[-2][2],
                transitions[-2][4],
                transitions[-2][6],
            ),
            (
                "Post Asset Movement",
                "Accounts Manager",
                "Asset Movement Submitted",
                "Asset Movement Approved",
            ),
        )

    def test_workflow_mode_accepts_absent_legacy_and_desired_only(self) -> None:
        desired = migration._desired_workflow()
        states = migration.LEGACY_WORKFLOW["states"]
        transitions = migration.LEGACY_WORKFLOW["transitions"]
        assert isinstance(states, list)
        assert isinstance(transitions, list)
        legacy = _doc(
            {
                **migration.LEGACY_WORKFLOW,
                "states": [dict(zip(migration._STATE_KEYS, row, strict=True)) for row in states],
                "transitions": [
                    dict(zip(migration._TRANSITION_KEYS, row, strict=True)) for row in transitions
                ],
            }
        )
        with patch.object(migration.frappe.db, "exists", return_value=False):
            self.assertEqual(migration._workflow_mode(), "absent")
        for expected_mode, current in (("legacy", legacy), ("desired", _doc(desired))):
            with (
                self.subTest(expected_mode=expected_mode),
                patch.object(migration.frappe.db, "exists", return_value=True),
                patch.object(migration.frappe, "get_doc", return_value=current),
            ):
                self.assertEqual(migration._workflow_mode(), expected_mode)

        third = _doc(desired)
        third_states = third.get("states")
        assert isinstance(third_states, list)
        third_states[0].allow_edit = "System Manager"
        with (
            patch.object(migration.frappe.db, "exists", return_value=True),
            patch.object(migration.frappe, "get_doc", return_value=third),
        ):
            with self.assertRaises(frappe.ValidationError):
                migration._workflow_mode()

    def test_master_task_and_custom_field_collisions_fail_closed(self) -> None:
        state = next(iter(migration._desired_state_records().values()))
        bad_state = _doc({**state, "style": "Danger"})
        with (
            patch.object(migration.frappe.db, "exists", return_value=True),
            patch.object(migration.frappe, "get_doc", return_value=bad_state),
        ):
            with self.assertRaises(frappe.ValidationError):
                migration._validate_masters("Workflow State", {state["name"]: state})

        bad_task = _doc({"tasks": [{"task": "Wrong", "enabled": 1, "asynchronous": 0}]})
        with (
            patch.object(migration.frappe.db, "exists", return_value=True),
            patch.object(migration.frappe, "get_doc", return_value=bad_task),
        ):
            with self.assertRaises(frappe.ValidationError):
                migration._validate_tasks()

        expected = migration.CUSTOM_FIELDS["Asset Movement"][0]
        bad_field = frappe._dict(expected)
        bad_field.fieldtype = "Data"
        with patch.object(migration, "_custom_field", return_value=bad_field):
            with self.assertRaises(frappe.ValidationError):
                migration._validate_custom_fields()

    def test_preflight_rejects_other_active_workflow_and_open_actions(self) -> None:
        with patch.object(migration.frappe, "get_all", return_value=["Other Workflow"]):
            with self.assertRaises(frappe.ValidationError):
                migration._preflight()

        with (
            patch.object(migration.frappe, "get_all", side_effect=[[], ["OPEN-1"]]),
            patch.object(migration, "_workflow_mode", return_value="legacy"),
            patch.object(migration, "_validate_masters"),
            patch.object(migration, "_validate_tasks"),
            patch.object(migration, "_validate_custom_fields"),
        ):
            with self.assertRaises(frappe.ValidationError):
                migration._preflight()

    def test_execute_performs_no_mutation_when_preflight_fails(self) -> None:
        with (
            patch.object(migration, "_preflight", side_effect=frappe.ValidationError),
            patch.object(migration, "_ensure_masters") as ensure_masters,
            patch.object(migration, "_ensure_tasks") as ensure_tasks,
            patch.object(migration, "_ensure_custom_fields") as ensure_fields,
            patch.object(migration, "_replace_workflow") as replace,
        ):
            with self.assertRaises(frappe.ValidationError):
                migration.execute()
        ensure_masters.assert_not_called()
        ensure_tasks.assert_not_called()
        ensure_fields.assert_not_called()
        replace.assert_not_called()

    def test_execute_upgrades_legacy_and_desired_rerun_is_noop(self) -> None:
        with (
            patch.object(migration, "_preflight", return_value="legacy"),
            patch.object(migration, "_desired_state_records", return_value={}),
            patch.object(migration, "_desired_action_records", return_value={}),
            patch.object(migration, "_ensure_masters") as ensure_masters,
            patch.object(migration, "_ensure_tasks") as ensure_tasks,
            patch.object(migration, "_ensure_custom_fields") as ensure_fields,
            patch.object(migration, "_replace_workflow") as replace,
        ):
            migration.execute()
        self.assertEqual(
            ensure_masters.call_args_list,
            [call("Workflow State", {}), call("Workflow Action Master", {})],
        )
        ensure_tasks.assert_called_once_with()
        ensure_fields.assert_called_once_with()
        replace.assert_called_once_with(migration._desired_workflow())

        with (
            patch.object(migration, "_preflight", return_value="desired"),
            patch.object(migration, "_desired_state_records", return_value={}),
            patch.object(migration, "_desired_action_records", return_value={}),
            patch.object(migration, "_ensure_masters"),
            patch.object(migration, "_ensure_tasks"),
            patch.object(migration, "_ensure_custom_fields"),
            patch.object(migration, "_replace_workflow") as rerun_replace,
            patch.object(migration.frappe, "get_doc") as get_doc,
        ):
            migration.execute()
        rerun_replace.assert_not_called()
        get_doc.assert_not_called()

    def test_ensure_tasks_and_fields_create_only_missing_records(self) -> None:
        inserted = MagicMock()
        with (
            patch.object(migration.frappe.db, "exists", return_value=False),
            patch.object(migration.frappe, "get_doc", return_value=inserted),
        ):
            migration._ensure_tasks()
        self.assertEqual(inserted.insert.call_count, len(migration.TASKS))

        expected = migration.CUSTOM_FIELDS["Asset Movement"]
        with (
            patch.object(migration, "_custom_field", return_value=None),
            patch.object(migration, "create_custom_fields") as create,
        ):
            migration._ensure_custom_fields()
        create.assert_called_once_with({"Asset Movement": expected}, ignore_validate=True)

    def test_replace_workflow_does_not_copy_fixture_metadata(self) -> None:
        workflow = MagicMock()
        record = {**migration._desired_workflow(), "modified": "stale", "owner": "fixture-owner"}
        with patch.object(migration.frappe, "get_doc", return_value=workflow):
            migration._replace_workflow(record)
        payload = workflow.update.call_args.args[0]
        self.assertEqual(set(payload), set(migration._WORKFLOW_UPDATE_KEYS))
        self.assertNotIn("modified", payload)
        self.assertNotIn("owner", payload)
        workflow.save.assert_called_once_with(ignore_permissions=True)

    def test_rollback_is_guarded_and_preserves_configuration_records(self) -> None:
        with (
            patch.object(migration, "_preflight", return_value="desired"),
            patch.object(migration.frappe, "get_all", return_value=[]),
            patch.object(migration, "_replace_workflow") as replace,
            patch.object(migration.frappe.db, "delete") as delete,
        ):
            migration.rollback()
        replacement = replace.call_args.args[0]
        self.assertEqual(migration._workflow_shape(replacement), migration.LEGACY_WORKFLOW)
        delete.assert_not_called()

        with (
            patch.object(migration, "_preflight", return_value="desired"),
            patch.object(migration.frappe, "get_all", return_value=["AM-1"]),
        ):
            with self.assertRaises(frappe.ValidationError):
                migration.rollback()

        with (
            patch.object(migration, "_preflight", side_effect=frappe.ValidationError),
            patch.object(migration, "_replace_workflow") as drifted_replace,
        ):
            with self.assertRaises(frappe.ValidationError):
                migration.rollback()
        drifted_replace.assert_not_called()
