# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import remove_workflow_only_roles as patch_module


class TestRemoveWorkflowOnlyRoles(UnitTestCase):
    def test_purchase_requester_is_not_targeted(self) -> None:
        names = set(patch_module.WORKFLOW_ONLY_ROLES) | set(patch_module.WORKFLOW_ONLY_ROLE_PROFILES)
        self.assertNotIn("Purchase Requester", names)
        self.assertEqual(len(patch_module.WORKFLOW_ONLY_ROLES), 3)

    def test_deletes_roles_profiles_perms_and_drops_column(self) -> None:
        deleted_docs: list[tuple[str, str]] = []
        db_deletes: list[tuple[str, dict]] = []
        ddl: list[str] = []

        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(
                patch_module.frappe.db,
                "delete",
                side_effect=lambda doctype, filters: db_deletes.append((doctype, filters)),
            ),
            patch.object(
                patch_module.frappe,
                "delete_doc",
                side_effect=lambda doctype, name, **_kw: deleted_docs.append((doctype, name)),
            ),
            patch.object(patch_module.frappe.db, "sql_ddl", side_effect=lambda s: ddl.append(s)),
        ):
            patch_module.execute()

        # Payment Request approver DocPerms cleared for both approver roles.
        self.assertEqual(
            [f for dt, f in db_deletes if dt == "Custom DocPerm"],
            [{"parent": "Payment Request", "role": r} for r in patch_module.PAYMENT_REQUEST_APPROVER_ROLES],
        )
        # Has Role assignments cleared for each workflow-only role.
        self.assertEqual(
            [f["role"] for dt, f in db_deletes if dt == "Has Role"],
            list(patch_module.WORKFLOW_ONLY_ROLES),
        )
        self.assertEqual(
            deleted_docs,
            [("Role Profile", p) for p in patch_module.WORKFLOW_ONLY_ROLE_PROFILES]
            + [("Role", r) for r in patch_module.WORKFLOW_ONLY_ROLES],
        )
        self.assertEqual(len(ddl), 1)
        self.assertIn("DROP COLUMN IF EXISTS `base_grand_total`", ddl[0])

    def test_is_a_no_op_when_already_removed(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=False),
            patch.object(patch_module.frappe.db, "commit"),
            patch.object(patch_module.frappe.db, "delete"),
            patch.object(patch_module.frappe.db, "sql_ddl"),
            patch.object(patch_module.frappe, "delete_doc") as delete_doc,
        ):
            patch_module.execute()

        delete_doc.assert_not_called()
