from __future__ import annotations

from unittest import TestCase
from unittest.mock import call, patch

from connect_diagnostics_core.patches.v1_0 import disable_collapsible_sections as patch_module


class TestDisableCollapsibleSectionsPatch(TestCase):
    @patch.object(patch_module, "make_property_setter")
    @patch.object(patch_module, "frappe")
    def test_execute_disables_standard_custom_and_property_setter_sections(
        self, frappe, make_property_setter
    ) -> None:
        frappe.get_all.side_effect = [
            [{"parent": "Sales Invoice", "fieldname": "more_info"}],
            [{"dt": "Employee", "fieldname": "health_insurance_section"}],
            [{"doc_type": "Sales Order", "field_name": "accounting_dimensions_section"}],
        ]
        frappe.db.exists.return_value = None

        patch_module.execute()

        frappe.db.set_value.assert_called_once_with(
            "Custom Field",
            {"dt": "Employee", "fieldname": "health_insurance_section"},
            {"collapsible": 0, "collapsible_depends_on": None},
            update_modified=False,
        )
        self.assertEqual(
            make_property_setter.call_args_list,
            [
                call(
                    "Sales Invoice",
                    "more_info",
                    "collapsible",
                    "0",
                    "Check",
                    validate_fields_for_doctype=False,
                ),
                call(
                    "Sales Invoice",
                    "more_info",
                    "collapsible_depends_on",
                    "",
                    "Data",
                    validate_fields_for_doctype=False,
                ),
                call(
                    "Sales Order",
                    "accounting_dimensions_section",
                    "collapsible",
                    "0",
                    "Check",
                    validate_fields_for_doctype=False,
                ),
                call(
                    "Sales Order",
                    "accounting_dimensions_section",
                    "collapsible_depends_on",
                    "",
                    "Data",
                    validate_fields_for_doctype=False,
                ),
            ],
        )
        self.assertEqual(
            frappe.clear_cache.call_args_list,
            [
                call(doctype="Employee"),
                call(doctype="Sales Invoice"),
                call(doctype="Sales Order"),
            ],
        )

    @patch.object(patch_module, "make_property_setter")
    @patch.object(patch_module, "frappe")
    def test_set_property_setter_updates_existing_setter(self, frappe, make_property_setter) -> None:
        frappe.db.exists.return_value = "Sales Invoice-more_info-collapsible"

        patch_module._set_property_setter("Sales Invoice", "more_info", "collapsible", "0", "Check")

        make_property_setter.assert_not_called()
        frappe.db.set_value.assert_called_once_with(
            "Property Setter",
            "Sales Invoice-more_info-collapsible",
            "value",
            "0",
            update_modified=False,
        )
