# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import Mock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import tds


class TestTDSSetup(UnitTestCase):
    def test_catalog_does_not_include_thai_vat_fields(self) -> None:
        all_fields = {field for fields in tds.TDS_FIELDS.values() for field in fields}
        self.assertNotIn("tax_category", all_fields)
        self.assertNotIn("tax_id", all_fields)
        self.assertNotIn("withholding_tax_type", all_fields)

    def test_property_setters_follow_installed_metadata(self) -> None:
        meta = Mock()
        meta.has_field.side_effect = lambda fieldname: fieldname != "tax_withholding_tab"

        with patch.object(tds.frappe, "get_meta", return_value=meta):
            setters = tds.get_property_setters()

        journal_setters = setters["Journal Entry"]
        self.assertIn(("apply_tds", "hidden", "1", "Check"), journal_setters)
        self.assertNotIn(("tax_withholding_tab", "hidden", "1", "Check"), journal_setters)

    def test_permission_fields_are_all_disabled(self) -> None:
        permission = Mock()
        permission.get.side_effect = lambda fieldname: 1 if fieldname == "read" else 0
        permission.is_new.return_value = False

        with patch.object(tds.frappe, "get_doc", return_value=permission):
            tds._zero_permission("Custom DocPerm-1")

        permission.set.assert_called_once_with("read", 0)
        permission.save.assert_called_once_with(ignore_permissions=True)
