# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import (
    move_dksh_item_to_dksh_module,
    rollback_move_dksh_item_to_dksh_module,
)


class TestModuleMapRefresh(UnitTestCase):
    def test_refresh_drops_the_cached_module_lists_and_rebuilds_the_map(self) -> None:
        cache = MagicMock()
        client_cache = MagicMock()
        setup_module_map = MagicMock()
        with (
            patch.object(move_dksh_item_to_dksh_module.frappe, "cache", cache),
            patch.object(move_dksh_item_to_dksh_module.frappe, "client_cache", client_cache),
            patch.object(move_dksh_item_to_dksh_module.frappe, "setup_module_map", setup_module_map),
        ):
            move_dksh_item_to_dksh_module._refresh_module_map()

        cache.delete_value.assert_called_once_with("app_modules")
        client_cache.delete_value.assert_called_once_with("installed_app_modules")
        setup_module_map.assert_called_once_with()


class TestExecute(UnitTestCase):
    def test_execute_refreshes_the_map_then_repoints_and_reloads(self) -> None:
        recorder = MagicMock()
        with (
            patch.object(move_dksh_item_to_dksh_module, "_refresh_module_map", recorder.refresh),
            patch.object(move_dksh_item_to_dksh_module.frappe.db, "exists", return_value=True),
            patch.object(move_dksh_item_to_dksh_module.frappe.db, "set_value", recorder.set_value),
            patch.object(move_dksh_item_to_dksh_module.frappe, "reload_doc", recorder.reload_doc),
            patch.object(move_dksh_item_to_dksh_module.frappe, "clear_cache", MagicMock()),
        ):
            move_dksh_item_to_dksh_module.execute()

        recorder.set_value.assert_called_once_with(
            "DocType", "DKSH Item", "module", "Connect Diagnostics DKSH"
        )
        recorder.reload_doc.assert_called_once_with(
            "Connect Diagnostics DKSH", "doctype", "dksh_item", force=True
        )
        calls = [call[0] for call in recorder.mock_calls]
        self.assertLess(calls.index("refresh"), calls.index("reload_doc"))

    def test_execute_skips_repointing_when_the_doctype_is_missing(self) -> None:
        set_value = MagicMock()
        with (
            patch.object(move_dksh_item_to_dksh_module, "_refresh_module_map", MagicMock()),
            patch.object(move_dksh_item_to_dksh_module.frappe.db, "exists", return_value=False),
            patch.object(move_dksh_item_to_dksh_module.frappe.db, "set_value", set_value),
            patch.object(move_dksh_item_to_dksh_module.frappe, "reload_doc", MagicMock()),
            patch.object(move_dksh_item_to_dksh_module.frappe, "clear_cache", MagicMock()),
        ):
            move_dksh_item_to_dksh_module.execute()

        set_value.assert_not_called()


class TestRollback(UnitTestCase):
    def test_rollback_repoints_the_doctype_back_to_core(self) -> None:
        set_value = MagicMock()
        with (
            patch.object(rollback_move_dksh_item_to_dksh_module, "_refresh_module_map", MagicMock()),
            patch.object(rollback_move_dksh_item_to_dksh_module.frappe.db, "exists", return_value=True),
            patch.object(rollback_move_dksh_item_to_dksh_module.frappe.db, "set_value", set_value),
            patch.object(rollback_move_dksh_item_to_dksh_module.frappe, "clear_cache", MagicMock()),
        ):
            rollback_move_dksh_item_to_dksh_module.execute()

        set_value.assert_called_once_with("DocType", "DKSH Item", "module", "Connect Diagnostics Core")
