# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""v5 Workflow configuration and installed-path rehearsal support."""

from __future__ import annotations

import copy
import json
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch
from uuid import uuid4

import frappe
from erpnext.accounts.party import get_party_account
from frappe import _
from frappe.core.doctype.file.file import File
from frappe.core.doctype.file.utils import get_content_hash
from frappe.core.doctype.user.user import User
from frappe.model.workflow import apply_workflow, get_transitions
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.workflow.doctype.workflow.workflow import Workflow

from connect_diagnostics_core.api.erpnext.tests.test_purchase_order_workflow_integration import (
    _draft_order,
    _ordered_qty,
)
from connect_diagnostics_core.patches.v1_0 import normalize_workflow_baseline as v4
from connect_diagnostics_core.patches.v1_0 import rollback_normalize_workflow_baseline as v4_recovery
from connect_diagnostics_core.patches.v1_0 import rollback_workflow_baseline_v5 as recovery
from connect_diagnostics_core.patches.v1_0 import upgrade_workflow_baseline_v5 as v5
from connect_diagnostics_core.setup import procure_to_pay

MAKER = "_test.po.v5.maker@example.com"
REVIEWER = "_test.po.v5.reviewer@example.com"
APPROVER = "_test.po.v5.approver@example.com"
RETURN_USER = "_test.po.v5.return@example.com"
REHEARSAL_MARKER = "PO-v5-native-return-rehearsal"
REHEARSAL_USERS = (MAKER, REVIEWER, APPROVER, RETURN_USER)
SIGNATURE = "data:image/svg+xml;base64,PHN2Zy8+"
AUTOMATIC_ROLES = {"All", "Guest", "Desk User", "Employee"}
EXPECTED_V5_HASHES = {
    "Connect Asset Movement Approval": "d3ea3ffa11e19998adbd30711b32002daf452e46562b141052f6f76d65e9f802",
    "Connect Journal Entry Approval": "d1f2068b35354fae8436b5d1aafc4633f229e266fe7a611f3249ed73fb8ab887",
    "Connect Payment Entry Approval": "8d17caa3740ddc9d51ff4ae5fbb7333d88936b7edf581e3f783082966f564b4f",
    "Connect Payroll Entry Blueprint": "1ce1226a09541436854bdb7df4e94d1c0091b7a2127fe64f63ad98f23d4d03ce",
    "Connect Purchase Invoice Blueprint": "2e90c74d0de6faed16db19327511190a9d190e127b0508def2974fa80d46aab0",
    "Connect Purchase Order Blueprint": "bc27869de8fa4d0f78541667336fc8b3fef885e934b84b7b1dcf979dc1549c64",
    "Connect Sales Invoice Credit Blueprint": "3a96f9a14eecca6ec7c17df363546e057b58bcf4d65603bf75f99f92cccdfc74",
    "Connect Sales Order Blueprint": "938b9bdf0facd8ff276041bde8bd3e82abe749417f0b8152440706e48663a622",
    "Connect Stock Reconciliation Blueprint": "2cac16c497c1030d65521061b2365a6b752171c8a143375bc0d622b55c4a6fc8",
    "Connect Stock Transfer Approval": "afe9edddc19ae9ed1f5f7eca0ef21af6f979541ae6856d2e9d0d63b9ef815107",
}


def _create_actor(user: str, roles: tuple[str, ...]) -> None:
    if frappe.db.exists("User", user) or frappe.db.exists("Employee", {"user_id": user}):
        frappe.throw(_("A dedicated v5 rehearsal identity already exists; inspect it before retry."))
    frappe.get_doc(
        {
            "doctype": "User",
            "email": user,
            "first_name": user,
            "send_welcome_email": 0,
            "user_type": "System User",
            "roles": [{"role": role} for role in roles],
        }
    ).insert(ignore_permissions=True)
    department = frappe.db.get_value("Department", {"company": "_Test Company"}, "name")
    employment_type = frappe.db.get_value("Employment Type", {}, "name")
    if not department or not employment_type:
        frappe.throw(_("Employee prerequisites for the v5 rehearsal are unavailable."))
    frappe.get_doc(
        {
            "doctype": "Employee",
            "first_name": user,
            "company": "_Test Company",
            "department": department,
            "gender": "Female",
            "date_of_birth": "1990-05-08",
            "date_of_joining": "2020-01-01",
            "status": "Active",
            "employment_type": employment_type,
            "user_id": user,
            "company_email": user,
            "approval_signature": SIGNATURE,
        }
    ).insert(ignore_permissions=True)
    frappe.clear_cache(user=user)


def _assert_return_roles() -> None:
    configured = {row.role for row in cast(User, frappe.get_doc("User", RETURN_USER)).roles}
    effective = set(frappe.get_roles(RETURN_USER))
    if configured - {"Employee"} != {"C-Level Approver"} or effective - AUTOMATIC_ROLES != {
        "C-Level Approver"
    }:
        frappe.throw(_("The v5 Return actor has an unexpected business role."))
    if "System Manager" in effective:
        frappe.throw(_("The v5 Return actor must not have System Manager."))


