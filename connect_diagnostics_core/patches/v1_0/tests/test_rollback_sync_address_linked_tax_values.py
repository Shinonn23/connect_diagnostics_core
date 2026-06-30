from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock, patch

from frappe import _dict

from connect_diagnostics_core.patches.v1_0 import rollback_sync_address_linked_tax_values as rollback_module
from connect_diagnostics_core.patches.v1_0.sync_address_linked_tax_values import AddressTaxSource


class TestRollbackSyncAddressLinkedTaxValuesPatch(TestCase):
    @patch.object(rollback_module, "_get_address_values")
    @patch.object(rollback_module, "_get_linked_address_tax_sources")
    @patch.object(rollback_module, "_get_existing_fields")
    @patch.object(rollback_module, "frappe")
    def test_execute_clears_fields_matching_the_linked_source_and_commits(
        self,
        frappe: Mock,
        get_existing_fields: Mock,
        get_linked_address_tax_sources: Mock,
        get_address_values: Mock,
    ) -> None:
        get_existing_fields.return_value = ("tax_id", "branch_code")
        get_linked_address_tax_sources.return_value = [
            AddressTaxSource(
                address="ADDR-001",
                link_doctype="Supplier",
                link_name="SUPP-001",
                idx=1,
                tax_id="SUPP-TAX",
                branch_code="00001",
            ),
        ]
        get_address_values.return_value = {
            "ADDR-001": _dict(name="ADDR-001", tax_id="SUPP-TAX", branch_code="00001"),
        }

        rollback_module.execute()

        frappe.db.set_value.assert_called_once_with(
            "Address",
            "ADDR-001",
            {"tax_id": "", "branch_code": ""},
            update_modified=False,
        )
        frappe.db.commit.assert_called_once_with()

    @patch.object(rollback_module, "_get_address_values")
    @patch.object(rollback_module, "_get_linked_address_tax_sources")
    @patch.object(rollback_module, "_get_existing_fields")
    @patch.object(rollback_module, "frappe")
    def test_execute_skips_addresses_whose_current_value_no_longer_matches_the_source(
        self,
        frappe: Mock,
        get_existing_fields: Mock,
        get_linked_address_tax_sources: Mock,
        get_address_values: Mock,
    ) -> None:
        get_existing_fields.return_value = ("tax_id", "branch_code")
        get_linked_address_tax_sources.return_value = [
            AddressTaxSource(
                address="ADDR-001",
                link_doctype="Supplier",
                link_name="SUPP-001",
                idx=1,
                tax_id="SUPP-TAX",
                branch_code="00001",
            ),
        ]
        get_address_values.return_value = {
            "ADDR-001": _dict(name="ADDR-001", tax_id="USER-EDITED-TAX", branch_code="USER-EDITED-BRANCH"),
        }

        rollback_module.execute()

        frappe.db.set_value.assert_not_called()
        frappe.db.commit.assert_not_called()

    @patch.object(rollback_module, "_get_linked_address_tax_sources")
    @patch.object(rollback_module, "_get_existing_fields")
    @patch.object(rollback_module, "frappe")
    def test_execute_noop_when_tax_id_field_missing(
        self,
        frappe: Mock,
        get_existing_fields: Mock,
        get_linked_address_tax_sources: Mock,
    ) -> None:
        get_existing_fields.return_value = ()

        rollback_module.execute()

        get_linked_address_tax_sources.assert_not_called()
        frappe.db.set_value.assert_not_called()
        frappe.db.commit.assert_not_called()

    def test_get_address_values_to_clear_only_clears_matching_fields(self) -> None:
        values = rollback_module._get_address_values_to_clear(
            _dict(tax_id="SUPP-TAX", branch_code="OTHER-BRANCH"),
            AddressTaxSource(
                address="ADDR-001",
                link_doctype="Supplier",
                link_name="SUPP-001",
                idx=1,
                tax_id="SUPP-TAX",
                branch_code="00001",
            ),
            ("tax_id", "branch_code"),
        )

        self.assertEqual(values, {"tax_id": ""})
