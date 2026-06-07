from __future__ import annotations

from unittest import TestCase
from unittest.mock import call, patch

from connect_diagnostics_core.patches.v1_0 import disable_quick_entry as patch_module


class TestDisableQuickEntryPatch(TestCase):
    @patch.object(patch_module, "make_property_setter")
    @patch.object(patch_module, "frappe")
    def test_execute_disables_doctype_and_property_setter_quick_entry(
        self, frappe, make_property_setter
    ) -> None:
        frappe.get_all.side_effect = [
            [{"name": "Customer"}, {"name": "Supplier"}],
            [{"doc_type": "Item"}, {"doc_type": "Customer"}],
        ]
        frappe.db.exists.return_value = None

        patch_module.execute()

        self.assertEqual(
            make_property_setter.call_args_list,
            [
                call(
                    "Customer",
                    None,
                    "quick_entry",
                    "0",
                    "Check",
                    for_doctype=True,
                    validate_fields_for_doctype=False,
                ),
                call(
                    "Item",
                    None,
                    "quick_entry",
                    "0",
                    "Check",
                    for_doctype=True,
                    validate_fields_for_doctype=False,
                ),
                call(
                    "Supplier",
                    None,
                    "quick_entry",
                    "0",
                    "Check",
                    for_doctype=True,
                    validate_fields_for_doctype=False,
                ),
            ],
        )
        self.assertEqual(
            frappe.clear_cache.call_args_list,
            [
                call(doctype="Customer"),
                call(doctype="Item"),
                call(doctype="Supplier"),
            ],
        )

    @patch.object(patch_module, "make_property_setter")
    @patch.object(patch_module, "frappe")
    def test_set_quick_entry_property_setter_updates_existing_setter(
        self, frappe, make_property_setter
    ) -> None:
        frappe.db.exists.return_value = "Customer-main-quick_entry"

        patch_module._set_quick_entry_property_setter("Customer")

        make_property_setter.assert_not_called()
        frappe.db.set_value.assert_called_once_with(
            "Property Setter",
            "Customer-main-quick_entry",
            "value",
            "0",
            update_modified=False,
        )