def _cleanup_rehearsal(name: str) -> None:
    if frappe.db.get_value("Purchase Order", name, "title") != REHEARSAL_MARKER:
        frappe.throw(_("The Purchase Order is not owned by the v5 rehearsal."))
    employee_names: dict[str, str] = {}
    for user in REHEARSAL_USERS:
        actor = frappe.db.get_value("User", user, ["email", "first_name"], as_dict=True)
        employees = frappe.get_all(
            "Employee", filters={"user_id": user}, fields=["name", "first_name", "user_id", "company"]
        )
        if (
            not actor
            or actor.email != user
            or actor.first_name != user
            or len(employees) != 1
            or employees[0].first_name != user
            or employees[0].user_id != user
            or employees[0].company != "_Test Company"
        ):
            frappe.throw(_("A v5 rehearsal actor or Employee has unexpected ownership."))
        employee_names[user] = str(employees[0].name)

    permissions = frappe.get_all(
        "User Permission",
        filters={"user": ["in", list(REHEARSAL_USERS)]},
        fields=[
            "name",
            "user",
            "allow",
            "for_value",
            "applicable_for",
            "apply_to_all_doctypes",
            "is_default",
            "hide_descendants",
        ],
    )
    permission_names: list[str] = []
    for user in REHEARSAL_USERS:
        rows = [row for row in permissions if row.user == user]
        expected = {("Employee", employee_names[user]), ("Company", "_Test Company")}
        if (
            len(rows) != 2
            or {(row.allow, row.for_value) for row in rows} != expected
            or any(
                row.applicable_for
                or int(row.apply_to_all_doctypes or 0) != 1
                or int(row.is_default or 0) != 0
                or int(row.hide_descendants or 0) != 0
                for row in rows
            )
        ):
            frappe.throw(_("A v5 rehearsal User Permission differs from native Employee scope."))
        permission_names.extend(str(row.name) for row in rows)
    if frappe.db.exists(
        "User Permission",
        {
            "allow": "Employee",
            "for_value": ["in", list(employee_names.values())],
            "user": ["not in", list(REHEARSAL_USERS)],
        },
    ):
        frappe.throw(_("Another User references a v5 rehearsal Employee."))

    action_names = frappe.get_all(
        "Workflow Action",
        filters={"reference_doctype": "Purchase Order", "reference_name": name},
        pluck="name",
    )
    for action_name in action_names:
        frappe.delete_doc("Workflow Action", action_name, ignore_permissions=True)
    frappe.delete_doc("Purchase Order", name, ignore_permissions=True)
    for permission_name in permission_names:
        frappe.delete_doc("User Permission", permission_name, ignore_permissions=True)
    for user in REHEARSAL_USERS:
        frappe.delete_doc("Employee", employee_names[user], ignore_permissions=True)
        frappe.delete_doc("User", user, ignore_permissions=True)


@contextmanager
def isolated_v4_baseline() -> Iterator[set[Path]]:
    """Exercise v5 upgrade against test-owned artifacts on installed v4 or v5."""
    original_shape = v5._site_shape(v5._current_blueprint())
    if original_shape not in {"v4", "v5"}:
        raise AssertionError("The v5 rehearsal requires installed v4 or v5 configuration")
    original_history = v5._history()
    v4_anchor_ids = set(
        frappe.get_all("File", filters={"file_name": v4.RECOVERY_FILE, "is_private": 1}, pluck="name")
    )
    real_ids = {v5.RECOVERY_FILE, v5.AUDIT_FILE, v5.CONSUMED_FILE, *v4_anchor_ids}
    real_artifacts: dict[str, tuple[dict[str, object], bytes] | None] = {}
    for artifact_id in real_ids:
        if frappe.db.exists("File", artifact_id):
            record = cast(File, frappe.get_doc("File", artifact_id))
            real_artifacts[artifact_id] = (dict(record.as_dict()), Path(record.get_full_path()).read_bytes())
        else:
            real_artifacts[artifact_id] = None
    token = uuid4().hex
    test_ids = {
        "RECOVERY_FILE": f"_test-connect-workflow-v5-recovery-{token}.json",
        "AUDIT_FILE": f"_test-connect-workflow-v5-audit-{token}.json",
        "CONSUMED_FILE": f"_test-connect-workflow-v5-consumed-{token}.json",
    }
    if any(frappe.db.exists("File", name) for name in test_ids.values()):
        raise AssertionError("A reserved v5 test artifact identity is already occupied")
    savepoint = f"v5_isolated_{token}"
    frappe.db.savepoint(savepoint)
    original_user = frappe.session.user
    owned_paths: set[Path] = set()
    original_file_write = File.write_file

    def track_file_write(file_doc: File) -> str | None:
        if any(
            cast(str, file_doc.file_name).startswith(name.removesuffix(".json")) for name in test_ids.values()
        ):
            path = Path(file_doc.get_full_path()).resolve()
            expected_path = Path(frappe.get_site_path("private", "files", file_doc.file_name)).resolve()
            if (
                not file_doc.is_private
                or file_doc.file_url != f"/private/files/{file_doc.file_name}"
                or path != expected_path
            ):
                raise AssertionError("A reserved v5 test artifact resolved outside its private File path")
            if path.exists():
                raise AssertionError("A reserved v5 test artifact path already exists")
            owned_paths.add(path)
        return original_file_write(file_doc)

    with ExitStack() as patches:
        for constant, artifact_id in test_ids.items():
            patches.enter_context(patch.object(v5, constant, artifact_id))
        patches.enter_context(patch.object(File, "write_file", track_file_write))
        try:
            if original_shape == "v5":
                frappe.set_user("Administrator")
                po = cast(Workflow, frappe.get_doc("Workflow", v5.PURCHASE_ORDER_WORKFLOW))
                matching = [
                    row
                    for row in po.transitions
                    if all(row.get(key) == value for key, value in v5.RETURN_TRANSITION.items())
                ]
                if len(matching) != 1:
                    raise AssertionError("Installed v5 is missing the exact reviewed PO Return transition")
                po.remove(matching[0])
                for index, row in enumerate(po.transitions, 1):
                    row.idx = index
                po.save(ignore_permissions=True)
                frappe.clear_cache(doctype="Workflow")
            if v5._site_shape(v5._current_blueprint()) != "v4":
                raise AssertionError("Test isolation did not reach the archived v4 baseline")
            frappe.set_user(original_user)
            yield owned_paths
        finally:
            frappe.set_user("Administrator")
            frappe.db.rollback(save_point=savepoint)
            for path in owned_paths:
                path.unlink(missing_ok=True)
            for doctype in ("Workflow", "Purchase Order", "File"):
                frappe.clear_cache(doctype=doctype)
            for user in REHEARSAL_USERS:
                frappe.clear_cache(user=user)
            frappe.set_user(original_user)
            if v5._site_shape(v5._current_blueprint()) != original_shape or v5._history() != original_history:
                raise AssertionError(
                    "The v5 test isolation did not restore the installed configuration or history"
                )
            for artifact_id, expected in real_artifacts.items():
                if expected is None:
                    if frappe.db.exists("File", artifact_id):
                        raise AssertionError("A real v5 artifact appeared during test isolation")
                else:
                    record = cast(File, frappe.get_doc("File", artifact_id))
                    if (
                        dict(record.as_dict()) != expected[0]
                        or Path(record.get_full_path()).read_bytes() != expected[1]
                    ):
                        raise AssertionError("A real v5 artifact changed during test isolation")
            if (
                set(
                    frappe.get_all(
                        "File", filters={"file_name": v4.RECOVERY_FILE, "is_private": 1}, pluck="name"
                    )
                )
                != v4_anchor_ids
            ):
                raise AssertionError(
                    "The historical v4 recovery File identity set changed during test isolation"
                )


