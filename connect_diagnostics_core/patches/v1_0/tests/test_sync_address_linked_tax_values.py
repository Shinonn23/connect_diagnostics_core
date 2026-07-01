from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, call, patch

from frappe import _dict

from connect_diagnostics_core.patches.v1_0 import sync_address_linked_tax_values as patch_module
from connect_diagnostics_core.patches.v1_0.sync_address_linked_tax_values import AddressTaxSource


class TestSyncAddressLinkedTaxValuesPatch(TestCase):
    @patch.object(patch_module, "refresh_address_display_values")
    @patch.object(patch_module, "sync_linked_address_tax_values")
    @patch.object(patch_module, "frappe")
    def test_execute_refreshes_address_displays_after_changes(
        self,
        frappe: Mock,
        sync_linked_address_tax_values: Mock,
        refresh_address_display_values: Mock,
    ) -> None:
        sync_linked_address_tax_values.return_value = 1

        patch_module.execute()

        refresh_address_display_values.assert_called_once_with(
            all=True,
            include_party_primary=True,
            apply=True,
        )
        frappe.db.commit.assert_called_once_with()

    @patch.object(patch_module, "refresh_address_display_values")
    @patch.object(patch_module, "sync_linked_address_tax_values")
    @patch.object(patch_module, "frappe")
    def test_execute_skips_refresh_when_nothing_changed(
        self,
        frappe: Mock,
        sync_linked_address_tax_values: Mock,
        refresh_address_display_values: Mock,
    ) -> None:
        sync_linked_address_tax_values.return_value = 0

        patch_module.execute()

        refresh_address_display_values.assert_not_called()
        frappe.db.commit.assert_not_called()

    def test_selects_customer_supplier_company_before_generic_doctype(self) -> None:
        selected = patch_module._select_address_tax_sources(
            [
                AddressTaxSource(
                    address="ADDR-001",
                    link_doctype="Sales Invoice",
                    link_name="SINV-001",
                    idx=1,
                    tax_id="GENERIC-TAX",
                ),
                AddressTaxSource(
                    address="ADDR-001",
                    link_doctype="Company",
                    link_name="Company A",
                    idx=2,
                    tax_id="COMPANY-TAX",
                ),
                AddressTaxSource(
                    address="ADDR-001",
                    link_doctype="Customer",
                    link_name="CUST-001",
                    idx=3,
                    tax_id="CUSTOMER-TAX",
                ),
            ]
        )

        self.assertEqual(selected["ADDR-001"].link_doctype, "Customer")
        self.assertEqual(selected["ADDR-001"].tax_id, "CUSTOMER-TAX")

    def test_get_address_values_to_set_overwrites_different_values(self) -> None:
        values = patch_module._get_address_values_to_set(
            _dict(tax_id="OLD-TAX", branch_code="OLD-BRANCH"),
            AddressTaxSource(
                address="ADDR-001",
                link_doctype="Supplier",
                link_name="SUPP-001",
                idx=1,
                tax_id="NEW-TAX",
                branch_code="00000",
            ),
            ("tax_id", "branch_code"),
        )

        self.assertEqual(values, {"tax_id": "NEW-TAX", "branch_code": "00000"})

    @patch.object(patch_module, "_get_linked_address_tax_sources")
    @patch.object(patch_module, "frappe")
    def test_sync_updates_selected_addresses_without_touching_modified(
        self,
        frappe: Mock,
        get_linked_address_tax_sources: Mock,
    ) -> None:
        address_meta = Mock()
        address_meta.get_field.side_effect = lambda fieldname: fieldname in {"tax_id", "branch_code"}
        frappe.get_meta.return_value = address_meta
        get_linked_address_tax_sources.return_value = [
            AddressTaxSource(
                address="ADDR-001",
                link_doctype="Supplier",
                link_name="SUPP-001",
                idx=1,
                tax_id="SUPP-TAX",
                branch_code="00001",
            ),
            AddressTaxSource(
                address="ADDR-002",
                link_doctype="Company",
                link_name="Company A",
                idx=1,
                tax_id="COMPANY-TAX",
            ),
        ]
        frappe.get_all.return_value = [
            _dict(name="ADDR-001", tax_id=None, branch_code=None),
            _dict(name="ADDR-002", tax_id="COMPANY-TAX", branch_code=None),
        ]

        changed = patch_module.sync_linked_address_tax_values()

        self.assertEqual(changed, 1)
        frappe.db.set_value.assert_called_once_with(
            "Address",
            "ADDR-001",
            {"tax_id": "SUPP-TAX", "branch_code": "00001"},
            update_modified=False,
        )

    @patch.object(patch_module, "frappe")
    def test_get_linked_address_tax_sources_reads_any_linked_doctype_with_tax_fields(
        self, frappe: Mock
    ) -> None:
        frappe.get_all.side_effect = [
            [
                _dict(parent="ADDR-001", link_doctype="Customer", link_name="CUST-001", idx=2),
                _dict(parent="ADDR-002", link_doctype="Company", link_name="Company A", idx=1),
                _dict(parent="ADDR-003", link_doctype="Lead", link_name="LEAD-001", idx=1),
            ],
            [_dict(name="CUST-001", tax_id="CUST-TAX", branch_code="00000")],
            [_dict(name="Company A", tax_id="COMPANY-TAX")],
            [_dict(name="LEAD-001", tax_id="LEAD-TAX")],
        ]
        frappe.db.table_exists.return_value = True

        def get_meta(doctype: str) -> SimpleNamespace:
            fields_by_doctype = {
                "Customer": {"tax_id", "branch_code"},
                "Company": {"tax_id"},
                "Lead": {"tax_id"},
            }
            fields = fields_by_doctype[doctype]
            return SimpleNamespace(
                issingle=False,
                is_virtual=False,
                get_field=lambda fieldname: fieldname in fields,
            )

        frappe.get_meta.side_effect = get_meta

        sources = patch_module._get_linked_address_tax_sources(include_branch=True)

        self.assertEqual(
            sources,
            [
                AddressTaxSource(
                    address="ADDR-001",
                    link_doctype="Customer",
                    link_name="CUST-001",
                    idx=2,
                    tax_id="CUST-TAX",
                    branch_code="00000",
                ),
                AddressTaxSource(
                    address="ADDR-002",
                    link_doctype="Company",
                    link_name="Company A",
                    idx=1,
                    tax_id="COMPANY-TAX",
                    branch_code=None,
                ),
                AddressTaxSource(
                    address="ADDR-003",
                    link_doctype="Lead",
                    link_name="LEAD-001",
                    idx=1,
                    tax_id="LEAD-TAX",
                    branch_code=None,
                ),
            ],
        )
        self.assertEqual(
            frappe.get_all.call_args_list[0],
            call(
                "Dynamic Link",
                filters={"parenttype": "Address"},
                fields=["parent", "link_doctype", "link_name", "idx"],
                order_by="parent asc, idx asc",
            ),
        )
