# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, patch

import frappe
from frappe.model import workflow as native_workflow
from frappe.model.docstatus import DocStatus
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.frappe import role_scope_assignment as assignment_api
from connect_diagnostics_core.connect_diagnostics_stock.doctype.role_scope_assignment.role_scope_assignment import (
    RoleScopeAssignment,
)


class _TestDocument(SimpleNamespace):
    def get(self, fieldname: str, default: object = None) -> object:
        return getattr(self, fieldname, default)

    def set(self, fieldname: str, value: object) -> None:
        setattr(self, fieldname, value)

    def append(self, fieldname: str, value: dict[str, object]) -> _TestDocument:
        row = _TestDocument(**value, name="HR-created")
        getattr(self, fieldname).append(row)
        return row


class _WorkflowDocument(_TestDocument):
    def __init__(self, name: str, docstatus: int):
        super().__init__(
            doctype="Role Scope Assignment",
            name=name,
            workflow_state="Draft",
            docstatus=DocStatus(docstatus),
            meta=SimpleNamespace(queue_in_background=0),
            flags=frappe._dict(),
            lifecycle_events=[],
            is_new=lambda: False,
            _validate_scope=lambda: None,
        )

    def load_from_db(self) -> _WorkflowDocument:
        self.lifecycle_events.append("load")
        return self

    def save(self) -> _WorkflowDocument:
        self._action = "save"
        RoleScopeAssignment.validate(cast(RoleScopeAssignment, self))
        self.lifecycle_events.append("save")
        return self

    def submit(self) -> _WorkflowDocument:
        self._action = "submit"
        self.docstatus = DocStatus(1)
        RoleScopeAssignment.validate(cast(RoleScopeAssignment, self))
        RoleScopeAssignment.before_submit(cast(RoleScopeAssignment, self))
        self.lifecycle_events.append("submit")
        return self

    def cancel(self) -> _WorkflowDocument:
        self._action = "cancel"
        self.docstatus = DocStatus(2)
        RoleScopeAssignment.before_cancel(cast(RoleScopeAssignment, self))
        self.lifecycle_events.append("cancel")
        return self

    def add_comment(self, comment_type: str, content: str) -> None:
        self.lifecycle_events.append("comment")