class TestUpgradeWorkflowBaselineV5(UnitTestCase):
    @staticmethod
    def _cleanup_fixture() -> tuple[dict[str, list[frappe._dict]], list[frappe._dict]]:
        employees: dict[str, list[frappe._dict]] = {}
        permissions: list[frappe._dict] = []
        for index, user in enumerate(REHEARSAL_USERS):
            employee_name = f"EMP-OWNED-{index}"
            employees[user] = [
                frappe._dict(name=employee_name, first_name=user, user_id=user, company="_Test Company")
            ]
            for allow, for_value in (("Employee", employee_name), ("Company", "_Test Company")):
                permissions.append(
                    frappe._dict(
                        name=f"UP-{index}-{allow}",
                        user=user,
                        allow=allow,
                        for_value=for_value,
                        applicable_for=None,
                        apply_to_all_doctypes=1,
                        is_default=0,
                        hide_descendants=0,
                    )
                )
        return employees, permissions

    @contextmanager
    def _mock_cleanup_data(
        self,
        employees: dict[str, list[frappe._dict]],
        permissions: list[frappe._dict],
        *,
        cross_user: bool = False,
    ) -> Iterator[tuple[Mock, Mock]]:
        def value(doctype: str, filters: object, fieldname: object, **_kwargs: object) -> object:
            if doctype == "Purchase Order":
                self.assertEqual((filters, fieldname), ("PO-OWNED", "title"))
                return REHEARSAL_MARKER
            self.assertEqual((doctype, fieldname), ("User", ["email", "first_name"]))
            return frappe._dict(email=filters, first_name=filters)

        def rows(doctype: str, *, filters: dict[str, object], **_kwargs: object) -> object:
            if doctype == "Employee":
                return employees[str(filters["user_id"])]
            if doctype == "User Permission":
                return permissions
            self.assertEqual(doctype, "Workflow Action")
            return ["WA-OWNED"]

        with (
            patch.object(frappe.db, "get_value", side_effect=value),
            patch.object(frappe, "get_all", side_effect=rows),
            patch.object(frappe.db, "exists", return_value=cross_user) as exists,
            patch.object(frappe, "delete_doc") as delete,
        ):
            yield delete, exists

    def test_cleanup_deletes_only_owned_actions_before_order_and_users(self) -> None:
        employees, permissions = self._cleanup_fixture()
        with self._mock_cleanup_data(employees, permissions) as (delete, exists):
            _cleanup_rehearsal("PO-OWNED")
        exists.assert_called_once()
        self.assertEqual(exists.call_args.args[0], "User Permission")
        expected = [("Workflow Action", "WA-OWNED"), ("Purchase Order", "PO-OWNED")]
        expected.extend(("User Permission", str(row.name)) for row in permissions)
        for user in REHEARSAL_USERS:
            expected.extend((("Employee", str(employees[user][0].name)), ("User", user)))
        self.assertEqual([event.args for event in delete.call_args_list], expected)

    def test_cleanup_preflight_rejects_incomplete_foreign_or_changed_scope_without_deletes(self) -> None:
        for case in (
            "missing_employee",
            "wrong_employee_company",
            "missing_permission",
            "duplicate_permission",
            "foreign_scope",
            "changed_flags",
            "cross_user_employee_link",
        ):
            with self.subTest(case=case):
                employees, permissions = self._cleanup_fixture()
                if case == "missing_employee":
                    employees[MAKER] = []
                elif case == "wrong_employee_company":
                    employees[MAKER][0].company = "Other Company"
                elif case == "missing_permission":
                    permissions.pop()
                elif case == "duplicate_permission":
                    permissions[-1] = copy.deepcopy(permissions[-2])
                elif case == "foreign_scope":
                    permissions[-1].allow = "Warehouse"
                elif case == "changed_flags":
                    permissions[-1].applicable_for = "Purchase Order"
                with (
                    self._mock_cleanup_data(
                        employees, permissions, cross_user=case == "cross_user_employee_link"
                    ) as (delete, _exists),
                    self.assertRaises(frappe.ValidationError),
                ):
                    _cleanup_rehearsal("PO-OWNED")
                delete.assert_not_called()

    def test_exact_delta_keeps_v4_routes_and_companions(self) -> None:
        current = v5._current_blueprint()
        archived = v4._blueprint()[0]
        self.assertEqual(set(current), set(archived))
        self.assertEqual(set(current), set(v4.CANONICAL_WORKFLOWS))
        self.assertEqual(
            {name: v4.workflow_fingerprint(row) for name, row in current.items()}, EXPECTED_V5_HASHES
        )
        for name in archived:
            before = copy.deepcopy(archived[name])
            after = copy.deepcopy(current[name])
            if name == v5.PURCHASE_ORDER_WORKFLOW:
                self.assertEqual(after["transitions"].count(v5.RETURN_TRANSITION), 1)
                return_index = after["transitions"].index(v5.RETURN_TRANSITION)
                self.assertEqual(after["transitions"][return_index + 1]["action"], "Post Purchase Order")
                after["transitions"].remove(v5.RETURN_TRANSITION)
            self.assertEqual(v4.workflow_shape(after), v4.workflow_shape(before))

    def test_static_v5_blueprint_does_not_read_live_fixtures_or_mutate_archive(self) -> None:
        archived_before = v4._blueprint()[0]
        shapes_before = {name: v4.workflow_fingerprint(row) for name, row in archived_before.items()}
        with patch("frappe.get_app_path", side_effect=AssertionError("Live fixture was read")):
            first = v5._current_blueprint()
            second = v5._current_blueprint()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertIsNot(first[v5.PURCHASE_ORDER_WORKFLOW], second[v5.PURCHASE_ORDER_WORKFLOW])
        self.assertEqual(
            {name: v4.workflow_fingerprint(row) for name, row in v4._blueprint()[0].items()},
            shapes_before,
        )

    def test_static_v5_blueprint_rejects_missing_duplicate_post_or_existing_delta(self) -> None:
        for change in ("missing_post", "duplicate_post", "existing_return"):
            archived, states, actions = v4._blueprint()
            po = archived[v5.PURCHASE_ORDER_WORKFLOW]
            transitions = po["transitions"]
            post = next(row for row in transitions if row["action"] == "Post Purchase Order")
            if change == "missing_post":
                transitions.remove(post)
            elif change == "duplicate_post":
                transitions.append(copy.deepcopy(post))
            else:
                transitions.append(copy.deepcopy(v5.RETURN_TRANSITION))
            with (
                self.subTest(change=change),
                patch.object(v4, "_blueprint", return_value=(archived, states, actions)),
                self.assertRaises(frappe.ValidationError),
            ):
                v5._current_blueprint()

    def test_preflight_rejects_v5_without_recovery_snapshot(self) -> None:
        with (
            patch.object(v5, "_current_blueprint", return_value={}),
            patch.object(v5, "_site_shape", return_value="v5"),
            patch.object(v5, "_snapshot", return_value=None),
            self.assertRaises(frappe.ValidationError),
        ):
            v5.preflight()

    def test_preflight_rejects_changed_history_before_audit(self) -> None:
        with (
            patch.object(v5, "_current_blueprint", return_value={}),
            patch.object(v5, "_site_shape", return_value="v4"),
            patch.object(
                v5,
                "_snapshot",
                return_value={"desired_hashes": {}, "history": "old", "predecessor": "v4"},
            ),
            patch.object(v5, "_history", return_value="changed"),
            patch.object(v5, "_artifact", return_value=None),
            self.assertRaises(frappe.ValidationError),
        ):
            v5.preflight()

    def test_completed_audit_allows_later_business_history(self) -> None:
        saved = {"desired_hashes": {}, "history": "old", "predecessor": "v4"}
        with (
            patch.object(v5, "_current_blueprint", return_value={}),
            patch.object(v5, "_site_shape", return_value="v5"),
            patch.object(v5, "_snapshot", return_value=saved),
            patch.object(
                v5,
                "_artifact",
                return_value={"schema_version": 5, "desired_hashes": {}, "config_versions": {}},
            ),
            patch.object(v5, "_history") as history,
        ):
            v5.preflight()
        history.assert_not_called()

    def test_recovery_requires_v4_predecessor(self) -> None:
        with (
            patch.object(v5, "_locked_config"),
            patch.object(v5, "preflight"),
            patch.object(v5, "_snapshot", return_value={"predecessor": "absent"}),
            self.assertRaises(frappe.ValidationError),
        ):
            recovery._preflight()

    def test_snapshot_revision_mismatch_refuses_preflight(self) -> None:
        current = v5._current_blueprint()
        with (
            patch.object(v5, "_current_blueprint", return_value=current),
            patch.object(v5, "_site_shape", return_value="v4"),
            patch.object(
                v5, "_snapshot", return_value={"predecessor": "v4", "desired_hashes": {}, "history": {}}
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            v5.preflight()

    def test_foreign_active_route_and_callback_reference_refuse_preflight(self) -> None:
        current = v5._current_blueprint()
        with (
            patch.object(v5.frappe, "get_all", return_value=["FOREIGN-WORKFLOW"]),
            self.assertRaises(frappe.ValidationError),
        ):
            v5._site_shape(current)

        original_exists = frappe.db.exists

        def foreign_group_reference(doctype: str, filters: object, *args: object, **kwargs: object) -> object:
            if (
                doctype == "Workflow Transition"
                and isinstance(filters, dict)
                and "transition_tasks" in filters
            ):
                return "FOREIGN-TRANSITION"
            return original_exists(doctype, filters, *args, **kwargs)

        with (
            patch.object(v5.frappe.db, "exists", side_effect=foreign_group_reference),
            self.assertRaises(frappe.ValidationError),
        ):
            v5._site_shape(current)

    def test_fresh_lifecycle_harness_records_absent_predecessor(self) -> None:
        from connect_diagnostics_core import hooks

        self.assertLess(
            hooks.after_install.index(
                "connect_diagnostics_core.patches.v1_0.normalize_workflow_baseline.execute"
            ),
            hooks.after_install.index(
                "connect_diagnostics_core.patches.v1_0.upgrade_workflow_baseline_v5.prepare"
            ),
        )
        self.assertEqual(
            hooks.after_sync[-1], "connect_diagnostics_core.patches.v1_0.upgrade_workflow_baseline_v5.verify"
        )
        current = v5._current_blueprint()
        site_shape = "absent"
        saved: dict[str, object] | None = None

        def create_snapshot(predecessor: str, blueprint: dict[str, dict[str, object]]) -> None:
            nonlocal saved
            self.assertIs(blueprint, current)
            saved = {
                "predecessor": predecessor,
                "desired_hashes": {name: v4.workflow_fingerprint(row) for name, row in current.items()},
                "history": {},
            }

        with (
            patch.object(v5, "_locked_config"),
            patch.object(v5, "_current_blueprint", return_value=current),
            patch.object(v5, "_site_shape", side_effect=lambda _current: site_shape),
            patch.object(v5, "_snapshot", side_effect=lambda: saved),
            patch.object(v5, "_create_snapshot", side_effect=create_snapshot),
            patch.object(v5, "_history", return_value={}),
            patch.object(v5, "_artifact", return_value=None),
            patch.object(v5, "_configuration_versions", return_value={}),
            patch.object(v5, "_write_artifact") as write_audit,
        ):
            v5.preflight()
            v5.prepare()
            assert saved is not None
            self.assertEqual(saved["predecessor"], "absent")
            site_shape = "v5"  # Native fixture import between after_install and after_sync.
            v5.verify()
            write_audit.assert_called_once()
            self.assertEqual(write_audit.call_args.args[:2], (v5.AUDIT_FILE, "audit"))
            with self.assertRaises(frappe.ValidationError):
                recovery._preflight()


class TestUpgradeArtifactIntegration(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._isolation = isolated_v4_baseline()
        self._isolation.__enter__()

    def tearDown(self) -> None:
        try:
            self._isolation.__exit__(None, None, None)
        finally:
            super().tearDown()

    @contextmanager
    def _uuid_rehearsal(self) -> Iterator[tuple[str, tuple[str, ...]]]:
        token = uuid4().hex
        users = tuple(
            f"_test.po.v5.{role}.{token}@example.com" for role in ("maker", "reviewer", "approver", "return")
        )
        marker = f"PO-v5-native-cleanup-{token}"
        with patch.multiple(
            sys.modules[__name__],
            MAKER=users[0],
            REVIEWER=users[1],
            APPROVER=users[2],
            RETURN_USER=users[3],
            REHEARSAL_USERS=users,
            REHEARSAL_MARKER=marker,
        ):
            try:
                prepare_inflight(commit=False)
                name = frappe.db.get_value("Purchase Order", {"title": marker}, "name")
                assert name
                yield str(name), users
            finally:
                frappe.set_user("Administrator")
                for user in users:
                    frappe.clear_cache(user=user)

    def test_uuid_rehearsal_cleanup_deletes_only_owned_scopes_and_actors(self) -> None:
        with self._uuid_rehearsal() as (name, users):
            foreign = f"_test.po.v5.foreign.{uuid4().hex}@example.com"
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": foreign,
                    "first_name": foreign,
                    "send_welcome_email": 0,
                    "user_type": "System User",
                }
            ).insert(ignore_permissions=True)
            unrelated = frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "user": foreign,
                    "allow": "Company",
                    "for_value": "_Test Company",
                }
            ).insert(ignore_permissions=True)
            try:
                self.assertEqual(frappe.db.count("User Permission", {"user": ["in", list(users)]}), 8)
                self.assertTrue(frappe.db.exists("Workflow Action", {"reference_name": name}))
                _cleanup_rehearsal(name)
                self.assertFalse(frappe.db.exists("Purchase Order", name))
                self.assertFalse(frappe.db.exists("Workflow Action", {"reference_name": name}))
                self.assertEqual(frappe.db.count("User Permission", {"user": ["in", list(users)]}), 0)
                for user in users:
                    self.assertFalse(frappe.db.exists("Employee", {"user_id": user}))
                    self.assertFalse(frappe.db.exists("User", user))
                self.assertTrue(frappe.db.exists("User Permission", unrelated.name))
                self.assertTrue(frappe.db.exists("User", foreign))
            finally:
                frappe.clear_cache(user=foreign)

    def test_uuid_rehearsal_cleanup_refuses_foreign_scope_and_cross_user_link_before_deletes(self) -> None:
        with self._uuid_rehearsal() as (name, users):
            foreign = f"_test.po.v5.foreign.{uuid4().hex}@example.com"
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": foreign,
                    "first_name": foreign,
                    "send_welcome_email": 0,
                    "user_type": "System User",
                }
            ).insert(ignore_permissions=True)
            employee = frappe.db.get_value("Employee", {"user_id": users[0]}, "name")
            try:
                for case in ("foreign_scope", "cross_user_employee"):
                    case_savepoint = f"v5_cleanup_{case}"
                    frappe.db.savepoint(case_savepoint)
                    try:
                        if case == "foreign_scope":
                            frappe.get_doc(
                                {
                                    "doctype": "User Permission",
                                    "user": users[0],
                                    "allow": "Warehouse",
                                    "for_value": "_Test Warehouse - _TC",
                                }
                            ).insert(ignore_permissions=True)
                        else:
                            frappe.get_doc(
                                {
                                    "doctype": "User Permission",
                                    "user": foreign,
                                    "allow": "Employee",
                                    "for_value": employee,
                                }
                            ).insert(ignore_permissions=True)
                        before = (
                            frappe.db.count("Workflow Action", {"reference_name": name}),
                            frappe.db.count("User Permission", {"user": ["in", list(users)]}),
                            frappe.db.get_value("Purchase Order", name, "workflow_state"),
                        )
                        with (
                            patch.object(frappe, "delete_doc", wraps=frappe.delete_doc) as delete,
                            self.assertRaises(frappe.ValidationError),
                        ):
                            _cleanup_rehearsal(name)
                        delete.assert_not_called()
                        self.assertEqual(
                            (
                                frappe.db.count("Workflow Action", {"reference_name": name}),
                                frappe.db.count("User Permission", {"user": ["in", list(users)]}),
                                frappe.db.get_value("Purchase Order", name, "workflow_state"),
                            ),
                            before,
                        )
                        self.assertTrue(all(frappe.db.exists("User", user) for user in users))
                    finally:
                        frappe.db.rollback(save_point=case_savepoint)
            finally:
                frappe.clear_cache(user=foreign)

    def test_isolation_restores_simulated_installed_v5_and_its_artifacts(self) -> None:
        v5.execute()
        v5.verify()
        outer_recovery = v5.RECOVERY_FILE
        outer_artifact = cast(File, frappe.get_doc("File", outer_recovery))
        outer_metadata = dict(outer_artifact.as_dict())
        outer_raw = Path(outer_artifact.get_full_path()).read_bytes()
        outer_history = v5._history()
        self.assertEqual(v5._site_shape(v5._current_blueprint()), "v5")
        with isolated_v4_baseline():
            self.assertNotEqual(v5.RECOVERY_FILE, outer_recovery)
            self.assertEqual(v5._site_shape(v5._current_blueprint()), "v4")
            v5.execute()
            v5.verify()
            self.assertEqual(v5._site_shape(v5._current_blueprint()), "v5")
        self.assertEqual(v5.RECOVERY_FILE, outer_recovery)
        self.assertEqual(v5._site_shape(v5._current_blueprint()), "v5")
        self.assertEqual(v5._history(), outer_history)
        restored = cast(File, frappe.get_doc("File", outer_recovery))
        self.assertEqual(dict(restored.as_dict()), outer_metadata)
        self.assertEqual(Path(restored.get_full_path()).read_bytes(), outer_raw)

    def test_failed_file_insert_removes_only_test_owned_orphan(self) -> None:
        with isolated_v4_baseline() as owned_paths:
            with (
                patch.object(File, "db_insert", side_effect=frappe.ValidationError("File DB insert failed")),
                self.assertRaises(frappe.ValidationError),
            ):
                v5._write_artifact(v5.RECOVERY_FILE, "recovery", {"schema_version": 5, "probe": "orphan"})
            self.assertFalse(frappe.db.exists("File", v5.RECOVERY_FILE))
            self.assertEqual(len(owned_paths), 1)
            orphan = next(iter(owned_paths))
            self.assertTrue(orphan.exists())
        self.assertFalse(orphan.exists())

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_invalid_action_or_business_state_refuses_before_upgrade(self, _mail: object) -> None:
        savepoint = "v5_invalid_action_state"
        frappe.db.savepoint(savepoint)
        self.addCleanup(frappe.set_user, "Administrator")
        try:
            prepare_inflight(commit=False)
            name = frappe.db.get_value("Purchase Order", {"title": REHEARSAL_MARKER}, "name")
            action = frappe.db.get_value(
                "Workflow Action",
                {"reference_doctype": "Purchase Order", "reference_name": name, "status": "Open"},
                "name",
            )
            action_role = frappe.db.get_value("Workflow Action Permitted Role", {"parent": action}, "name")
            for doctype, field, invalid in (
                ("Workflow Action", "workflow_state", "Unknown PO State"),
                ("Workflow Action", "status", "Invalid"),
                ("Purchase Order", "workflow_state", "Unknown PO State"),
            ):
                case_savepoint = f"v5_invalid_{field}_{doctype.replace(' ', '_')}"
                frappe.db.savepoint(case_savepoint)
                try:
                    frappe.db.set_value(
                        doctype, action if doctype == "Workflow Action" else name, field, invalid
                    )
                    with self.assertRaises(frappe.ValidationError):
                        v5.execute()
                    self.assertFalse(frappe.db.exists("File", v5.RECOVERY_FILE))
                finally:
                    frappe.db.rollback(save_point=case_savepoint)
            for field, invalid in (("parenttype", "Purchase Order"), ("parent", "MISSING-ACTION")):
                case_savepoint = f"v5_invalid_role_{field}"
                frappe.db.savepoint(case_savepoint)
                try:
                    frappe.db.set_value("Workflow Action Permitted Role", action_role, field, invalid)
                    with self.assertRaises(frappe.ValidationError):
                        v5.execute()
                    self.assertFalse(frappe.db.exists("File", v5.RECOVERY_FILE))
                finally:
                    frappe.db.rollback(save_point=case_savepoint)
            self.assertEqual(v5._site_shape(v5._current_blueprint()), "v4")
        finally:
            frappe.set_user("Administrator")
            frappe.db.rollback(save_point=savepoint)

    def test_eligible_recovery_consumes_snapshot_and_refuses_reupgrade(self) -> None:
        savepoint = "v5_eligible_recovery"
        frappe.db.savepoint(savepoint)
        try:
            v5.execute()
            v5.verify()
            recovery.execute()
            self.assertEqual(v5._site_shape(v5._current_blueprint()), "v4")
            self.assertEqual(
                v4.workflow_shape(frappe.get_doc("Workflow", v5.PURCHASE_ORDER_WORKFLOW)),
                v4.workflow_shape(v4._blueprint()[0][v5.PURCHASE_ORDER_WORKFLOW]),
            )
            self.assertEqual(
                v5._artifact(v5.CONSUMED_FILE, "consumed"),
                {"schema_version": v5.SNAPSHOT_VERSION, "status": "rolled_back"},
            )
            with self.assertRaises(frappe.ValidationError):
                v5.preflight()
            with self.assertRaises(frappe.ValidationError):
                recovery.execute()
            self.assertEqual(v5._site_shape(v5._current_blueprint()), "v4")
        finally:
            frappe.db.rollback(save_point=savepoint)

    def test_reserved_recovery_id_preemption_stops_before_workflow_write(self) -> None:
        savepoint = "v5_reserved_id_preemption"
        frappe.db.savepoint(savepoint)
        try:
            frappe.get_doc(
                {
                    "doctype": "File",
                    "file_name": f"{v5.RECOVERY_FILE.removesuffix('.json')}-foreign.json",
                    "is_private": 1,
                    "content": f"foreign-{v5.RECOVERY_FILE}",
                }
            ).insert(ignore_permissions=True, set_name=v5.RECOVERY_FILE)
            with self.assertRaises(frappe.ValidationError):
                v5.execute()
            self.assertEqual(v5._site_shape(v5._current_blueprint()), "v4")
            self.assertFalse(frappe.db.exists("File", v5.AUDIT_FILE))
        finally:
            frappe.db.rollback(save_point=savepoint)

    def test_config_drift_refuses_upgrade_before_snapshot(self) -> None:
        savepoint = "v5_config_drift"
        frappe.db.savepoint(savepoint)
        try:
            po = cast(Workflow, frappe.get_doc("Workflow", v5.PURCHASE_ORDER_WORKFLOW))
            frappe.db.set_value("Workflow", po.name, "send_email_alert", int(not po.send_email_alert))
            with self.assertRaises(frappe.ValidationError):
                v5.execute()
            self.assertFalse(frappe.db.exists("File", v5.RECOVERY_FILE))
        finally:
            frappe.db.rollback(save_point=savepoint)

    @patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
    def test_native_c_level_only_return_keeps_maker_and_no_posting(self, _mail: object) -> None:
        savepoint = "v5_native_return_rehearsal"
        frappe.db.savepoint(savepoint)
        old_request = getattr(frappe.local, "request", None)
        frappe.local.request = frappe._dict(method="POST")
        self.addCleanup(setattr, frappe.local, "request", old_request)
        self.addCleanup(frappe.set_user, "Administrator")
        try:
            prepare_inflight(commit=False)
            name = frappe.db.get_value("Purchase Order", {"title": REHEARSAL_MARKER}, "name")
            order = frappe.get_doc("Purchase Order", name)
            maker = order.get("approval_maker_user")
            ordered_before = _ordered_qty()
            v5.execute()
            v5.verify()
            procure_to_pay.activate_standard_permissions()
            procure_to_pay._preflight_master_read_permissions()
            account_grant = frappe.db.get_value(
                "Custom DocPerm",
                {"parent": "Account", "role": "C-Level Approver", "permlevel": 0, "if_owner": 0},
                ["select", "read"],
                as_dict=True,
            )
            self.assertEqual((account_grant.select, account_grant.read), (1, 0))
            frappe.clear_cache(doctype="Supplier")
            frappe.clear_cache(doctype="Item")
            frappe.clear_cache(doctype="Account")
            frappe.set_user(RETURN_USER)
            _assert_return_roles()
            payable = get_party_account("Supplier", order.get("supplier"), order.get("company"))
            self.assertTrue(frappe.only_has_select_perm("Account"))
            self.assertTrue(frappe.has_permission("Account", "select", payable))
            self.assertFalse(frappe.has_permission("Account", "read", payable))
            self.assertTrue(frappe.has_permission("Purchase Order", "write", doc=order))
            self.assertIn("Return Purchase Order", {row["action"] for row in get_transitions(order)})
            apply_workflow(order, "Return Purchase Order")
            order.reload()
            self.assertEqual((order.docstatus, order.get("workflow_state")), (0, "Purchase Order Draft"))
            self.assertEqual(order.get("approval_maker_user"), maker)
            from connect_diagnostics_core.api.erpnext.purchase_order_workflow import SNAPSHOT_FIELDS

            self.assertFalse(any(order.get(field) for field in SNAPSHOT_FIELDS))
            self.assertEqual(_ordered_qty(), ordered_before)
            v5.preflight()
            v5.verify()
            with self.assertRaises(frappe.ValidationError):
                recovery._preflight()
        finally:
            frappe.set_user("Administrator")
            frappe.db.rollback(save_point=savepoint)

    def test_existing_v4_upgrade_and_retry_preserve_exact_single_delta(self) -> None:
        self.assertEqual(v5._site_shape(v5._current_blueprint()), "v4")
        savepoint = "v5_upgrade_rehearsal"
        frappe.db.savepoint(savepoint)
        try:
            v5.execute()
            self.assertEqual(v5._site_shape(v5._current_blueprint()), "v5")
            with self.assertRaises(frappe.ValidationError):
                v4.preflight()
            with self.assertRaises(frappe.ValidationError):
                v4_recovery._preflight(v4_recovery._snapshot(), incomplete=False)
            v5.execute()
            po = cast(Workflow, frappe.get_doc("Workflow", v5.PURCHASE_ORDER_WORKFLOW))
            self.assertEqual(
                sum(
                    row.action == "Return Purchase Order" and row.state == "Purchase Order Approved"
                    for row in po.transitions
                ),
                1,
            )
        finally:
            frappe.db.rollback(save_point=savepoint)

    def test_reserved_file_identity_is_authenticated_and_retry_survives_orphan(self) -> None:
        artifact_id = f"{v5.RECOVERY_FILE.removesuffix('.json')}-retry.json"
        self.assertFalse(frappe.db.exists("File", artifact_id))
        first = "v5_artifact_first"
        frappe.db.savepoint(first)
        v5._write_artifact(artifact_id, "retry-test", {"schema_version": 5, "value": "first"})
        first_file = cast(File, frappe.get_doc("File", artifact_id))
        first_name = first_file.file_name
        first_payload = v5._artifact(artifact_id, "retry-test")
        assert first_payload is not None
        self.assertEqual(first_payload["value"], "first")
        frappe.db.rollback(save_point=first)
        self.assertFalse(frappe.db.exists("File", artifact_id))
        second = "v5_artifact_second"
        frappe.db.savepoint(second)
        second_path: Path | None = None
        original_content: bytes | None = None
        try:
            v5._write_artifact(artifact_id, "retry-test", {"schema_version": 5, "value": "retry"})
            second_file = cast(File, frappe.get_doc("File", artifact_id))
            second_path = Path(second_file.get_full_path())
            self.assertNotEqual(second_file.file_name, first_name)
            second_payload = v5._artifact(artifact_id, "retry-test")
            assert second_payload is not None
            self.assertEqual(second_payload["value"], "retry")
            with self.assertRaises(frappe.ValidationError):
                v5._artifact(artifact_id, "wrong-kind")
            original_content = second_path.read_bytes()
            tampered = json.loads(original_content)
            tampered["payload"]["value"] = "forged"
            tampered_content = json.dumps(tampered, sort_keys=True).encode()
            second_path.write_bytes(tampered_content)
            frappe.db.set_value("File", artifact_id, "content_hash", get_content_hash(tampered_content))
            with self.assertRaises(frappe.ValidationError):
                v5._artifact(artifact_id, "retry-test")
        finally:
            if second_path is not None and original_content is not None:
                second_path.write_bytes(original_content)
            frappe.db.rollback(save_point=second)
            self.assertFalse(frappe.db.exists("File", artifact_id))


