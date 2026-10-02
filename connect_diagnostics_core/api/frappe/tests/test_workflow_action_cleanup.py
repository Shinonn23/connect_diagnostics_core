# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.frappe.workflow_action_cleanup import delete_linked_actions


class TestWorkflowActionCleanup(UnitTestCase):
    def test_exact_source_binding_sorted_once_and_native_deletion(self) -> None:
        source = Document({"doctype": "Journal Entry", "name": "JE-TEST-001"})
        with (
            patch.object(frappe.db, "get_values", return_value=["B", "A", "B"]) as get_values,
            patch("frappe.delete_doc") as delete_doc,
        ):
            delete_linked_actions(source, "on_trash")

        get_values.assert_called_once_with(
            "Workflow Action",
            {"reference_doctype": "Journal Entry", "reference_name": "JE-TEST-001"},
            "name",
            pluck=True,
            for_update=True,
            wait=False,
            order_by="name",
        )
        self.assertEqual(
            delete_doc.call_args_list,
            [
                (("Workflow Action", "A"), {"ignore_permissions": True, "delete_permanently": True}),
                (("Workflow Action", "B"), {"ignore_permissions": True, "delete_permanently": True}),
            ],
        )

    def test_unrelated_source_or_method_fails_before_database_access(self) -> None:
        cases = (
            (Document({"doctype": "ToDo", "name": "TD-1"}), "on_trash"),
            (Document({"doctype": "Journal Entry"}), "on_trash"),
            (Document({"doctype": "Journal Entry", "name": "JE-1"}), "validate"),
        )
        with (
            patch(
                "connect_diagnostics_core.api.frappe.workflow_action_cleanup._", side_effect=lambda text: text
            ),
            patch("frappe.throw", side_effect=frappe.ValidationError) as throw,
            patch.object(frappe.db, "get_values") as get_values,
            patch("frappe.delete_doc") as delete_doc,
        ):
            for source, method in cases:
                with self.subTest(source=source.doctype, method=method):
                    with self.assertRaises(frappe.ValidationError):
                        delete_linked_actions(source, method)
            get_values.assert_not_called()
            delete_doc.assert_not_called()
            self.assertEqual(throw.call_count, len(cases))

    def test_action_delete_error_propagates_without_commit(self) -> None:
        source = Document({"doctype": "Sales Order", "name": "SO-TEST-001"})
        with (
            patch.object(frappe.db, "get_values", return_value=["A", "B"]),
            patch("frappe.delete_doc", side_effect=[None, frappe.QueryTimeoutError("locked")]) as delete_doc,
            patch.object(frappe.db, "commit") as commit,
        ):
            with self.assertRaises(frappe.QueryTimeoutError):
                delete_linked_actions(source, "on_trash")
        self.assertEqual(delete_doc.call_count, 2)
        commit.assert_not_called()
