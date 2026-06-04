from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock, patch

from click.testing import CliRunner

from connect_diagnostics_core.commands.sync_address_party_tax import sync_address_party_tax
from connect_diagnostics_core.utils.address import SyncAddressPartyTaxResult


class TestSyncAddressPartyTaxCommand(TestCase):
    @patch("connect_diagnostics_core.commands.sync_address_party_tax.sync_address_party_tax_values")
    @patch("connect_diagnostics_core.commands.sync_address_party_tax.frappe")
    def test_preview_does_not_commit(self, frappe: Mock, sync_address_party_tax_values: Mock) -> None:
        sync_address_party_tax_values.return_value = SyncAddressPartyTaxResult(
            changed=1,
            unchanged=2,
            skipped=3,
            conflict=4,
        )

        result = CliRunner().invoke(
            sync_address_party_tax,
            ["--address", "CUST-001-Billing"],
            obj={"sites": ["dev.local"], "profile": False},
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("dev.local: preview changed=1 unchanged=2 skipped=3 conflict=4", result.output)
        frappe.db.commit.assert_not_called()
        frappe.destroy.assert_called_once_with()

    @patch("connect_diagnostics_core.commands.sync_address_party_tax.sync_address_party_tax_values")
    @patch("connect_diagnostics_core.commands.sync_address_party_tax.frappe")
    def test_apply_commits(self, frappe: Mock, sync_address_party_tax_values: Mock) -> None:
        sync_address_party_tax_values.return_value = SyncAddressPartyTaxResult(changed=1)

        result = CliRunner().invoke(
            sync_address_party_tax,
            ["--party-type", "Customer", "--party", "CUST-001", "--overwrite", "--apply"],
            obj={"sites": ["dev.local"], "profile": False},
        )

        self.assertEqual(result.exit_code, 0, result.output)
        sync_address_party_tax_values.assert_called_once_with(
            addresses=(),
            party_type="Customer",
            party="CUST-001",
            overwrite=True,
            apply=True,
        )
        frappe.db.commit.assert_called_once_with()

    def test_party_requires_party_type(self) -> None:
        result = CliRunner().invoke(
            sync_address_party_tax,
            ["--party", "CUST-001"],
            obj={"sites": ["dev.local"], "profile": False},
        )

        self.assertEqual(result.exit_code, 2)
        self.assertIn("--party requires --party-type", result.output)

    @patch("connect_diagnostics_core.commands.sync_address_party_tax.sync_address_party_tax_values")
    @patch("connect_diagnostics_core.commands.sync_address_party_tax.frappe")
    def test_error_rolls_back(self, frappe: Mock, sync_address_party_tax_values: Mock) -> None:
        sync_address_party_tax_values.side_effect = RuntimeError("boom")

        result = CliRunner().invoke(
            sync_address_party_tax,
            ["--address", "CUST-001-Billing", "--apply"],
            obj={"sites": ["dev.local"], "profile": False},
        )

        self.assertNotEqual(result.exit_code, 0)
        frappe.db.rollback.assert_called_once_with()
        frappe.destroy.assert_called_once_with()