def prepare_inflight(*, commit: bool = True) -> None:
    """Create one genuine v4 Approved PO and Open Post action before native migrate."""
    if frappe.db.exists("Purchase Order", {"title": REHEARSAL_MARKER}):
        frappe.throw(_("The v5 rehearsal Purchase Order already exists."))
    if v5._site_shape(v5._current_blueprint()) != "v4":
        frappe.throw(_("The v5 rehearsal requires exact installed v4 configuration."))
    frappe.set_user("Administrator")
    _create_actor(MAKER, ("Purchase User",))
    _create_actor(REVIEWER, ("Purchase User", "Purchase Manager"))
    _create_actor(APPROVER, ("Purchase User", "C-Level Approver"))
    _create_actor(RETURN_USER, ("C-Level Approver",))
    _assert_return_roles()
    frappe.set_user(MAKER)
    order = _draft_order()
    order.set("title", REHEARSAL_MARKER)
    order.save()
    apply_workflow(order, "Submit Purchase Order for Review")
    frappe.set_user(REVIEWER)
    apply_workflow(order.reload(), "Review Purchase Order")
    frappe.set_user(APPROVER)
    apply_workflow(order.reload(), "Approve Purchase Order")
    order.reload()
    if order.get("workflow_state") != "Purchase Order Approved" or order.docstatus != 0:
        frappe.throw(_("The v4 Purchase Order did not reach Approved draft state."))
    actions = frappe.get_all(
        "Workflow Action",
        filters={"reference_doctype": "Purchase Order", "reference_name": order.name, "status": "Open"},
        fields=["name", "workflow_state"],
    )
    if not actions or any(row.workflow_state != "Purchase Order Approved" for row in actions):
        frappe.throw(_("The v4 Purchase Order lacks its legitimate Open Post action."))
    frappe.set_user("Administrator")
    if commit:
        frappe.db.commit()


