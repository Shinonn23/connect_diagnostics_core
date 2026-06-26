from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from click.testing import CliRunner

from connect_diagnostics_core.commands.refresh_address_display import refresh_address_display
from connect_diagnostics_core.utils.address import RefreshAddressDisplayResult


class TestRefreshAddressDisplayCommand(TestCase):
    @patch("connect_diagnostics_core.commands.refresh_address_display.refresh_address_display_values")
    @patch("connect_diagnostics_core.commands.refresh_address_display.frappe")
    def test_preview_does_not_commit(self, frappe: Mock, refresh_address_display_values: Mock) -> None:
        refresh_address_display_values.return_value = RefreshAddressDisplayResult(changed=1, unchanged=2)

        result = CliRunner().invoke(
            refresh_address_display,
            ["--doctype", "Sales Invoice"],
            obj=SimpleNamespace(sites=["dev.local"], profile=False),
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("dev.local: preview changed=1 unchanged=2 dangling=0", result.output)
        frappe.db.commit.assert_not_called()
        frappe.destroy.assert_called_once_with()

    @patch("connect_diagnostics_core.commands.refresh_address_display.sync_fixtures_for_app")
    @patch("connect_diagnostics_core.commands.refresh_address_display.refresh_address_display_values")
    @patch("connect_diagnostics_core.commands.refresh_address_display.frappe")
    def test_apply_can_sync_fixtures_and_commits(
        self,
        frappe: Mock,
        refresh_address_display_values: Mock,
        sync_fixtures_for_app: Mock,
    ) -> None:
        refresh_address_display_values.return_value = RefreshAddressDisplayResult()

        result = CliRunner().invoke(
            refresh_address_display,
            ["--all", "--sync-fixtures", "--apply"],
            obj=SimpleNamespace(sites=["dev.local"], profile=False),
        )

        self.assertEqual(result.exit_code, 0, result.output)
        sync_fixtures_for_app.assert_called_once_with()
        frappe.db.commit.assert_called_once_with()

    def test_sync_fixtures_requires_apply(self) -> None:
        result = CliRunner().invoke(
            refresh_address_display,
            ["--all", "--sync-fixtures"],
            obj=SimpleNamespace(sites=["dev.local"], profile=False),
        )

        self.assertEqual(result.exit_code, 2)
        self.assertIn("--sync-fixtures requires --apply", result.output)