class TestRoleScopeAssignmentHelpers(UnitTestCase):
    def test_native_apply_workflow_keeps_capability_until_exact_lifecycle_hook(self) -> None:
        cases = (
            ("Request Assignment", "Pending Owner Approval", 0, 0, "save"),
            ("Approve Assignment", "Active", 0, 1, "submit"),
            ("Reject Assignment", "Rejected", 0, 0, "save"),
            ("Cancel", "Revoked", 1, 2, "cancel"),
        )
        for action, next_state, old_status, new_status, operation in cases:
            with self.subTest(action=action):
                self._apply_native_transition(action, next_state, old_status, new_status, operation)

    def _apply_native_transition(
        self, action: str, next_state: str, old_status: int, new_status: int, operation: str
    ) -> None:
        name = f"RSA-{action}"
        doc = _WorkflowDocument(name, old_status)
        task_name = "Authorize Role Scope Assignment Transition"
        transition = frappe._dict(action=action, next_state=next_state, transition_tasks="WF15 Test Tasks")
        workflow = frappe._dict(
            workflow_state_field="workflow_state",
            states=[frappe._dict(state=next_state, doc_status=new_status)],
        )

        def callback(loaded_doc: _WorkflowDocument) -> None:
            doc.lifecycle_events.append("task")
            assignment_api.authorize_workflow_transition(cast(Document, loaded_doc), name, action, operation)

        with (
            patch.object(native_workflow, "get_workflow", return_value=workflow),
            patch.object(native_workflow, "get_transitions", return_value=[transition]),
            patch.object(native_workflow, "has_approval_access", return_value=True),
            patch.object(frappe, "get_doc", return_value=doc),
            patch.object(
                frappe.db,
                "get_all",
                return_value=[frappe._dict(task=task_name, link=None, asynchronous=0)],
            ),
            patch.object(frappe, "get_hooks", return_value=[{"name": task_name, "method": "test.callback"}]),
            patch.object(frappe, "get_attr", return_value=callback),
        ):
            result = native_workflow.apply_workflow(
                json.dumps({"doctype": "Role Scope Assignment", "name": name}), action
            )

        self.assertIs(result, doc)
        self.assertEqual(doc.lifecycle_events, ["load", "task", operation, "comment"])
        self.assertEqual(doc.workflow_state, next_state)
        self.assertEqual(int(doc.docstatus), new_status)
        self.assertIsNone(doc.flags.get(assignment_api._WORKFLOW_CAPABILITY_FLAG))

    def test_transition_capability_rejects_wrong_document_action_operation_and_replay(self) -> None:
        doc = _WorkflowDocument("RSA-1", 0)
        other_doc = _WorkflowDocument("RSA-1", 0)
        assignment_api.authorize_workflow_transition(
            cast(Document, doc), "RSA-1", "Request Assignment", "save"
        )

        self.assertFalse(
            assignment_api.is_authorized_workflow_transition(
                cast(Document, other_doc), "Request Assignment", "save"
            )
        )
        self.assertFalse(
            assignment_api.is_authorized_workflow_transition(
                cast(Document, doc), "Approve Assignment", "save"
            )
        )
        self.assertFalse(
            assignment_api.is_authorized_workflow_transition(
                cast(Document, doc), "Request Assignment", "submit"
            )
        )
        with self.assertRaises(frappe.ValidationError):
            assignment_api.authorize_workflow_transition(
                cast(Document, doc), "RSA-1", "Request Assignment", "submit"
            )
        self.assertTrue(
            assignment_api.consume_workflow_transition(cast(Document, doc), "Request Assignment", "save")
        )
        self.assertFalse(
            assignment_api.consume_workflow_transition(cast(Document, doc), "Request Assignment", "save")
        )

    def test_grant_and_revoke_helpers_are_not_rpc_endpoints(self) -> None:
        self.assertFalse(getattr(assignment_api.grant_assignment, "is_whitelisted", False))
        self.assertFalse(getattr(assignment_api.revoke_assignment, "is_whitelisted", False))
        self.assertFalse(getattr(assignment_api.authorize_workflow_transition, "is_whitelisted", False))

    def test_grant_creation_persists_exact_native_grant_provenance(self) -> None:
        assignment = _TestDocument(
            name="RSA-Grant",
            target_user="target@example.test",
            functional_role="Stock User",
            scope_type="Company",
            company="C1",
        )
        target = _TestDocument(enabled=1, roles=[])
        target.save = Mock(
            side_effect=lambda **_kwargs: self.assertTrue(
                assignment_api.consume_user_role_capability("target@example.test", "Stock User", "add")
            )
        )
        permission = _TestDocument(name="UP-created", insert=Mock())

        def get_value(doctype: str, name: object, fieldname: object = None, **kwargs: object) -> object:
            if doctype == "Role":
                return "Stock User"
            if doctype == "Company":
                return "C1"
            if doctype == "User":
                return "target@example.test"
            return None

        with (
            patch.object(frappe.db, "get_value", side_effect=get_value),
            patch.object(frappe.db, "sql", return_value=[]),
            patch.object(frappe, "get_doc", side_effect=[target, permission]),
        ):
            assignment_api.grant_assignment(cast(Document, assignment))

        self.assertEqual(assignment.role_grant_created, 1)
        self.assertEqual(assignment.role_grant_row, "HR-created")
        self.assertEqual(assignment.user_permission_created, 1)
        self.assertEqual(assignment.user_permission_row, "UP-created")
        permission.insert.assert_called_once_with(ignore_permissions=True)

    def test_role_capability_is_exact_and_consumed_once(self) -> None:
        self.assertFalse(assignment_api.consume_user_role_capability("u1", "Stock User", "add"))
        token = assignment_api._arm_role_capability("RSA-1", "u1", "Stock User", "add")
        try:
            self.assertFalse(assignment_api.consume_user_role_capability("u2", "Stock User", "add"))
            self.assertFalse(assignment_api.consume_user_role_capability("u1", "Stock Manager", "add"))
            self.assertTrue(assignment_api.consume_user_role_capability("u1", "Stock User", "add"))
            self.assertFalse(assignment_api.consume_user_role_capability("u1", "Stock User", "add"))
        finally:
            assignment_api._disarm_role_capability(token)
        self.assertFalse(assignment_api.consume_user_role_capability("u1", "Stock User", "add"))

    def test_wrong_parent_company_fails_scope_binding(self) -> None:
        with (
            patch.object(frappe.db, "get_value", return_value=frappe._dict(name="D1", company="C1")),
            self.assertRaises(frappe.ValidationError),
        ):
            assignment_api.validate_scope_binding("Department", "D1", "C2")

    def test_requester_cannot_approve_even_if_scope_owner(self) -> None:
        with (
            patch.object(assignment_api, "resolve_scope_owners", return_value=["same-user"]),
            self.assertRaises(frappe.ValidationError),
        ):
            assignment_api.validate_assignment_actor(
                scope_type="Company",
                scope_name="C1",
                company="C1",
                requester="same-user",
                actor="same-user",
            )

    def test_owner_resolution_requires_exact_unrestricted_permission(self) -> None:
        with (
            patch.object(frappe.db, "get_value", return_value=frappe._dict(name="C1")),
            patch.object(frappe.db, "sql", return_value=[frappe._dict(name="owner@example.test")]) as sql,
            patch.object(frappe, "get_doc", return_value=SimpleNamespace(name="C1")),
            patch.object(frappe, "has_permission", return_value=True),
        ):
            owners = assignment_api.resolve_scope_owners("Company", "C1", "C1")
        self.assertEqual(owners, ["owner@example.test"])
        self.assertEqual(sql.call_args.args[1], ("Company Owner", "Company", "C1"))
        self.assertIn("up.applicable_for IS NULL OR up.applicable_for = ''", sql.call_args.args[0])
        self.assertIn("FOR UPDATE", sql.call_args.args[0])

    def test_existing_role_and_exact_permission_are_not_claimed_as_owned(self) -> None:
        target = _TestDocument(enabled=1, roles=[_TestDocument(role="Stock User", name="HR-1")], save=Mock())
        assignment = _TestDocument(
            name="RSA-1",
            target_user="target@example.test",
            functional_role="Stock User",
            scope_type="Company",
            company="C1",
        )

        def get_value(doctype: str, name: object, fieldname: object = None, **kwargs: object) -> object:
            if doctype == "Role":
                return "Stock User"
            if doctype == "Company":
                return "C1"
            if doctype == "User":
                return "target@example.test"
            return None

        with (
            patch.object(frappe.db, "get_value", side_effect=get_value),
            patch.object(frappe.db, "sql", return_value=[frappe._dict(name="UP-existing")]),
            patch.object(frappe, "get_doc", return_value=target) as get_doc,
        ):
            assignment_api.grant_assignment(cast(Document, assignment))
        self.assertEqual(assignment.role_grant_created, 0)
        self.assertIsNone(assignment.role_grant_row)
        self.assertEqual(assignment.user_permission_created, 0)
        self.assertIsNone(assignment.user_permission_row)
        target.save.assert_not_called()
        get_doc.assert_called_once_with("User", "target@example.test")

    def test_revoke_deletes_only_the_exact_owned_rows(self) -> None:
        target = _TestDocument(
            enabled=1,
            roles=[_TestDocument(role="Stock User", name="HR-owned")],
            save=Mock(),
        )
        target.save.side_effect = lambda **kwargs: self.assertTrue(
            assignment_api.consume_user_role_capability("target@example.test", "Stock User", "remove")
        )
        assignment = _TestDocument(
            name="RSA-1",
            target_user="target@example.test",
            functional_role="Stock User",
            scope_type="Company",
            company="C1",
            user_permission_created=1,
            user_permission_row="UP-owned",
            role_grant_created=1,
            role_grant_row="HR-owned",
        )
        permission_row = frappe._dict(
            name="UP-owned",
            user="target@example.test",
            allow="Company",
            for_value="C1",
            apply_to_all_doctypes=1,
            hide_descendants=1,
            applicable_for=None,
        )

        def get_value(doctype: str, name: object, fieldname: object = None, **kwargs: object) -> object:
            if doctype == "Company":
                return "C1"
            if doctype == "User":
                return "target@example.test"
            if doctype == "User Permission":
                return permission_row
            if doctype == "Has Role":
                return frappe._dict(
                    name="HR-owned",
                    parent="target@example.test",
                    role="Stock User",
                    parenttype="User",
                )
            return None

        with (
            patch.object(frappe.db, "get_value", side_effect=get_value),
            patch.object(frappe, "get_doc", return_value=target),
            patch.object(frappe, "get_all", return_value=[]),
            patch.object(frappe, "delete_doc") as delete_doc,
        ):
            assignment_api.revoke_assignment(cast(Document, assignment))
        delete_doc.assert_called_once_with("User Permission", "UP-owned", ignore_permissions=True)
        target.save.assert_called_once_with(ignore_permissions=True)

    def test_stale_permission_provenance_is_preserved(self) -> None:
        assignment = _TestDocument(
            name="RSA-1",
            target_user="target@example.test",
            functional_role="Stock User",
            scope_type="Company",
            company="C1",
            user_permission_created=1,
            user_permission_row="UP-owned",
            role_grant_created=0,
            role_grant_row=None,
        )
        target = _TestDocument(enabled=1, roles=[])
        stale = frappe._dict(
            name="UP-owned",
            user="target@example.test",
            allow="Company",
            for_value="C-other",
            apply_to_all_doctypes=1,
            hide_descendants=1,
            applicable_for=None,
        )

        def get_value(doctype: str, name: object, fieldname: object = None, **kwargs: object) -> object:
            if doctype == "Company":
                return "C1"
            if doctype == "User":
                return "target@example.test"
            if doctype == "User Permission":
                return stale
            return None

        with (
            patch.object(frappe.db, "get_value", side_effect=get_value),
            patch.object(frappe, "get_doc", return_value=target),
            patch.object(frappe, "get_all", return_value=[]),
            patch.object(frappe, "delete_doc") as delete_doc,
        ):
            assignment_api.revoke_assignment(cast(Document, assignment))
        delete_doc.assert_not_called()

    def test_revoking_role_owner_hands_provenance_to_another_active_assignment(self) -> None:
        target = _TestDocument(
            enabled=1,
            roles=[_TestDocument(role="Stock User", name="HR-owned")],
            save=Mock(),
        )
        assignment = _TestDocument(
            name="RSA-1",
            target_user="target@example.test",
            functional_role="Stock User",
            scope_type="Company",
            company="C1",
            user_permission_created=0,
            user_permission_row=None,
            role_grant_created=1,
            role_grant_row="HR-owned",
        )

        def get_value(doctype: str, name: object, fieldname: object = None, **kwargs: object) -> object:
            if doctype == "Company":
                return "C1"
            if doctype == "User":
                return "target@example.test"
            if doctype == "Has Role":
                return frappe._dict(
                    name="HR-owned",
                    parent="target@example.test",
                    role="Stock User",
                    parenttype="User",
                )
            return None

        with (
            patch.object(frappe.db, "get_value", side_effect=get_value),
            patch.object(frappe.db, "set_value") as set_value,
            patch.object(frappe, "get_doc", return_value=target),
            patch.object(
                frappe,
                "get_all",
                return_value=[frappe._dict(name="RSA-2", role_grant_created=0, role_grant_row=None)],
            ),
        ):
            assignment_api.revoke_assignment(cast(Document, assignment))

        set_value.assert_called_once_with(
            "Role Scope Assignment",
            "RSA-2",
            {"role_grant_created": 1, "role_grant_row": "HR-owned"},
        )
        target.save.assert_not_called()

    def test_revoking_permission_owner_hands_provenance_to_same_scope_assignment(self) -> None:
        assignment = _TestDocument(
            name="RSA-1",
            target_user="target@example.test",
            functional_role="Stock User",
            scope_type="Company",
            company="C1",
            user_permission_created=1,
            user_permission_row="UP-owned",
            role_grant_created=0,
            role_grant_row=None,
        )
        target = _TestDocument(enabled=1, roles=[])
        permission_row = frappe._dict(
            name="UP-owned",
            user="target@example.test",
            allow="Company",
            for_value="C1",
            apply_to_all_doctypes=1,
            hide_descendants=1,
            applicable_for=None,
        )

        def get_value(doctype: str, name: object, fieldname: object = None, **kwargs: object) -> object:
            if doctype == "Company":
                return "C1"
            if doctype == "User":
                return "target@example.test"
            if doctype == "User Permission":
                return permission_row
            return None

        with (
            patch.object(frappe.db, "get_value", side_effect=get_value),
            patch.object(frappe.db, "set_value") as set_value,
            patch.object(frappe, "get_doc", return_value=target),
            patch.object(
                frappe,
                "get_all",
                return_value=[
                    frappe._dict(name="RSA-2", user_permission_created=0, user_permission_row=None)
                ],
            ),
            patch.object(frappe, "delete_doc") as delete_doc,
        ):
            assignment_api.revoke_assignment(cast(Document, assignment))

        set_value.assert_called_once_with(
            "Role Scope Assignment",
            "RSA-2",
            {"user_permission_created": 1, "user_permission_row": "UP-owned"},
        )
        delete_doc.assert_not_called()
