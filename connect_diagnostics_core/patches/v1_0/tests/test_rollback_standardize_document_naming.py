# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import rollback_standardize_document_naming
from connect_diagnostics_core.setup import document_naming


class TestRollbackStandardizeDocumentNaming(UnitTestCase):
    @patch.object(rollback_standardize_document_naming.frappe.db, "commit")
    @patch.object(rollback_standardize_document_naming.frappe, "clear_cache")
    @patch.object(rollback_standardize_document_naming.frappe, "delete_doc")
    @patch.object(rollback_standardize_document_naming.frappe, "get_all")
    def test_execute_deletes_only_current_policy_setters(
        self,
        get_all,
        delete_doc,
        clear_cache,
        commit,
    ) -> None:
        setters = {
            "Sales Invoice": [
                ("naming_series", "default", "SI.YYYY-BE.MM-DATE.####", "Text"),
                (None, "autoname", "SI.YYYY-BE.MM-DATE.####", "Data"),
            ]
        }
        get_all.side_effect = [
            [
                SimpleNamespace(name="current-default", value="SI.YYYY-BE.MM-DATE.####"),
                SimpleNamespace(name="user-default", value="CUSTOM.####"),
            ],
            [SimpleNamespace(name="current-autoname", value="SI.YYYY-BE.MM-DATE.####")],
        ]

        with patch.object(document_naming, "PROPERTY_SETTERS", setters):
            rollback_standardize_document_naming.execute()

        self.assertEqual(
            get_all.call_args_list,
            [
                call(
                    "Property Setter",
                    filters={
                        "doc_type": "Sales Invoice",
                        "property": "default",
                        "field_name": "naming_series",
                    },
                    fields=["name", "value"],
                ),
                call(
                    "Property Setter",
                    filters={
                        "doc_type": "Sales Invoice",
                        "property": "autoname",
                        "field_name": ["is", "not set"],
                    },
                    fields=["name", "value"],
                ),
            ],
        )
        self.assertEqual(
            delete_doc.call_args_list,
            [
                call("Property Setter", "current-default", ignore_permissions=True, force=True),
                call("Property Setter", "current-autoname", ignore_permissions=True, force=True),
            ],
        )
        clear_cache.assert_called_once_with(doctype="Sales Invoice")
        commit.assert_called_once_with()
