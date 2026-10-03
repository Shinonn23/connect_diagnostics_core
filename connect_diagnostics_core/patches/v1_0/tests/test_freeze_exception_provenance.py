# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import add_freeze_exception_execution_task as patch_module


class TestFreezeExceptionProvenancePatch(UnitTestCase):
    def test_existing_task_content_is_checked(self) -> None:
        existing = type(
            "Task", (), {"tasks": [type("Row", (), {"task": "Wrong", "enabled": 1, "asynchronous": 1})()]}
        )()
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe, "get_doc", return_value=existing),
            patch.object(patch_module.frappe, "throw", side_effect=RuntimeError("conflict")) as throw,
        ):
            with self.assertRaises(RuntimeError):
                patch_module.execute()
        throw.assert_called_once()

    def test_rollback_never_deletes_unproven_owned_record(self) -> None:
        with patch.object(patch_module.frappe, "delete_doc") as delete_doc:
            patch_module.rollback()
        delete_doc.assert_not_called()
