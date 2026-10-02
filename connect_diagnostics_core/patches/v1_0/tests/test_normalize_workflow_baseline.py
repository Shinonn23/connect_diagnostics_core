# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core import hooks
from connect_diagnostics_core.patches.v1_0 import normalize_workflow_baseline as guard
from connect_diagnostics_core.patches.v1_0 import rollback_normalize_workflow_baseline as recovery


class TestNormalizeWorkflowBaseline(UnitTestCase):
    def test_v4_archive_matches_literal_snapshot_anchors(self) -> None:
        desired, states, actions = guard._blueprint()
        expected = {
            "Connect Asset Movement Approval": "d3ea3ffa11e19998adbd30711b32002daf452e46562b141052f6f76d65e9f802",
            "Connect Journal Entry Approval": "d1f2068b35354fae8436b5d1aafc4633f229e266fe7a611f3249ed73fb8ab887",
            "Connect Payment Entry Approval": "8d17caa3740ddc9d51ff4ae5fbb7333d88936b7edf581e3f783082966f564b4f",
            "Connect Payroll Entry Blueprint": "1ce1226a09541436854bdb7df4e94d1c0091b7a2127fe64f63ad98f23d4d03ce",
            "Connect Purchase Invoice Blueprint": "2e90c74d0de6faed16db19327511190a9d190e127b0508def2974fa80d46aab0",
            "Connect Purchase Order Blueprint": "79d0feb4739377982ab9df30cc4f65e727b5a74e7c516997d0f51cc21c39500e",
            "Connect Sales Invoice Credit Blueprint": "3a96f9a14eecca6ec7c17df363546e057b58bcf4d65603bf75f99f92cccdfc74",
            "Connect Sales Order Blueprint": "938b9bdf0facd8ff276041bde8bd3e82abe749417f0b8152440706e48663a622",
            "Connect Stock Reconciliation Blueprint": "2cac16c497c1030d65521061b2365a6b752171c8a143375bc0d622b55c4a6fc8",
            "Connect Stock Transfer Approval": "afe9edddc19ae9ed1f5f7eca0ef21af6f979541ae6856d2e9d0d63b9ef815107",
        }
        self.assertEqual({name: guard.workflow_fingerprint(row) for name, row in desired.items()}, expected)
        self.assertEqual(guard._archive()["desired_hashes"], expected)
        with patch.object(guard.frappe, "get_attr", return_value=lambda: None):
            groups = guard._task_blueprints(desired)
        self.assertEqual(len(groups), 63)
        self.assertEqual(
            guard._companion_hash(states, actions, groups),
            "751180bd31640c0fc8824b2cf1ea076047c0e070e494f53abce5ba330f03d1d2",
        )

    def test_fixture_and_export_filters_are_exact_without_disposal_retirement(self) -> None:
        desired, states, actions = guard._blueprint()
        self.assertEqual(set(desired), set(guard.CANONICAL_WORKFLOWS))
        self.assertNotIn("Connect Asset Disposal Blueprint", desired)
        for doctype, rows in (
            ("Workflow", desired),
            ("Workflow State", states),
            ("Workflow Action Master", actions),
        ):
            entry = next(row for row in hooks.fixtures if row["doctype"] == doctype)
            self.assertEqual(set(entry["filters"][0][2]), set(rows))
            self.assertEqual(len(entry["filters"][0][2]), len(rows))
        self.assertEqual(
            hooks.before_install[0],
            "connect_diagnostics_core.patches.v1_0.normalize_workflow_baseline.preflight",
        )
        self.assertEqual(
            hooks.before_migrate[0],
            "connect_diagnostics_core.patches.v1_0.upgrade_workflow_baseline_v5.preflight",
        )
        self.assertEqual(
            hooks.after_install[0],
            "connect_diagnostics_core.patches.v1_0.normalize_workflow_baseline.execute",
        )
        self.assertEqual(
            hooks.after_install[1],
            "connect_diagnostics_core.patches.v1_0.upgrade_workflow_baseline_v5.prepare",
        )

    def test_full_shape_tracks_status_email_expression_and_side_effects(self) -> None:
        desired = guard._desired_workflows()["Connect Sales Order Blueprint"]
        initial = guard.workflow_fingerprint(desired)
        variants = (
            ("parent", "workflow_state_field", "other_state"),
            ("state", "update_value", "approved"),
            ("state", "evaluate_as_expression", 1),
            ("state", "next_action_email_template", "Another Template"),
            ("transition", "send_email_to_creator", 1),
            ("transition", "transition_tasks", "Other Tasks"),
        )
        for section, field, value in variants:
            with self.subTest(section=section, field=field):
                changed = dict(desired)
                if section == "parent":
                    changed[field] = value
                else:
                    key = "states" if section == "state" else "transitions"
                    changed[key] = [dict(row) for row in desired[key]]
                    changed[key][0][field] = value
                self.assertNotEqual(guard.workflow_fingerprint(changed), initial)

    def test_sales_order_groups_capture_signatures_before_approval_callbacks(self) -> None:
        with patch.object(guard.frappe, "get_attr", return_value=lambda: None):
            groups = guard._task_blueprints(guard._desired_workflows())
        self.assertEqual(
            [row["task"] for row in groups["Connect Sales Order Capture Review"]],
            ["Capture Print Action: Checked", "Connect Sales Order Capture Review"],
        )
        self.assertEqual(
            [row["task"] for row in groups["Connect Sales Order Capture Approval"]],
            ["Capture Print Action: Authorized", "Connect Sales Order Capture Approval"],
        )
        for rows in groups.values():
            self.assertTrue(all(row["enabled"] == 1 and row["asynchronous"] == 0 for row in rows))
            self.assertTrue(all(row["link"] is None for row in rows))

    def _preflight_one_existing(self, rows: list[dict[str, Any]]) -> None:
        desired = guard._desired_workflows()
        target = "Connect Stock Transfer Approval"

        def exists(doctype: str, name: object) -> bool:
            return doctype == "Workflow" and name == target

        with (
            patch.object(guard.frappe, "get_all", return_value=[]),
            patch.object(guard.frappe.db, "exists", side_effect=exists),
            patch.object(guard.frappe.db, "get_value", return_value=None),
            patch.object(guard.frappe, "get_doc", return_value=desired[target]),
            patch.object(guard, "_business_rows", side_effect=lambda dt: rows if dt == "Stock Entry" else []),
            patch.object(guard, "_action_rows", return_value=[]),
        ):
            guard._preflight_site(desired, {}, {}, {})

    def test_all_business_rows_are_checked_including_later_pages(self) -> None:
        rows = [
            frappe._dict(name=f"SE-{index:03}", docstatus=0, workflow_state="Stock Transfer Draft")
            for index in range(5)
        ]
        rows[4].workflow_state = "Unknown State"

        def page(doctype: str, **kwargs: Any) -> list[Any]:
            self.assertEqual(doctype, "Stock Entry")
            self.assertEqual(kwargs["order_by"], "name asc")
            self.assertEqual(kwargs["limit_page_length"], 2)
            after = kwargs["filters"].get("name", [">", ""])[1]
            return [row for row in rows if row.name > after][:2]

        with (
            patch.object(guard, "HISTORY_PAGE_SIZE", 2),
            patch.object(guard.frappe.db, "has_column", return_value=True),
            patch.object(guard.frappe, "get_all", side_effect=page) as get_all,
            self.assertRaises(frappe.ValidationError),
        ):
            guard._history_fingerprint(guard._business_rows("Stock Entry"), {"Stock Transfer Draft": 0})
        self.assertGreaterEqual(get_all.call_count, 3)
        self.assertEqual(get_all.call_args_list[0].kwargs["filters"], {})
        self.assertEqual(get_all.call_args_list[1].kwargs["filters"], {"name": [">", "SE-001"]})
        self.assertEqual(get_all.call_args_list[2].kwargs["filters"], {"name": [">", "SE-003"]})

    def test_later_page_action_mutation_changes_history_fingerprint(self) -> None:
        rows = [
            frappe._dict(
                name=f"WA-{index:03}", reference_name=f"SE-{index:03}", status="Open", workflow_state="Draft"
            )
            for index in range(5)
        ]

        def page(doctype: str, **kwargs: Any) -> list[Any]:
            self.assertEqual(doctype, "Workflow Action")
            self.assertEqual(kwargs["order_by"], "name asc")
            self.assertEqual(kwargs["limit_page_length"], 2)
            self.assertEqual(kwargs["filters"]["reference_doctype"], "Stock Entry")
            after = kwargs["filters"].get("name", [">", ""])[1]
            return [row for row in rows if row.name > after][:2]

        with (
            patch.object(guard, "HISTORY_PAGE_SIZE", 2),
            patch.object(guard.frappe, "get_all", side_effect=page),
        ):
            initial = guard._history_fingerprint(guard._action_rows("Stock Entry"))
            rows[4].status = "Completed"
            changed = guard._history_fingerprint(guard._action_rows("Stock Entry"))
        self.assertEqual(initial["count"], 5)
        self.assertEqual(changed["count"], 5)
        self.assertNotEqual(initial["sha256"], changed["sha256"])

    def test_pagination_accepts_sql_collation_order_for_mixed_case_names(self) -> None:
        rows = [
            frappe._dict(name="a", reference_name="SE-1", status="Open", workflow_state="Draft"),
            frappe._dict(name="B", reference_name="SE-2", status="Open", workflow_state="Draft"),
        ]
        with (
            patch.object(guard, "HISTORY_PAGE_SIZE", 2),
            patch.object(guard.frappe, "get_all", side_effect=[rows, []]) as get_all,
        ):
            digest = guard._history_fingerprint(guard._action_rows("Stock Entry"))
        self.assertEqual(digest["count"], 2)
        self.assertEqual(get_all.call_args_list[1].kwargs["filters"]["name"], [">", "B"])

    def test_blank_state_and_wrong_docstatus_fail_closed(self) -> None:
        for state, status in (("", 0), ("Stock Transfer Submitted", 0)):
            with self.subTest(state=state, status=status), self.assertRaises(frappe.ValidationError):
                self._preflight_one_existing(
                    [{"name": "SE-ONE", "docstatus": status, "workflow_state": state}]
                )

    def test_existing_rows_without_state_column_stop_before_ddl(self) -> None:
        with (
            patch.object(guard.frappe.db, "has_column", return_value=False),
            patch.object(guard.frappe.db, "count", return_value=1),
            self.assertRaises(frappe.ValidationError),
        ):
            list(guard._business_rows("Journal Entry"))

    def test_missing_workflow_with_business_history_or_actions_stops(self) -> None:
        desired = guard._desired_workflows()
        for history, actions in (([{"name": "SE-ONE"}], []), ([], [{"name": "ACTION-ONE"}])):
            with (
                self.subTest(history=bool(history)),
                patch.object(guard.frappe, "get_all", return_value=[]),
                patch.object(guard.frappe.db, "exists", return_value=False),
                patch.object(
                    guard, "_business_rows", side_effect=lambda dt: history if dt == "Stock Entry" else []
                ),
                patch.object(
                    guard, "_action_rows", side_effect=lambda dt: actions if dt == "Stock Entry" else []
                ),
                self.assertRaises(frappe.ValidationError),
            ):
                guard._preflight_site(desired, {}, {}, {})

    def test_foreign_active_workflow_stops_before_snapshot(self) -> None:
        desired = guard._desired_workflows()
        with (
            patch.object(guard.frappe, "get_all", return_value=["Unreviewed Workflow"]),
            self.assertRaises(frappe.ValidationError),
        ):
            guard._preflight_site(desired, {}, {}, {})

    def test_companion_name_collision_stops_before_mutation(self) -> None:
        desired, states, _actions = guard._blueprint()
        name, state = next(iter(states.items()))
        foreign = dict(state, style="Danger" if state.get("style") != "Danger" else "Info")
        with (
            patch.object(guard.frappe, "get_all", return_value=[]),
            patch.object(
                guard.frappe.db,
                "exists",
                side_effect=lambda dt, key: dt == "Workflow State" and key == name,
            ),
            patch.object(guard, "_business_rows", return_value=[]),
            patch.object(guard, "_action_rows", return_value=[]),
            patch.object(guard.frappe, "get_doc", return_value=foreign),
            self.assertRaises(frappe.ValidationError),
        ):
            guard._preflight_site(desired, {name: state}, {}, {})

    def test_unresolved_callback_stops_preparation(self) -> None:
        with (
            patch.object(guard.frappe, "get_attr", side_effect=ImportError("missing callback")),
            self.assertRaises(ImportError),
        ):
            guard._task_blueprints(guard._desired_workflows())

    def test_existing_unreviewed_workflow_stops_before_snapshot_or_fields(self) -> None:
        with (
            patch.object(guard, "_blueprint", return_value=({}, {}, {})),
            patch.object(guard, "_task_blueprints", return_value={}),
            patch.object(guard, "_preflight_site", side_effect=frappe.ValidationError("collision")),
            patch.object(guard, "_save_snapshot") as snapshot,
            patch.object(guard, "create_custom_fields") as fields,
            self.assertRaises(frappe.ValidationError),
        ):
            guard.execute()
        snapshot.assert_not_called()
        fields.assert_not_called()

    def test_existing_group_is_never_overwritten(self) -> None:
        desired = guard._desired_workflows()
        name = "Connect Sales Order Capture Review"
        foreign = frappe._dict(tasks=[frappe._dict(task="Foreign Task", enabled=1, asynchronous=0)])
        with (
            patch.object(guard.frappe, "get_all", return_value=[]),
            patch.object(
                guard.frappe.db,
                "exists",
                side_effect=lambda dt, key: dt == "Workflow Transition Tasks" and key == name,
            ),
            patch.object(guard.frappe.db, "get_value", return_value=None),
            patch.object(guard.frappe, "get_doc", return_value=foreign),
            patch.object(guard, "_business_rows", return_value=[]),
            patch.object(guard, "_action_rows", return_value=[]),
            self.assertRaises(frappe.ValidationError),
        ):
            guard._preflight_site(
                desired, {}, {}, {name: [{"task": name, "link": None, "enabled": 1, "asynchronous": 0}]}
            )

    def test_snapshot_is_immutable_on_identical_rerun(self) -> None:
        saved = {
            "schema_version": guard.SNAPSHOT_VERSION,
            "desired_hashes": {"A": "hash"},
            "companion_hash": "companions",
        }
        file_doc = frappe._dict(get_content=lambda: __import__("json").dumps(saved))
        with (
            patch.object(guard.frappe.db, "exists", return_value="snapshot"),
            patch.object(guard.frappe, "get_doc", return_value=file_doc) as get_doc,
        ):
            guard._save_snapshot(dict(saved, missing_workflows=["A"]))
        get_doc.assert_called_once_with("File", "snapshot")
        with (
            patch.object(guard.frappe.db, "exists", return_value="snapshot"),
            patch.object(guard.frappe, "get_doc", return_value=file_doc),
            self.assertRaises(frappe.ValidationError),
        ):
            guard._save_snapshot(dict(saved, companion_hash="changed"))

    def test_repeated_preflight_refuses_changed_callback_revision(self) -> None:
        desired, states, actions = guard._blueprint()
        groups: dict[str, list[dict[str, Any]]] = {}
        saved = {
            "schema_version": guard.SNAPSHOT_VERSION,
            "desired_hashes": {name: guard.workflow_fingerprint(row) for name, row in desired.items()},
            "companion_hash": "previous-callback-revision",
        }
        file_doc = frappe._dict(get_content=lambda: __import__("json").dumps(saved))
        with (
            patch.object(guard.frappe.db, "exists", return_value="snapshot"),
            patch.object(guard.frappe, "get_doc", return_value=file_doc),
            self.assertRaises(frappe.ValidationError),
        ):
            guard._assert_snapshot_revision(desired, states, actions, groups)

    def test_identical_prepare_creates_only_missing_groups_without_rewriting_snapshot(self) -> None:
        desired = guard._desired_workflows()
        task = "Connect Sales Order Capture Maker"
        rows = [{"task": task, "link": None, "enabled": 1, "asynchronous": 0}]
        created = MagicMock()
        with (
            patch.object(guard, "_blueprint", return_value=(desired, {}, {})),
            patch.object(guard, "_task_blueprints", return_value={task: rows}),
            patch.object(guard, "_preflight_site") as site,
            patch.object(guard, "_snapshot_payload", return_value={"schema_version": guard.SNAPSHOT_VERSION}),
            patch.object(guard, "_save_snapshot") as snapshot,
            patch.object(guard.frappe.db, "exists", return_value=False),
            patch.object(guard.frappe, "get_doc", return_value=created) as get_doc,
            patch.object(guard, "create_custom_fields") as fields,
            patch.object(guard, "CUSTOM_FIELDS", {}),
        ):
            guard.execute()
        site.assert_called_once_with(desired, {}, {}, {task: rows})
        snapshot.assert_called_once_with({"schema_version": guard.SNAPSHOT_VERSION})
        fields.assert_not_called()
        get_doc.assert_called_once_with({"doctype": "Workflow Transition Tasks", "name": task, "tasks": rows})
        created.insert.assert_called_once_with(ignore_permissions=True)

    def test_read_only_preflight_cannot_mutate_site(self) -> None:
        with (
            patch.object(guard, "_blueprint", return_value=({}, {}, {})),
            patch.object(guard, "_task_blueprints", return_value={}),
            patch.object(guard, "_assert_snapshot_revision") as revision,
            patch.object(guard, "_preflight_site") as site,
            patch.object(guard, "_save_snapshot") as snapshot,
            patch.object(guard, "create_custom_fields") as fields,
        ):
            guard.preflight()
        revision.assert_called_once_with({}, {}, {}, {})
        site.assert_called_once_with({}, {}, {}, {})
        snapshot.assert_not_called()
        fields.assert_not_called()


