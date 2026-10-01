# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext.asset_value_adjustment_workflow import (
    AssetValueAdjustmentWorkflowMixin,
)


class _NativeAVA:
    def make_asset_revaluation_entry(self) -> None:
        return None


class _AVA(AssetValueAdjustmentWorkflowMixin, _NativeAVA):
    doctype = "Asset Value Adjustment"
    name = "AVA-1"


class TestAssetValueAdjustmentWorkflow(UnitTestCase):
    def test_submit_only_invokes_native_revaluation(self) -> None:
        with patch(
            "connect_diagnostics_core.api.erpnext.asset_value_adjustment_workflow.frappe"
        ) as frappe_mock:
            frappe_mock.flags = MagicMock()
            frappe_mock.flags.journal_entry_draft_context = None
            with patch.object(_AVA, "make_asset_revaluation_entry", autospec=True) as make_entry:
                ava = _AVA()
                ava.on_submit()
                make_entry.assert_called_once_with(ava)
