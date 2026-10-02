# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import role_scope_assignment


class TestRoleScopeAssignmentSetup(UnitTestCase):
    def test_ensures_only_scope_owner_roles_and_never_assigns_users(self) -> None:
        with (
            patch.object(frappe.db, "get_value", return_value=None),
            patch.object(frappe, "get_doc") as get_doc,
        ):
            role_scope_assignment.ensure_configuration()

        self.assertEqual(get_doc.call_count, 3)
        self.assertEqual(
            [item.args[0]["role_name"] for item in get_doc.call_args_list],
            list(role_scope_assignment.OWNER_ROLES),
        )
        self.assertTrue(all(item.args[0]["doctype"] == "Role" for item in get_doc.call_args_list))
        self.assertEqual(get_doc.return_value.insert.call_count, 3)
        self.assertTrue(
            all(
                item.kwargs == {"ignore_permissions": True}
                for item in get_doc.return_value.insert.call_args_list
            )
        )

    def test_existing_enabled_roles_are_preserved(self) -> None:
        with (
            patch.object(
                frappe.db,
                "get_value",
                side_effect=[
                    frappe._dict(name=name, disabled=0) for name in role_scope_assignment.OWNER_ROLES
                ],
            ),
            patch.object(frappe, "get_doc") as get_doc,
        ):
            role_scope_assignment.ensure_configuration()
        get_doc.assert_not_called()

    def test_disabled_reserved_role_fails_closed(self) -> None:
        with (
            patch.object(
                frappe.db,
                "get_value",
                side_effect=[frappe._dict(name=role_scope_assignment.OWNER_ROLES[0], disabled=1)],
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            role_scope_assignment.ensure_configuration()
