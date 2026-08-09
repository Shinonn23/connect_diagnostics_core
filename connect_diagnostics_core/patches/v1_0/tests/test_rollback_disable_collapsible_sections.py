from __future__ import annotations

from unittest.mock import call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import rollback_disable_collapsible_sections as rollback_module


class TestRollbackDisableCollapsibleSectionsPatch(UnitTestCase):
    @patch.object(rollback_module, "frappe")
    def test_execute_deletes_property_setters_and_clears_cache(self, frappe) -> None:
        frappe.get_all.return_value = [
            {"doc_type": "Sales Invoice", "field_name": "more_info"},
        ]
        frappe.db.exists.side_effect = [
            "Sales Invoice-more_info-collapsible",
            "Sales Invoice-more_info-collapsible_depends_on",
        ]

        rollback_module.execute()

        self.assertEqual(
            frappe.delete_doc.call_args_list,
            [
                call("Property Setter", "Sales Invoice-more_info-collapsible", force=True),
                call(
                    "Property Setter",
                    "Sales Invoice-more_info-collapsible_depends_on",
                    force=True,
                ),
            ],
        )
        frappe.clear_cache.assert_called_once_with(doctype="Sales Invoice")