class TestNormalizeWorkflowRecovery(UnitTestCase):
    def test_later_page_action_mutation_blocks_recovery(self) -> None:
        rows = [
            frappe._dict(
                name=f"WA-{index:03}", reference_name=f"SE-{index:03}", status="Open", workflow_state="Draft"
            )
            for index in range(5)
        ]

        def page(_doctype: str, **kwargs: Any) -> list[Any]:
            after = kwargs["filters"].get("name", [">", ""])[1]
            return [row for row in rows if row.name > after][:2]

        empty = guard._history_fingerprint(iter(()))
        with (
            patch.object(guard, "HISTORY_PAGE_SIZE", 2),
            patch.object(guard.frappe, "get_all", side_effect=page),
        ):
            initial = guard._history_fingerprint(guard._action_rows("Stock Entry"))
            rows[4].status = "Completed"
            snapshot = {
                "business_history": {doctype: empty for doctype in guard.CANONICAL_WORKFLOWS.values()},
                "action_history": {
                    doctype: initial if doctype == "Stock Entry" else empty
                    for doctype in guard.CANONICAL_WORKFLOWS.values()
                },
            }
            with (
                patch.object(recovery, "_business_rows", side_effect=lambda _dt: iter(())),
                patch.object(
                    recovery,
                    "_action_rows",
                    side_effect=lambda dt: guard._action_rows(dt) if dt == "Stock Entry" else iter(()),
                ),
                self.assertRaises(frappe.ValidationError),
            ):
                recovery._check_histories(snapshot)

    def test_foreign_reference_blocks_rollback_before_deletion(self) -> None:
        snapshot = {
            "missing_workflows": ["Connect Stock Transfer Approval"],
            "missing_groups": ["Connect Stock Transfer Maker Snapshot"],
            "missing_states": [],
            "missing_actions": [],
        }
        with (
            patch.object(recovery.frappe.db, "exists", return_value="foreign-transition") as exists,
            self.assertRaises(frappe.ValidationError),
        ):
            recovery._check_removal_references(snapshot)
        self.assertEqual(
            exists.call_args.args,
            (
                "Workflow Transition",
                {
                    "transition_tasks": "Connect Stock Transfer Maker Snapshot",
                    "parent": ["not in", ["Connect Stock Transfer Approval"]],
                },
            ),
        )

    def test_versioned_snapshot_rejects_legacy_shape(self) -> None:
        file_doc = frappe._dict(get_content=lambda: '{"schema_version": 2}')
        with (
            patch.object(recovery.frappe.db, "exists", return_value="snapshot"),
            patch.object(recovery.frappe, "get_doc", return_value=file_doc),
            self.assertRaises(frappe.ValidationError),
        ):
            recovery._snapshot()

    def test_new_business_history_blocks_rollback_before_deletion(self) -> None:
        desired, states, actions = guard._blueprint()
        empty = guard._history_fingerprint(iter(()))
        snapshot = {
            "desired_hashes": {name: guard.workflow_fingerprint(row) for name, row in desired.items()},
            "companion_hash": guard._companion_hash(states, actions, {}),
            "business_history": {doctype: empty for doctype in guard.CANONICAL_WORKFLOWS.values()},
            "action_history": {doctype: empty for doctype in guard.CANONICAL_WORKFLOWS.values()},
        }
        with (
            patch.object(recovery, "_snapshot", return_value=snapshot),
            patch.object(recovery, "_task_blueprints", return_value={}),
            patch.object(recovery, "_business_rows", return_value=[{"name": "NEW"}]),
            patch.object(recovery, "_remove_created") as remove,
            self.assertRaises(frappe.ValidationError),
        ):
            recovery.execute()
        remove.assert_not_called()

    def test_incomplete_recovery_refuses_partial_fixture_import(self) -> None:
        desired, states, actions = guard._blueprint()
        name = next(iter(desired))
        snapshot = {
            "desired_hashes": {key: guard.workflow_fingerprint(row) for key, row in desired.items()},
            "companion_hash": guard._companion_hash(states, actions, {}),
            "missing_workflows": [name],
        }
        with (
            patch.object(recovery, "_task_blueprints", return_value={}),
            patch.object(recovery, "_check_histories"),
            patch.object(recovery.frappe.db, "exists", return_value=True),
            self.assertRaises(frappe.ValidationError),
        ):
            recovery._preflight(snapshot, incomplete=True)

    def test_changed_post_configuration_blocks_rollback_before_deletion(self) -> None:
        desired, states, actions = guard._blueprint()
        groups: dict[str, list[dict[str, object]]] = {}
        empty = guard._history_fingerprint(iter(()))
        snapshot = {
            "desired_hashes": {name: guard.workflow_fingerprint(row) for name, row in desired.items()},
            "companion_hash": guard._companion_hash(states, actions, groups),
            "business_history": {doctype: empty for doctype in guard.CANONICAL_WORKFLOWS.values()},
            "action_history": {doctype: empty for doctype in guard.CANONICAL_WORKFLOWS.values()},
            "missing_workflows": [],
            "missing_states": [],
            "missing_actions": [],
            "missing_groups": [],
        }
        with (
            patch.object(recovery, "_snapshot", return_value=snapshot),
            patch.object(recovery, "_task_blueprints", return_value=groups),
            patch.object(recovery, "_business_rows", return_value=[]),
            patch.object(recovery, "_action_rows", return_value=[]),
            patch.object(recovery.frappe.db, "exists", return_value=True),
            patch.object(recovery.frappe, "get_doc", return_value=frappe._dict(name="changed")),
            patch.object(recovery, "_remove_created") as remove,
            self.assertRaises(frappe.ValidationError),
        ):
            recovery.execute()
        remove.assert_not_called()

    def test_completed_patch_log_does_not_block_pre_fixture_recovery(self) -> None:
        snapshot = {"missing_groups": []}
        with (
            patch.object(recovery.frappe.db, "exists", return_value=True),
            patch.object(recovery, "_snapshot", return_value=snapshot),
            patch.object(recovery, "_preflight") as preflight,
            patch.object(recovery, "_remove_created") as remove,
            patch.object(recovery, "_assert_recovered") as assert_recovered,
        ):
            recovery.recover_incomplete_apply()
        preflight.assert_called_once_with(snapshot, incomplete=True)
        remove.assert_called_once_with(snapshot, incomplete=True)
        assert_recovered.assert_called_once_with(snapshot, incomplete=True)
