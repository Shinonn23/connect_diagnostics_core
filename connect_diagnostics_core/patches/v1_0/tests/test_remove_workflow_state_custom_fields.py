# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import remove_workflow_state_custom_fields as patch_module


class TestRemoveWorkflowStateCustomFields(UnitTestCase):
    def test_targets_the_seven_workflow_state_fields(self) -> None:
        self.assertEqual(len(patch_module.WORKFLOW_STATE_FIELDS), 7)
        fieldnames = {fieldname for _doctype, fieldname in patch_module.WORKFLOW_STATE_FIELDS}
        self.assertEqual(
            fieldnames,
            {
                "payment_approval_state",
                "salary_slip_review_state",
                "supplier_onboarding_state",
                "p2p_workflow_state",
            },
        )

    def test_deletes_custom_fields_and_drops_columns(self) -> None:
        dropped_columns: list[str] = []
        deleted_fields: list[str] = []

        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe.db, "has_column", return_value=True),
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(
                patch_module.frappe,
                "delete_doc",
                side_effect=lambda _dt, name, **_kw: deleted_fields.append(name),
            ),
            patch.object(
                patch_module.frappe.db,
                "sql_ddl",
                side_effect=lambda statement: dropped_columns.append(statement),
            ),
        ):
            patch_module.execute()

        self.assertEqual(
            deleted_fields,
            [f"{dt}-{fn}" for dt, fn in patch_module.WORKFLOW_STATE_FIELDS],
        )
        self.assertEqual(len(dropped_columns), 7)
        for (doctype, fieldname), statement in zip(
            patch_module.WORKFLOW_STATE_FIELDS, dropped_columns, strict=True
        ):
            self.assertIn(f"`tab{doctype}`", statement)
            self.assertIn(f"`{fieldname}`", statement)

    def test_is_a_no_op_when_already_removed(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=False),
            patch.object(patch_module.frappe.db, "has_column", return_value=False),
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(patch_module.frappe, "delete_doc") as delete_doc,
            patch.object(patch_module.frappe.db, "sql_ddl") as sql_ddl,
        ):
            patch_module.execute()

        delete_doc.assert_not_called()
        sql_ddl.assert_not_called()
