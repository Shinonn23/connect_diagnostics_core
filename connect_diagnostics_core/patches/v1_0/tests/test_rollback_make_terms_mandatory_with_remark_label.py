from __future__ import annotations

from unittest import TestCase
from unittest.mock import call, patch

from connect_diagnostics_core.patches.v1_0 import rollback_make_terms_mandatory_with_remark_label as rollback_module


class TestRollbackMakeTermsMandatoryWithRemarkLabelPatch(TestCase):
    @patch.object(rollback_module, "frappe")
    def test_execute_deletes_property_setters_and_clears_cache(self, frappe) -> None:
        frappe.db.exists.side_effect = lambda _doctype, filters: f"{filters['doc_type']}-terms-{filters['property']}"

        rollback_module.execute()

        expected_delete_calls = []
        expected_clear_cache_calls = []
        for doctype in rollback_module.TERMS_DOCTYPES:
            expected_delete_calls.extend(
                [
                    call("Property Setter", f"{doctype}-terms-reqd", force=True),
                    call("Property Setter", f"{doctype}-terms-label", force=True),
                ]
            )
            expected_clear_cache_calls.append(call(doctype=doctype))

        self.assertEqual(frappe.delete_doc.call_args_list, expected_delete_calls)
        self.assertEqual(frappe.clear_cache.call_args_list, expected_clear_cache_calls)
