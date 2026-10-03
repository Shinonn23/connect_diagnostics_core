# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import remove_regulation_class_doctype as patch_module


class TestRemoveRegulationClassDoctype(UnitTestCase):
    def test_no_op_when_doctype_missing(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=False) as mocked_exists,
            patch.object(patch_module.frappe, "delete_doc") as mocked_delete,
        ):
            patch_module.execute()

        mocked_exists.assert_called_once_with("DocType", "Regulation Class")
        mocked_delete.assert_not_called()

    def test_deletes_doctype_when_present(self) -> None:
        with (
            patch.object(patch_module.frappe.db, "exists", return_value=True),
            patch.object(patch_module.frappe, "delete_doc") as mocked_delete,
            patch.object(patch_module.frappe.db, "commit") as mocked_commit,
        ):
            patch_module.execute()

        mocked_delete.assert_called_once_with(
            "DocType", "Regulation Class", force=True, ignore_permissions=True
        )
        mocked_commit.assert_called_once()
