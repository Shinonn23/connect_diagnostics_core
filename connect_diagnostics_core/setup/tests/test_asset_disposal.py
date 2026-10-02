# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import asset_disposal


class TestAssetDisposalSetup(UnitTestCase):
    def test_disabled_existing_role_blocks_configuration(self) -> None:
        with patch.object(
            frappe.db, "get_value", return_value=frappe._dict(name="Asset Administrator", disabled=1)
        ):
            with self.assertRaises(frappe.ValidationError):
                asset_disposal.preflight()

    def test_existing_enabled_role_is_not_recreated_or_assigned(self) -> None:
        with (
            patch.object(
                frappe.db, "get_value", return_value=frappe._dict(name="Asset Administrator", disabled=0)
            ),
            patch.object(frappe.db, "exists", return_value=True),
            patch.object(frappe, "get_doc") as get_doc,
        ):
            asset_disposal.apply_configuration()
        get_doc.assert_not_called()
