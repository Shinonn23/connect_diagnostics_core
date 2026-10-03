# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import remove_item_regulation_class_field as patch_module


class TestRemoveItemRegulationClassField(UnitTestCase):
    def test_drops_the_field_and_commits(self) -> None:
        with (
            patch.object(patch_module, "_drop_old") as mocked_drop,
            patch.object(patch_module.frappe.db, "commit") as mocked_commit,
        ):
            patch_module.execute()

        mocked_drop.assert_called_once_with("Item", "regulation_class")
        mocked_commit.assert_called_once()
