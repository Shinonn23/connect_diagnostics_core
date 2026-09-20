# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import remove_withholding_tax_type_fields as patch_module


class TestRemoveWithholdingTaxTypeFields(UnitTestCase):
    def test_drops_every_field_and_commits(self) -> None:
        with (
            patch.object(patch_module, "_drop_old") as mocked_drop,
            patch.object(patch_module.frappe.db, "commit") as mocked_commit,
        ):
            patch_module.execute()

        self.assertEqual(
            [call.args for call in mocked_drop.call_args_list],
            list(patch_module._FIELDS),
        )
        mocked_commit.assert_called_once()
