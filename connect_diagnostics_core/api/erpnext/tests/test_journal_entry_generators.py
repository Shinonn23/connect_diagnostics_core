# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import journal_entry_generators as generators


class TestJournalEntryGenerators(UnitTestCase):
    def test_operation_identity_ignores_amount_but_binds_reference(self) -> None:
        rows = [
            frappe._dict(
                reference_type="Purchase Invoice",
                reference_name="PINV-1",
                reference_detail_no="ROW-1",
                debit_in_account_currency=100,
            )
        ]
        doc = frappe._dict(
            voucher_type="Deferred Expense",
            posting_date="2026-01-31",
            accounts=rows,
        )
        context = {
            "source_doctype": "Process Deferred Accounting",
            "source_name": "PDA-1",
            "source_action": "process_deferred_accounting",
        }
        context["operation_base_id"] = "PDA-1"
        generators.set_deferred_operation_key(doc, context)
        identity = generators._operation_id(doc, context)
        rows[0].debit_in_account_currency = 200
        generators.set_deferred_operation_key(doc, context)
        self.assertEqual(identity, generators._operation_id(doc, context))
        rows[0].reference_detail_no = "ROW-2"
        generators.set_deferred_operation_key(doc, context)
        self.assertNotEqual(identity, generators._operation_id(doc, context))

    def test_source_proof_is_bound_to_final_journal_entry_name(self) -> None:
        with (
            patch.object(generators, "get_encryption_key", return_value="secret"),
            patch.object(generators.frappe.local, "site", "local.test", create=True),
        ):
            first = generators._source_proof("Source", "SRC-1", "create", "op", "JE-1")
            copied = generators._source_proof("Source", "SRC-1", "create", "op", "JE-2")
        self.assertNotEqual(first, copied)

    def test_petty_cash_requires_operation_id(self) -> None:
        with patch.object(generators.frappe, "throw", side_effect=ValueError):
            with self.assertRaises(ValueError):
                generators.create_petty_cash_journal_entry(
                    "2026-01-01", "Holder", "From", "To", 1, "topup", ""
                )

    @patch.object(generators, "_find_existing_draft")
    def test_petty_cash_retry_returns_existing_draft(self, find_existing: MagicMock) -> None:
        find_existing.return_value = MagicMock(name="JE-1")
        holder = frappe._dict(
            disabled=0,
            cash_bank_account_for_petty_cash_top_up="From",
            petty_cash_account="To",
            cash_bank_account_for_petty_cash_withdraw="From",
        )
        accounts = [
            frappe._dict(name="From", company="Test", account_currency="THB", disabled=0, is_group=0),
            frappe._dict(name="To", company="Test", account_currency="THB", disabled=0, is_group=0),
        ]
        with (
            patch.object(generators.frappe, "get_doc", return_value=holder),
            patch.object(generators.frappe.db, "get_all", return_value=accounts),
        ):
            result = generators.create_petty_cash_journal_entry(
                "2026-01-01",
                "Holder",
                "From",
                "To",
                1,
                "topup",
                "12345678-1234-5678-1234-567812345678",
            )
        self.assertEqual(result, {"name": find_existing.return_value.name, "pending_approval": True})

    @patch.object(generators, "_find_existing_draft")
    def test_bank_reconciliation_retry_does_not_call_native_generator(self, find_existing: MagicMock) -> None:
        find_existing.return_value = MagicMock(name="JE-2")
        with (
            patch.object(generators.frappe.db, "exists", return_value=True),
            patch(
                "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool.create_journal_entry_bts"
            ) as native,
        ):
            result = generators.create_journal_entry_bts(bank_transaction_name="BT-1")
        native.assert_not_called()
        self.assertTrue(result["pending_approval"])
