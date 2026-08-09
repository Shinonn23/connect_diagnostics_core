# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from unittest.mock import call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import remove_legacy_print_formats as patch_module


class TestRemoveLegacyPrintFormatsPatch(UnitTestCase):
    @patch.object(patch_module, "frappe")
    def test_execute_deletes_existing_legacy_print_formats(self, frappe) -> None:
        existing_print_formats = {
            "CD Purchase Order Print",
            "CD Sales Invoice Print",
        }

        def exists(doctype, name):
            return name if doctype == "Print Format" and name in existing_print_formats else None

        frappe.db.exists.side_effect = exists
        frappe.get_all.return_value = [
            {
                "doc_type": "Sales Order",
                "name": "Sales Order-main-default_print_format",
                "value": "CD Sales Order Print",
            },
        ]

        patch_module.execute()

        frappe.get_all.assert_called_once_with(
            "Property Setter",
            filters={
                "property": "default_print_format",
                "value": ["in", tuple(patch_module.DEFAULT_PRINT_FORMAT_RENAMES)],
            },
            fields=["name", "doc_type", "value"],
        )
        frappe.db.set_value.assert_called_once_with(
            "Property Setter",
            "Sales Order-main-default_print_format",
            "value",
            "Sales Order",
            update_modified=False,
        )
        self.assertEqual(
            frappe.delete_doc.call_args_list,
            [
                call(
                    "Print Format",
                    "CD Purchase Order Print",
                    force=True,
                    ignore_missing=True,
                ),
                call(
                    "Print Format",
                    "CD Sales Invoice Print",
                    force=True,
                    ignore_missing=True,
                ),
            ],
        )
        self.assertEqual(
            frappe.clear_cache.call_args_list,
            [
                call(doctype="Sales Order"),
                call(),
            ],
        )
        frappe.db.commit.assert_called_once_with()
