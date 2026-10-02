# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Native source deletion must cascade exact Workflow Action children transactionally."""

from __future__ import annotations

from typing import cast
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.model import delete_doc as native_delete
from frappe.tests import IntegrationTestCase
from frappe.workflow.doctype.workflow_action.workflow_action import WorkflowAction


def _source() -> str:
    # This test targets native deletion, so insert a minimal Draft row without
    # invoking the unrelated Journal Entry approval and posting lifecycle.
    name = f"_TEST-WA-CLEANUP-{uuid4().hex}"
    frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "name": name,
            "voucher_type": "Journal Entry",
            "posting_date": frappe.utils.today(),
            "company": "_Test Company",
            "docstatus": 0,
        }
    ).db_insert()
    return name


def _action(doctype: str, name: str) -> tuple[str, str]:
    action = cast(
        WorkflowAction,
        frappe.get_doc(
            {
                "doctype": "Workflow Action",
                "reference_doctype": doctype,
                "reference_name": name,
                "status": "Open",
                "workflow_state": "Pending Review",
                "permitted_roles": [{"role": "Accounts User"}],
            }
        ).insert(ignore_permissions=True),
    )
    return str(action.name), str(action.permitted_roles[0].name)


class TestWorkflowActionCleanupIntegration(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.assertEqual(frappe.local.site, "local.test")
        self.old_user = frappe.session.user
        frappe.set_user("Administrator")
        self.savepoint = f"workflow_action_cleanup_{uuid4().hex}"
        frappe.db.savepoint(self.savepoint)

    def tearDown(self) -> None:
        try:
            frappe.db.rollback(save_point=self.savepoint)
            frappe.set_user(self.old_user)
        finally:
            super().tearDown()

    def test_native_source_delete_cascades_its_actions_and_preserves_unrelated(self) -> None:
        source = _source()
        other_source = _source()
        target_action, target_role = _action("Journal Entry", source)
        unrelated_action, unrelated_role = _action("Journal Entry", other_source)

        frappe.delete_doc("Journal Entry", source)

        self.assertFalse(frappe.db.exists("Journal Entry", source))
        self.assertFalse(frappe.db.exists("Workflow Action", target_action))
        self.assertFalse(frappe.db.exists("Workflow Action Permitted Role", target_role))
        self.assertTrue(frappe.db.exists("Workflow Action", unrelated_action))
        self.assertTrue(frappe.db.exists("Workflow Action Permitted Role", unrelated_role))

    def test_downstream_link_failure_rollback_restores_actions_and_children(self) -> None:
        source = _source()
        action, role = _action("Journal Entry", source)
        failure_savepoint = f"workflow_action_failure_{uuid4().hex}"
        frappe.db.savepoint(failure_savepoint)
        original_check = native_delete.check_if_doc_is_linked

        def fail_source_link_check(doc: object) -> None:
            if getattr(doc, "doctype", None) == "Journal Entry":
                raise frappe.LinkExistsError("Test source link")
            original_check(doc)

        with patch.object(native_delete, "check_if_doc_is_linked", side_effect=fail_source_link_check):
            with self.assertRaises(frappe.LinkExistsError):
                frappe.delete_doc("Journal Entry", source)

        frappe.db.rollback(save_point=failure_savepoint)
        self.assertTrue(frappe.db.exists("Journal Entry", source))
        self.assertTrue(frappe.db.exists("Workflow Action", action))
        self.assertTrue(frappe.db.exists("Workflow Action Permitted Role", role))

    def test_native_permission_denial_preserves_source_action_and_child(self) -> None:
        source = _source()
        action, role = _action("Journal Entry", source)
        try:
            frappe.set_user("Guest")
            with self.assertRaises(frappe.PermissionError):
                frappe.delete_doc("Journal Entry", source)
        finally:
            frappe.set_user("Administrator")
        self.assertTrue(frappe.db.exists("Journal Entry", source))
        self.assertTrue(frappe.db.exists("Workflow Action", action))
        self.assertTrue(frappe.db.exists("Workflow Action Permitted Role", role))


class TestWorkflowActionCleanupTwoSessions(IntegrationTestCase):
    def test_existing_action_nowait_conflict_preserves_source_until_retry(self) -> None:
        self.assertEqual(frappe.local.site, "local.test")
        old_user = frappe.session.user
        frappe.set_user("Administrator")
        sources: list[str] = []
        actions: list[str] = []
        roles: list[str] = []
        published = False
        try:
            source = _source()
            unrelated_source = _source()
            sources.extend((source, unrelated_source))
            action, role = _action("Journal Entry", source)
            unrelated_action, unrelated_role = _action("Journal Entry", unrelated_source)
            actions.extend((action, unrelated_action))
            roles.extend((role, unrelated_role))
            # A second MariaDB session can only lock rows committed by the first.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
            published = True

            with self.primary_connection():
                self.assertEqual(
                    frappe.db.get_value("Workflow Action", action, "name", for_update=True, wait=False),
                    action,
                )
                with self.secondary_connection():
                    with self.assertRaises(frappe.QueryTimeoutError):
                        frappe.delete_doc("Journal Entry", source)
                    frappe.db.rollback()
                self.assertTrue(frappe.db.exists("Journal Entry", source))
                self.assertTrue(frappe.db.exists("Workflow Action", action))
                self.assertTrue(frappe.db.exists("Workflow Action Permitted Role", role))
                self.assertTrue(frappe.db.exists("Workflow Action", unrelated_action))
                self.assertTrue(frappe.db.exists("Workflow Action Permitted Role", unrelated_role))
                frappe.db.rollback()

            frappe.delete_doc("Journal Entry", source)
            self.assertFalse(frappe.db.exists("Workflow Action", action))
            self.assertFalse(frappe.db.exists("Workflow Action Permitted Role", role))
            self.assertTrue(frappe.db.exists("Workflow Action", unrelated_action))
            self.assertTrue(frappe.db.exists("Workflow Action Permitted Role", unrelated_role))
        finally:
            frappe.local.db = self._primary_connection
            frappe.db.rollback()
            if self._secondary_connection is not None:
                self._secondary_connection.rollback()
            if published:
                for source_name in sources:
                    if frappe.db.exists("Journal Entry", source_name):
                        frappe.delete_doc("Journal Entry", source_name)
                for action_name in actions:
                    if frappe.db.exists("Workflow Action", action_name):
                        frappe.delete_doc("Workflow Action", action_name, ignore_permissions=True)
                frappe.db.commit()  # nosemgrep: frappe-manual-commit
                for doctype, names in (
                    ("Journal Entry", sources),
                    ("Workflow Action", actions),
                    ("Workflow Action Permitted Role", roles),
                ):
                    for name in names:
                        self.assertFalse(frappe.db.exists(doctype, name), f"Owned {doctype} {name} remains")
            frappe.set_user(old_user)
