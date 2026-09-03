# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import (
    add_quotation_print_signatures,
    rollback_add_quotation_print_signatures,
)


class TestAddQuotationPrintSignaturesPatch(UnitTestCase):
    @patch.object(add_quotation_print_signatures.frappe.db, "has_column", return_value=True)
    @patch.object(add_quotation_print_signatures.frappe.db, "sql")
    @patch.object(add_quotation_print_signatures.frappe.db, "commit")
    def test_forward_patch_falls_back_blank_signatory_types(
        self, mocked_commit: MagicMock, mocked_sql: MagicMock, _has_column: MagicMock
    ) -> None:
        add_quotation_print_signatures.execute()

        mocked_sql.assert_called_once()
        query, value = mocked_sql.call_args.args
        self.assertIn("where ifnull(quotation_signatory_type, '') = ''", query)
        self.assertEqual(value, "Sales Representative")
        mocked_commit.assert_called_once()

    @patch.object(add_quotation_print_signatures.frappe.db, "has_column", return_value=False)
    @patch.object(add_quotation_print_signatures.frappe.db, "sql")
    def test_forward_patch_is_a_noop_before_the_legacy_column_exists(
        self, mocked_sql: MagicMock, _has_column: MagicMock
    ) -> None:
        add_quotation_print_signatures.execute()

        mocked_sql.assert_not_called()

    def test_rollback_does_not_clear_values_that_may_have_been_edited(self) -> None:
        # The rollback intentionally has no database dependency; a backup is
        # required for a full reversal because forward-filled rows are not
        # distinguishable from later user edits.
        self.assertIsNone(rollback_add_quotation_print_signatures.execute())
