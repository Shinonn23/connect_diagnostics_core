# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import backfill_broken_autoname_documents as patch_module


class TestBackfillBrokenAutonameDocumentsPatch(UnitTestCase):
    @patch.object(patch_module, "frappe")
    def test_execute_renames_documents_with_the_literal_broken_tokens(self, frappe) -> None:
        frappe.db.exists.side_effect = lambda doctype, name=None: doctype == "DocType"
        frappe.get_all.return_value = ["SHP{YY-BE}{MM-DOC}0001"]
        frappe.get_doc.return_value = SimpleNamespace(
            get=lambda field: {"creation": "2026-08-18 12:36:42.345779"}.get(field)
        )

        patch_module.execute()

        frappe.rename_doc.assert_called_once_with(
            "Shipment", "SHP{YY-BE}{MM-DOC}0001", "SHP69080001", force=True
        )
        frappe.db.commit.assert_called_once()

    @patch.object(patch_module, "frappe")
    def test_execute_skips_doctypes_not_installed(self, frappe) -> None:
        frappe.db.exists.return_value = False

        patch_module.execute()

        frappe.get_all.assert_not_called()
        frappe.rename_doc.assert_not_called()

    @patch.object(patch_module, "frappe")
    def test_rename_broken_document_ignores_a_name_that_does_not_match_the_pattern(self, frappe) -> None:
        renamed = patch_module._rename_broken_document("Shipment", "SHP", "SHP69080001")

        self.assertFalse(renamed)
        frappe.get_doc.assert_not_called()
        frappe.rename_doc.assert_not_called()

    @patch.object(patch_module, "frappe")
    def test_rename_broken_document_skips_when_target_name_already_exists(self, frappe) -> None:
        frappe.get_doc.return_value = SimpleNamespace(
            get=lambda field: {"creation": "2026-08-18 12:36:42.345779"}.get(field)
        )
        frappe.db.exists.return_value = True

        renamed = patch_module._rename_broken_document("Shipment", "SHP", "SHP{YY-BE}{MM-DOC}0001")

        self.assertFalse(renamed)
        frappe.rename_doc.assert_not_called()
