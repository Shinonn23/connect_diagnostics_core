# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import add_payroll_entry_approval_controls as migration


def _doc(value: dict[str, Any]) -> Any:
    result = frappe._dict(value)
    for fieldname in ("states", "transitions", "tasks"):
        if result.get(fieldname):
            result[fieldname] = [frappe._dict(row) for row in result[fieldname]]
    return result


class TestPayrollEntryApprovalMigration(UnitTestCase):
    def test_canonical_permission_install_preserves_workflow_and_native_manager(self) -> None:
        workflow = _doc(migration._desired_workflow())

        def get_all(doctype: str, **kwargs: Any) -> list[Any]:
            if doctype == "Workflow":
                return [migration.WORKFLOW]
            return []

        manager = ((0, 0, 0, 1, 1, 1, 1, 1),)
        with (
            patch.object(migration.frappe, "get_all", side_effect=get_all),
            patch.object(migration.frappe.db, "exists", return_value=True),
            patch.object(migration.frappe, "get_doc", return_value=workflow) as get_doc,
            patch.object(migration, "_hr_manager_permissions", return_value=manager) as manager_permissions,
            patch.object(migration, "_ensure_permissions") as ensure_permissions,
        ):
            migration.ensure_canonical_permissions()

        get_doc.assert_called_once_with("Workflow", migration.WORKFLOW)
        self.assertEqual(manager_permissions.call_count, 2)
        ensure_permissions.assert_called_once_with()

    def test_canonical_permission_install_rejects_collisions_before_writes(self) -> None:
        workflow = _doc(migration._desired_workflow())
        exact = frappe._dict(
            permlevel=0,
            if_owner=0,
            **migration._permission_values("HR User"),
        )
        wrong_level = frappe._dict(exact)
        wrong_level.permlevel = 1
        wrong_right = frappe._dict(exact)
        wrong_right.submit = 1
        for active, current, rows in (
            (["Other Workflow"], workflow, []),
            ([migration.WORKFLOW, "Other Workflow"], workflow, []),
            ([migration.WORKFLOW], _doc(migration.LEGACY_WORKFLOW), []),
            ([migration.WORKFLOW], workflow, [exact, exact]),
            ([migration.WORKFLOW], workflow, [wrong_level]),
            ([migration.WORKFLOW], workflow, [wrong_right]),
        ):
            with (
                self.subTest(active=active, rows=rows),
                patch.object(
                    migration.frappe,
                    "get_all",
                    side_effect=lambda dt, **kwargs: active if dt == "Workflow" else rows,
                ),
                patch.object(migration.frappe.db, "exists", return_value=True),
                patch.object(migration.frappe, "get_doc", return_value=current),
                patch.object(migration, "_ensure_permissions") as ensure_permissions,
                self.assertRaises(frappe.ValidationError),
            ):
                migration.ensure_canonical_permissions()
            ensure_permissions.assert_not_called()

    def test_canonical_permission_install_requires_native_manager(self) -> None:
        with (
            patch.object(
                migration.frappe,
                "get_all",
                side_effect=lambda dt, **kwargs: [migration.WORKFLOW] if dt == "Workflow" else [],
            ),
            patch.object(migration.frappe.db, "exists", return_value=True),
            patch.object(migration.frappe, "get_doc", return_value=_doc(migration._desired_workflow())),
            patch.object(migration, "_hr_manager_permissions", return_value=()),
            patch.object(migration, "_ensure_permissions") as ensure_permissions,
            self.assertRaises(frappe.ValidationError),
        ):
            migration.ensure_canonical_permissions()
        ensure_permissions.assert_not_called()

    def test_canonical_permission_install_rejects_broad_native_target_before_copy(self) -> None:
        for right in ("submit", "import", "select", "mask"):
            native_broad = frappe._dict(
                permlevel=0,
                if_owner=0,
                **{**migration._permission_values("HR User"), right: 1},
            )

            def get_all(doctype: str, **kwargs: Any) -> list[Any]:
                if doctype == "Workflow":
                    return [migration.WORKFLOW]
                if doctype == "DocPerm" and kwargs["filters"]["role"] == "HR User":
                    return [native_broad]
                return []

            with (
                self.subTest(right=right),
                patch.object(migration.frappe, "get_all", side_effect=get_all),
                patch.object(migration.frappe.db, "exists", return_value=True),
                patch.object(migration.frappe, "get_doc", return_value=_doc(migration._desired_workflow())),
                patch.object(migration, "setup_custom_perms") as copy_native,
                patch.object(migration, "_ensure_permissions") as ensure_permissions,
                self.assertRaises(frappe.ValidationError),
            ):
                migration.ensure_canonical_permissions()
            copy_native.assert_not_called()
            ensure_permissions.assert_not_called()

    def test_permission_install_copies_native_before_adding_only_target_rows(self) -> None:
        inserted = MagicMock()
        with (
            patch.object(migration, "setup_custom_perms") as copy_native,
            patch.object(migration, "_permission_rows", return_value=[]),
            patch.object(migration.frappe, "get_doc", return_value=inserted) as get_doc,
            patch.object(migration.frappe, "clear_cache") as clear_cache,
        ):
            migration._ensure_permissions()
        copy_native.assert_called_once_with(migration.DOCTYPE)
        self.assertEqual(get_doc.call_count, len(migration.PAYROLL_ENTRY_PERMISSIONS))
        for call_args in get_doc.call_args_list:
            row = call_args.args[0]
            self.assertIn(row["role"], migration.PAYROLL_ENTRY_PERMISSIONS)
            self.assertEqual(
                {field: row[field] for field in migration.PERMISSION_FIELDS},
                migration._permission_values(row["role"]),
            )
        self.assertEqual(inserted.insert.call_count, len(migration.PAYROLL_ENTRY_PERMISSIONS))
        clear_cache.assert_called_once_with(doctype=migration.DOCTYPE)

    def test_permission_install_reuses_exact_existing_target_rows(self) -> None:
        with (
            patch.object(migration, "setup_custom_perms") as copy_native,
            patch.object(
                migration,
                "_permission_rows",
                side_effect=lambda role: [frappe._dict(name="EXACT", **migration._permission_values(role))],
            ),
            patch.object(migration.frappe, "get_doc") as get_doc,
            patch.object(migration.frappe, "clear_cache") as clear_cache,
        ):
            migration._ensure_permissions()
        copy_native.assert_called_once_with(migration.DOCTYPE)
        get_doc.assert_not_called()
        clear_cache.assert_called_once_with(doctype=migration.DOCTYPE)

    def test_workflow_mode_accepts_absent_legacy_and_desired_only(self) -> None:
        with patch.object(migration.frappe.db, "exists", return_value=False):
            self.assertEqual(migration._workflow_mode(), "absent")
        for expected_mode, current in (
            ("legacy", _doc(migration.LEGACY_WORKFLOW)),
            ("desired", _doc(migration._desired_workflow())),
        ):
            with (
                self.subTest(expected_mode=expected_mode),
                patch.object(migration.frappe.db, "exists", return_value=True),
                patch.object(migration.frappe, "get_doc", return_value=current),
            ):
                self.assertEqual(migration._workflow_mode(), expected_mode)

        drifted = _doc(migration._desired_workflow())
        drifted.transitions[0].allowed = "System Manager"
        with (
            patch.object(migration.frappe.db, "exists", return_value=True),
            patch.object(migration.frappe, "get_doc", return_value=drifted),
            self.assertRaises(frappe.ValidationError),
        ):
            migration._workflow_mode()

    def test_master_task_and_field_collisions_fail_closed(self) -> None:
        state = next(iter(migration._state_records().values()))
        bad_state = _doc({**state, "style": "Danger"})
        with (
            patch.object(migration.frappe.db, "exists", return_value=True),
            patch.object(migration.frappe, "get_doc", return_value=bad_state),
            self.assertRaises(frappe.ValidationError),
        ):
            migration._validate_masters("Workflow State", {state["name"]: state})

        bad_task = _doc({"tasks": [{"task": "Wrong", "enabled": 1, "asynchronous": 0}]})
        with (
            patch.object(migration.frappe.db, "exists", return_value=True),
            patch.object(migration.frappe, "get_doc", return_value=bad_task),
            self.assertRaises(frappe.ValidationError),
        ):
            migration._validate_tasks()

        expected = migration._fields()[0]
        bad_field = frappe._dict(expected)
        bad_field.fieldtype = "Text"
        with (
            patch.object(migration, "_custom_field", return_value=bad_field),
            self.assertRaises(frappe.ValidationError),
        ):
            migration._validate_fields()

    def test_preflight_stops_other_workflow_actions_records_and_jobs(self) -> None:
        with patch.object(migration.frappe, "get_all", return_value=["Other Workflow"]):
            with self.assertRaises(frappe.ValidationError):
                migration._preflight()

        for results in (
            [[], ["WA-1"]],
            [[], [], [frappe._dict(name="PAY-1")]],
            [[], [], [], [frappe._dict(name="JOB-1")]],
        ):
            with (
                self.subTest(results=results),
                patch.object(migration, "_workflow_mode", return_value="legacy"),
                patch.object(migration, "_validate_masters"),
                patch.object(migration, "_validate_tasks"),
                patch.object(migration, "_validate_fields"),
                patch.object(migration, "_validate_permissions"),
                patch.object(migration.frappe, "get_all", side_effect=results),
            ):
                with self.assertRaises(frappe.ValidationError):
                    migration._preflight()

    def test_execute_performs_no_mutation_when_preflight_fails(self) -> None:
        with (
            patch.object(migration, "_preflight", side_effect=frappe.ValidationError),
            patch.object(migration, "_ensure_masters") as ensure_masters,
            patch.object(migration, "_ensure_tasks") as ensure_tasks,
            patch.object(migration, "_ensure_fields") as ensure_fields,
            patch.object(migration, "_ensure_permissions") as ensure_permissions,
            patch.object(migration, "_replace_workflow") as replace,
            self.assertRaises(frappe.ValidationError),
        ):
            migration.execute()
        ensure_masters.assert_not_called()
        ensure_tasks.assert_not_called()
        ensure_fields.assert_not_called()
        ensure_permissions.assert_not_called()
        replace.assert_not_called()

    def test_execute_upgrades_legacy_and_repairs_desired_companions(self) -> None:
        with (
            patch.object(migration, "_preflight", return_value="legacy"),
            patch.object(migration, "_state_records", return_value={}),
            patch.object(migration, "_action_records", return_value={}),
            patch.object(migration, "_ensure_masters") as ensure_masters,
            patch.object(migration, "_ensure_tasks") as ensure_tasks,
            patch.object(migration, "_ensure_fields") as ensure_fields,
            patch.object(migration, "_ensure_permissions") as ensure_permissions,
            patch.object(migration, "_replace_workflow") as replace,
        ):
            migration.execute()
        self.assertEqual(
            ensure_masters.call_args_list,
            [call("Workflow State", {}), call("Workflow Action Master", {})],
        )
        ensure_tasks.assert_called_once_with()
        ensure_fields.assert_called_once_with()
        ensure_permissions.assert_called_once_with()
        replace.assert_called_once_with(migration._desired_workflow())

        with (
            patch.object(migration, "_preflight", return_value="desired"),
            patch.object(migration, "_state_records", return_value={}),
            patch.object(migration, "_action_records", return_value={}),
            patch.object(migration, "_ensure_masters") as rerun_masters,
            patch.object(migration, "_ensure_tasks") as rerun_tasks,
            patch.object(migration, "_ensure_fields") as rerun_fields,
            patch.object(migration, "_ensure_permissions") as rerun_permissions,
            patch.object(migration, "_replace_workflow") as rerun_replace,
        ):
            migration.execute()
        self.assertEqual(
            rerun_masters.call_args_list,
            [call("Workflow State", {}), call("Workflow Action Master", {})],
        )
        rerun_tasks.assert_called_once_with()
        rerun_fields.assert_called_once_with()
        rerun_permissions.assert_called_once_with()
        rerun_replace.assert_not_called()

    def test_rollback_is_guarded_and_restores_only_legacy_shape(self) -> None:
        with (
            patch.object(migration, "_workflow_mode", return_value="desired"),
            patch.object(migration.frappe, "get_all", side_effect=[[], []]),
            patch.object(migration, "_remove_permissions") as remove_permissions,
            patch.object(migration, "_replace_workflow") as replace,
        ):
            migration.rollback()
        remove_permissions.assert_called_once_with()
        replace.assert_called_once_with(migration.LEGACY_WORKFLOW)

        with (
            patch.object(migration, "_workflow_mode", return_value="desired"),
            patch.object(migration.frappe, "get_all", return_value=["WA-1"]),
            patch.object(migration, "_replace_workflow") as history_replace,
            self.assertRaises(frappe.ValidationError),
        ):
            migration.rollback()
        history_replace.assert_not_called()

        with (
            patch.object(migration, "_workflow_mode", return_value="desired"),
            patch.object(migration.frappe, "get_all", side_effect=[[], ["PAY-1"]]),
            patch.object(migration, "_replace_workflow") as used_replace,
            self.assertRaises(frappe.ValidationError),
        ):
            migration.rollback()
        used_replace.assert_not_called()

    def test_ensure_tasks_and_fields_create_exact_records(self) -> None:
        inserted = MagicMock()
        with (
            patch.object(migration.frappe.db, "exists", return_value=False),
            patch.object(migration.frappe, "get_doc", return_value=inserted),
        ):
            migration._ensure_tasks()
        self.assertEqual(inserted.insert.call_count, len(migration.TASKS))

        with patch.object(migration, "create_custom_fields") as create:
            migration._ensure_fields()
        create.assert_called_once_with(
            {migration.DOCTYPE: migration._fields()}, update=True, ignore_validate=True
        )

    def test_permissions_fail_closed_and_are_reversible(self) -> None:
        desired = frappe._dict(name="PERM-1", **migration._permission_values("HR User"))
        with (
            patch.object(migration, "_permission_rows", return_value=[desired, desired]),
            self.assertRaises(frappe.ValidationError),
        ):
            migration._validate_permissions("desired")

        drifted = frappe._dict(desired)
        drifted.submit = 1
        with (
            patch.object(migration, "_permission_rows", return_value=[drifted]),
            self.assertRaises(frappe.ValidationError),
        ):
            migration._validate_permissions("desired")

        with (
            patch.object(migration, "_permission_rows", return_value=[desired]),
            self.assertRaises(frappe.ValidationError),
        ):
            migration._validate_permissions("legacy")

        rows = {
            role: [frappe._dict(name=f"PERM-{index}", **migration._permission_values(role))]
            for index, role in enumerate(migration.PAYROLL_ENTRY_PERMISSIONS, start=1)
        }
        with (
            patch.object(migration, "_permission_rows", side_effect=lambda role: rows[role]),
            patch.object(migration.frappe, "delete_doc") as delete_doc,
            patch.object(migration.frappe, "clear_cache") as clear_cache,
        ):
            migration._remove_permissions()
        self.assertEqual(
            delete_doc.call_args_list,
            [
                call("Custom DocPerm", "PERM-1", force=True, ignore_permissions=True),
                call("Custom DocPerm", "PERM-2", force=True, ignore_permissions=True),
            ],
        )
        clear_cache.assert_called_once_with(doctype=migration.DOCTYPE)
