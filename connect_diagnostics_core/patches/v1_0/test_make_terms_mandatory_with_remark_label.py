from __future__ import annotations

from unittest import TestCase
from unittest.mock import call, patch

from connect_diagnostics_core.patches.v1_0 import make_terms_mandatory_with_remark_label as patch_module


class TestMakeTermsMandatoryWithRemarkLabelPatch(TestCase):
    @patch.object(patch_module, "make_property_setter")
    @patch.object(patch_module, "frappe")
    def test_execute_creates_missing_property_setters(self, frappe, make_property_setter) -> None:
        frappe.db.exists.return_value = None

        patch_module.execute()

        expected_property_setter_calls = []
        for doctype in patch_module.TERMS_DOCTYPES:
            expected_property_setter_calls.extend(
                [
                    call(
                        doctype,
                        "terms",
                        "reqd",
                        "1",
                        "Check",
                        validate_fields_for_doctype=False,
                    ),
                    call(
                        doctype,
                        "terms",
                        "label",
                        "Terms and Conditions Content (Remark)",
                        "Data",
                        validate_fields_for_doctype=False,
                    ),
                ]
            )

        self.assertEqual(make_property_setter.call_args_list, expected_property_setter_calls)
        self.assertEqual(
            frappe.clear_cache.call_args_list,
            [call(doctype=doctype) for doctype in patch_module.TERMS_DOCTYPES],
        )

    @patch.object(patch_module, "make_property_setter")
    @patch.object(patch_module, "frappe")
    def test_set_property_setter_updates_existing_setter(self, frappe, make_property_setter) -> None:
        frappe.db.exists.return_value = "Sales Order-terms-reqd"

        patch_module._set_property_setter("Sales Order", "terms", "reqd", "1", "Check")

        make_property_setter.assert_not_called()
        frappe.db.set_value.assert_called_once_with(
            "Property Setter",
            "Sales Order-terms-reqd",
            "value",
            "1",
            update_modified=False,
        )

    @patch.object(patch_module, "make_property_setter")
    @patch.object(patch_module, "frappe")
    def test_set_property_setter_creates_missing_setter(self, frappe, make_property_setter) -> None:
        frappe.db.exists.return_value = None

        patch_module._set_property_setter(
            "Sales Order",
            "terms",
            "label",
            "Terms and Conditions Content (Remark)",
            "Data",
        )

        frappe.db.set_value.assert_not_called()
        make_property_setter.assert_called_once_with(
            "Sales Order",
            "terms",
            "label",
            "Terms and Conditions Content (Remark)",
            "Data",
            validate_fields_for_doctype=False,
        )