def verify_inflight_return() -> None:
    """Prove native C-Level-only Return after actual migrate, then remove the owned PO."""
    frappe.set_user("Administrator")
    name = frappe.db.get_value("Purchase Order", {"title": REHEARSAL_MARKER}, "name")
    if not name:
        frappe.throw(_("The v5 rehearsal Purchase Order is missing."))
    v5.verify()
    order = frappe.get_doc("Purchase Order", name)
    if order.get("workflow_state") != "Purchase Order Approved" or order.docstatus != 0:
        frappe.throw(_("Migration changed the in-flight Purchase Order."))
    maker = order.get("approval_maker_user")
    open_before = frappe.get_all(
        "Workflow Action",
        filters={"reference_doctype": "Purchase Order", "reference_name": name, "status": "Open"},
        pluck="name",
    )
    if not open_before:
        frappe.throw(_("Migration changed the in-flight Open Post action."))
    ordered_before = _ordered_qty()
    version_before = frappe.db.count("Version", {"ref_doctype": "Purchase Order", "docname": name})
    _assert_return_roles()
    frappe.set_user(RETURN_USER)
    payable = get_party_account("Supplier", order.get("supplier"), order.get("company"))
    if not (
        frappe.only_has_select_perm("Account")
        and frappe.has_permission("Account", "select", payable)
        and not frappe.has_permission("Account", "read", payable)
    ):
        frappe.throw(_("The Return actor has incorrect payable Account permissions."))
    if not frappe.has_permission("Purchase Order", "write", doc=order):
        frappe.throw(_("The C-Level-only Return actor lacks native Purchase Order write permission."))
    if "Return Purchase Order" not in {row["action"] for row in get_transitions(order)}:
        frappe.throw(_("The Approved Return transition is unavailable to the C-Level-only actor."))
    apply_workflow(order, "Return Purchase Order")
    order.reload()
    if order.get("workflow_state") != "Purchase Order Draft" or order.docstatus != 0:
        frappe.throw(_("Native Return did not restore Purchase Order Draft."))
    if order.get("approval_maker_user") != maker:
        frappe.throw(_("Native Return changed the Purchase Order maker."))
    from connect_diagnostics_core.api.erpnext.purchase_order_workflow import SNAPSHOT_FIELDS

    if any(order.get(field) for field in SNAPSHOT_FIELDS):
        frappe.throw(_("Native Return retained approval evidence."))
    if _ordered_qty() != ordered_before:
        frappe.throw(_("Native Return changed ordered stock quantity."))
    if frappe.db.count("Version", {"ref_doctype": "Purchase Order", "docname": name}) <= version_before:
        frappe.throw(_("Native Return did not write the business Version audit."))
    frappe.set_user("Administrator")
    _cleanup_rehearsal(str(name))
    frappe.db.commit()
