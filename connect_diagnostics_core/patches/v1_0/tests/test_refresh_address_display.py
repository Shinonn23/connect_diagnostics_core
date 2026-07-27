from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0.refresh_address_display import execute


class TestRefreshAddressDisplayPatch(UnitTestCase):
    @patch("connect_diagnostics_core.patches.v1_0.refresh_address_display.refresh_address_display_values")
    @patch("connect_diagnostics_core.patches.v1_0.refresh_address_display.sync_fixtures")
    def test_syncs_fixture_then_refreshes_all_snapshots(
        self, sync_fixtures, refresh_address_display_values
    ) -> None:
        execute()

        sync_fixtures.assert_called_once_with("connect_diagnostics_core")
        refresh_address_display_values.assert_called_once_with(
            all=True,
            include_party_primary=True,
            apply=True,
        )
