# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.frappe import role_scope_assignment as assignment_api
from connect_diagnostics_core.connect_diagnostics_stock.doctype.role_scope_assignment.role_scope_assignment import (
    RoleScopeAssignment,
)


class TestRoleScopeAssignmentController(UnitTestCase):
    def test_insert_discards_spoofed_workflow_and_grant_provenance(self) -> None:
        doc = SimpleNamespace(
            is_new=lambda: True,
            _validate_scope=Mock(),
            target_user="target@example.test",
            functional_role="Stock User",
            scope_type="Company",
            company="C1",
            department=None,
            warehouse=None,
            workflow_state="Active",
            requested_by="spoofed@example.test",
            requested_at="2000-01-01 00:00:00",
            scope_owner="spoofed-owner@example.test",
            decided_at="2000-01-01 00:00:00",
            role_grant_created=1,
            role_grant_row="spoofed-role-row",
            user_permission_created=1,
            user_permission_row="spoofed-permission-row",
        )
        RoleScopeAssignment.validate(cast(RoleScopeAssignment, doc))
        doc._validate_scope.assert_called_once()

        self.assertEqual(doc.requested_by, frappe.session.user)
        self.assertNotEqual(doc.requested_at, "2000-01-01 00:00:00")
        self.assertIsNone(doc.workflow_state)
        self.assertIsNone(doc.scope_owner)
        self.assertIsNone(doc.decided_at)
        self.assertEqual(doc.role_grant_created, 0)
        self.assertIsNone(doc.role_grant_row)
        self.assertEqual(doc.user_permission_created, 0)
        self.assertIsNone(doc.user_permission_row)

    def test_direct_submit_fails_when_workflow_is_not_authorized(self) -> None:
        doc = SimpleNamespace(name="RSA-TEST", workflow_state="Active", flags=frappe._dict())
        with (
            patch.object(assignment_api, "grant_assignment") as grant,
            self.assertRaises(frappe.ValidationError),
        ):
            RoleScopeAssignment.before_submit(cast(RoleScopeAssignment, doc))
        grant.assert_not_called()

    def test_delete_is_always_denied(self) -> None:
        doc = SimpleNamespace(name="RSA-TEST")
        with self.assertRaises(frappe.ValidationError):
            RoleScopeAssignment.on_trash(cast(RoleScopeAssignment, doc))

    def test_direct_cancel_fails_without_workflow_capability(self) -> None:
        doc = SimpleNamespace(name="RSA-TEST", workflow_state="Revoked", flags=frappe._dict())
        with self.assertRaises(frappe.ValidationError):
            RoleScopeAssignment.before_cancel(cast(RoleScopeAssignment, doc))
