# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import install_payment_approval_workflow as patch_module
from connect_diagnostics_core.patches.v1_0 import (
    rollback_install_payment_approval_workflow as rollback_module,
)
from connect_diagnostics_core.setup import payment_approval


class TestInstallPaymentApprovalWorkflow(UnitTestCase):
    def test_approval_deadline_is_indexed_for_scheduler_query(self) -> None:
        approval_due_at = next(
            field
            for field in payment_approval.CUSTOM_FIELDS[payment_approval.PAYMENT_ENTRY_DOCTYPE]
            if field["fieldname"] == payment_approval.APPROVAL_DUE_AT_FIELD
        )

        self.assertEqual(approval_due_at["search_index"], 1)

    @patch.object(patch_module.frappe, "clear_cache")
    @patch.object(patch_module, "assign_payment_approvers")
    @patch.object(patch_module, "ensure_configuration")
    @patch.object(patch_module, "create_custom_fields")
    def test_execute_creates_fields_before_configuration_and_assignment(
        self,
        mocked_create_fields: MagicMock,
        mocked_ensure_configuration: MagicMock,
        mocked_assign_approvers: MagicMock,
        _mocked_clear_cache: MagicMock,
    ) -> None:
        manager = MagicMock()
        manager.attach_mock(mocked_create_fields, "create_fields")
        manager.attach_mock(mocked_ensure_configuration, "ensure_configuration")
        manager.attach_mock(mocked_assign_approvers, "assign_approvers")

        patch_module.execute()

        self.assertEqual(
            manager.mock_calls,
            [
                call.create_fields(payment_approval.CUSTOM_FIELDS, ignore_validate=True),
                call.ensure_configuration(),
                call.assign_approvers(),
            ],
        )

    @patch.object(payment_approval, "_assign_role_profile_or_direct_roles")
    def test_assign_payment_approvers_uses_approved_users(self, mocked_assign_access: MagicMock) -> None:
        payment_approval.assign_payment_approvers()

        self.assertEqual(
            mocked_assign_access.call_args_list,
            [
                call(
                    payment_approval.PRIMARY_APPROVER_USER,
                    payment_approval.PRIMARY_APPROVER_PROFILE,
                    require_user=True,
                ),
                call(
                    payment_approval.LOW_VALUE_APPROVER_USER,
                    payment_approval.LOW_VALUE_APPROVER_PROFILE,
                    require_user=True,
                ),
                call(
                    payment_approval.SECONDARY_APPROVER_USER,
                    payment_approval.SECONDARY_APPROVER_PROFILE,
                    require_user=True,
                ),
            ],
        )

    @patch.object(payment_approval, "_get_enabled_user")
    def test_secondary_without_profiles_receives_direct_role(self, mocked_get_user: MagicMock) -> None:
        user = MagicMock()
        user.get.side_effect = lambda fieldname, default=None: {
            "role_profiles": [],
            "roles": [],
        }.get(fieldname, default)
        mocked_get_user.return_value = user

        payment_approval._assign_role_profile_or_direct_roles(
            "secondary@example.com",
            payment_approval.SECONDARY_APPROVER_PROFILE,
        )

        user.append.assert_called_once_with("roles", {"role": payment_approval.SECONDARY_APPROVER_ROLE})
        user.save.assert_called_once_with(ignore_permissions=True)

    @patch.object(payment_approval, "_get_enabled_user")
    def test_secondary_with_profiles_receives_secondary_profile(self, mocked_get_user: MagicMock) -> None:
        existing_profile = MagicMock(role_profile="Base Employee")
        user = MagicMock()
        user.get.side_effect = lambda fieldname, default=None: {
            "role_profiles": [existing_profile],
            "roles": [],
        }.get(fieldname, default)
        mocked_get_user.return_value = user

        payment_approval._assign_role_profile_or_direct_roles(
            "secondary@example.com",
            payment_approval.SECONDARY_APPROVER_PROFILE,
        )

        user.append.assert_called_once_with(
            "role_profiles", {"role_profile": payment_approval.SECONDARY_APPROVER_PROFILE}
        )
        user.save.assert_called_once_with(ignore_permissions=True)

    @patch.object(payment_approval, "_get_enabled_user")
    def test_primary_without_profiles_preserves_roles_and_receives_direct_roles(
        self, mocked_get_user: MagicMock
    ) -> None:
        retained_role = MagicMock(role="Employee")
        user = MagicMock()
        user.get.side_effect = lambda fieldname, default=None: {
            "role_profiles": [],
            "roles": [retained_role],
        }.get(fieldname, default)
        mocked_get_user.return_value = user

        payment_approval._assign_role_profile_or_direct_roles(
            "primary@example.com",
            payment_approval.PRIMARY_APPROVER_PROFILE,
        )

        self.assertEqual(
            user.append.call_args_list,
            [
                call("roles", {"role": payment_approval.PRIMARY_APPROVER_ROLE}),
                call("roles", {"role": payment_approval.LOW_VALUE_APPROVER_ROLE}),
            ],
        )
        user.save.assert_called_once_with(ignore_permissions=True)

    @patch.object(payment_approval.frappe, "clear_cache")
    @patch.object(payment_approval, "assign_payment_approvers")
    @patch.object(payment_approval, "ensure_workflow")
    @patch.object(payment_approval, "ensure_workflow_masters")
    @patch.object(payment_approval, "ensure_payment_entry_permissions")
    @patch.object(payment_approval, "ensure_role_profiles")
    @patch.object(payment_approval, "ensure_roles")
    def test_fresh_install_configuration_assigns_available_approvers(
        self,
        _mocked_ensure_roles: MagicMock,
        _mocked_ensure_profiles: MagicMock,
        _mocked_ensure_permissions: MagicMock,
        _mocked_ensure_masters: MagicMock,
        _mocked_ensure_workflow: MagicMock,
        mocked_assign_approvers: MagicMock,
        _mocked_clear_cache: MagicMock,
    ) -> None:
        payment_approval.ensure_configuration()

        mocked_assign_approvers.assert_called_once_with(require_users=False)

    @patch.object(payment_approval.frappe, "logger")
    @patch.object(payment_approval, "_assign_role_profile_or_direct_roles", return_value=False)
    def test_fresh_install_skips_unavailable_users_without_failing(
        self,
        _mocked_assign_access: MagicMock,
        mocked_logger: MagicMock,
    ) -> None:
        payment_approval.assign_payment_approvers(require_users=False)

        mocked_logger.return_value.warning.assert_called_once_with(
            "Skipped %s payment approver assignments because required Users are missing or disabled",
            3,
        )

    @patch.object(payment_approval, "_ensure_permission_copy_marker")
    @patch.object(payment_approval, "setup_custom_perms", return_value=True)
    def test_fresh_permission_setup_records_standard_permission_copy(
        self,
        _mocked_setup_custom_perms: MagicMock,
        mocked_ensure_marker: MagicMock,
    ) -> None:
        with patch.object(payment_approval, "PAYMENT_ENTRY_PERMISSIONS", {}):
            payment_approval.ensure_payment_entry_permissions()

        mocked_ensure_marker.assert_called_once_with()

    @patch.object(payment_approval.frappe, "get_doc")
    @patch.object(payment_approval.frappe.db, "exists", return_value=False)
    def test_permission_copy_marker_has_no_payment_entry_access(
        self,
        _mocked_exists: MagicMock,
        mocked_get_doc: MagicMock,
    ) -> None:
        marker = MagicMock()
        mocked_get_doc.return_value = marker

        payment_approval._ensure_permission_copy_marker()

        marker_values = mocked_get_doc.call_args.args[0]
        self.assertEqual(
            {fieldname: marker_values[fieldname] for fieldname in payment_approval.PERMISSION_FIELDS},
            {fieldname: 0 for fieldname in payment_approval.PERMISSION_FIELDS},
        )
        marker.insert.assert_called_once_with(ignore_permissions=True)

    @patch.object(payment_approval, "reset_perms")
    @patch.object(payment_approval.frappe.db, "exists", return_value=True)
    def test_rollback_resets_permissions_when_setup_copied_standard_rows(
        self,
        _mocked_exists: MagicMock,
        mocked_reset_perms: MagicMock,
    ) -> None:
        payment_approval._remove_payment_entry_permissions()

        mocked_reset_perms.assert_called_once_with(payment_approval.PAYMENT_ENTRY_DOCTYPE)

    @patch.object(payment_approval, "reset_perms")
    @patch.object(payment_approval.frappe, "delete_doc")
    @patch.object(payment_approval.frappe, "get_all", return_value=["MANAGED-PERM-1"])
    @patch.object(payment_approval.frappe.db, "exists", return_value=False)
    def test_rollback_preserves_preexisting_custom_permissions(
        self,
        _mocked_exists: MagicMock,
        mocked_get_all: MagicMock,
        mocked_delete_doc: MagicMock,
        mocked_reset_perms: MagicMock,
    ) -> None:
        payment_approval._remove_payment_entry_permissions()

        mocked_reset_perms.assert_not_called()
        mocked_get_all.assert_called_once_with(
            "Custom DocPerm",
            filters={
                "parent": payment_approval.PAYMENT_ENTRY_DOCTYPE,
                "role": ["in", tuple(payment_approval.PAYMENT_ENTRY_PERMISSIONS)],
                "permlevel": 0,
            },
            pluck="name",
        )
        mocked_delete_doc.assert_called_once_with(
            "Custom DocPerm",
            "MANAGED-PERM-1",
            force=True,
            ignore_permissions=True,
        )

    def test_rollback_removes_only_managed_user_rows(self) -> None:
        managed_profile = frappe._dict(role_profile=payment_approval.PRIMARY_APPROVER_PROFILE)
        retained_profile = frappe._dict(role_profile="Base Employee")
        managed_role = frappe._dict(role=payment_approval.PRIMARY_APPROVER_ROLE)
        retained_role = frappe._dict(role="Employee")
        user = MagicMock()
        user.get.side_effect = lambda fieldname, default=None: {
            "role_profiles": [managed_profile, retained_profile],
            "roles": [managed_role, retained_role],
        }.get(fieldname, default)

        profiles_changed = rollback_module._remove_user_child_rows(
            user,
            "role_profiles",
            "role_profile",
            rollback_module.MANAGED_PROFILES,
        )
        roles_changed = rollback_module._remove_user_child_rows(
            user,
            "roles",
            "role",
            payment_approval.MANAGED_ROLES,
        )

        self.assertTrue(profiles_changed)
        self.assertTrue(roles_changed)
        self.assertEqual(
            user.set.call_args_list,
            [
                call("role_profiles", [retained_profile]),
                call("roles", [retained_role]),
            ],
        )

    @patch.object(rollback_module.frappe, "get_all")
    def test_rollback_finds_every_user_with_managed_assignments(self, mocked_get_all: MagicMock) -> None:
        mocked_get_all.side_effect = [
            ["direct-role@example.com", "both@example.com"],
            ["profile@example.com", "both@example.com"],
        ]

        user_names = rollback_module._get_users_with_managed_assignments()

        self.assertEqual(
            user_names,
            (
                "both@example.com",
                "direct-role@example.com",
                "profile@example.com",
            ),
        )

    @patch.object(rollback_module.frappe, "delete_doc")
    @patch.object(rollback_module.frappe.db, "exists", return_value=True)
    @patch.object(rollback_module.frappe, "get_all", return_value=["ACTION-1", "ACTION-2"])
    def test_rollback_deletes_actions_for_all_managed_states(
        self,
        mocked_get_all: MagicMock,
        _mocked_exists: MagicMock,
        mocked_delete_doc: MagicMock,
    ) -> None:
        rollback_module._delete_managed_workflow_actions()

        mocked_get_all.assert_called_once_with(
            "Workflow Action",
            filters={
                "reference_doctype": payment_approval.PAYMENT_ENTRY_DOCTYPE,
                "workflow_state": ["in", tuple(payment_approval.WORKFLOW_STATE_STYLES)],
            },
            pluck="name",
        )
        self.assertEqual(
            mocked_delete_doc.call_args_list,
            [
                call("Workflow Action", "ACTION-1", force=True, ignore_permissions=True),
                call("Workflow Action", "ACTION-2", force=True, ignore_permissions=True),
            ],
        )
