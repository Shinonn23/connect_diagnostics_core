# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from decimal import Decimal
from typing import cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.hrms import payroll_entry_workflow as workflow
from connect_diagnostics_core.api.hrms import payroll_output_review as output


class TestPayrollOutputReview(UnitTestCase):
    def test_payroll_settings_native_reader_must_equal_locked_singles_projection(self) -> None:
        settings_doc = Document(
            {"doctype": "Payroll Settings", "name": "Payroll Settings", "employee_wise": 1}
        )
        fields = [frappe._dict(fieldname="employee_wise", fieldtype="Check", default=0)]
        with (
            patch.object(output.frappe, "clear_document_cache"),
            patch.object(output.frappe.db, "value_cache", {}),
            patch.object(output.frappe, "get_cached_doc", return_value=settings_doc),
            patch.object(output.frappe, "get_meta", return_value=frappe._dict(fields=fields)),
            patch.object(
                workflow,
                "_locked_payroll_settings",
                return_value=[frappe._dict(field="employee_wise", value="1")],
            ),
        ):
            workflow._verify_native_payroll_settings(
                output.critical_digest({"settings": [{"field": "employee_wise", "value": "1"}]})
            )

        settings_doc.set("employee_wise", 0)
        with (
            patch.object(output.frappe, "clear_document_cache"),
            patch.object(output.frappe.db, "value_cache", {}),
            patch.object(output.frappe, "get_cached_doc", return_value=settings_doc),
            patch.object(output.frappe, "get_meta", return_value=frappe._dict(fields=fields)),
            patch.object(
                workflow,
                "_locked_payroll_settings",
                return_value=[frappe._dict(field="employee_wise", value="1")],
            ),
            self.assertRaisesRegex(
                frappe.ValidationError, "Payroll Settings changed in the active transaction"
            ),
        ):
            workflow._verify_native_payroll_settings(
                output.critical_digest({"settings": [{"field": "employee_wise", "value": "1"}]})
            )

    def _payroll(self, **values: object) -> Document:
        return Document(
            {
                "doctype": "Payroll Entry",
                "name": "PE-OUTPUT-1",
                "docstatus": 1,
                "workflow_state": output.REVIEWED,
                "company": "ACME",
                "salary_slips_created": 1,
                "status": "Submitted",
                "error_message": "",
                **values,
            }
        )

    def test_review_signature_binds_actor_revision_and_batch(self) -> None:
        pe = self._payroll()
        with (
            patch.object(output, "output_payload", return_value={"amount": "100.00"}) as payload,
            patch.object(output, "get_encryption_key", return_value="local-test-key"),
            patch.object(output, "locked_payroll_entry", return_value=pe),
            patch.object(output, "current_roster", return_value=[]),
        ):
            output.seal_output_review(pe, [], "reviewer@example.com")
            self.assertEqual(output.require_output_review(pe, []), [])
            payload.return_value = {"amount": "100.01"}
            with self.assertRaises(frappe.PermissionError):
                output.require_output_review(pe, [])
            payload.return_value = {"amount": "100.00"}
            pe.set("output_review_revision", 2)
            with self.assertRaises(frappe.PermissionError):
                output.require_output_review(pe, [])

    def test_unknown_or_legacy_review_version_never_authorizes_posting(self) -> None:
        for version in (None, "", "unexpected"):
            with self.subTest(version=version):
                pe = self._payroll(output_review_version=version)
                with (
                    patch.object(output, "locked_payroll_entry", return_value=pe),
                    self.assertRaises(frappe.PermissionError),
                ):
                    output.require_output_review(pe, [])

    def test_lending_installed_fails_closed_before_output_seal_projection(self) -> None:
        pe = self._payroll()
        with (
            patch.object(output.frappe, "get_installed_apps", return_value=["frappe", "hrms", "lending"]),
            patch.object(output, "_dimensions") as dimensions,
            self.assertRaisesRegex(frappe.PermissionError, "versioned Lending contract"),
        ):
            output.output_payload(pe, [])
        dimensions.assert_not_called()

    def test_roster_rejects_duplicate_missing_and_foreign_slips(self) -> None:
        pe = self._payroll(
            start_date="2026-10-01",
            end_date="2026-10-31",
            posting_date="2026-10-31",
            payroll_frequency="Monthly",
            currency="THB",
            salary_slip_based_on_timesheet=0,
        )
        employees = [
            frappe._dict(name="R1", idx=1, employee="E1"),
            frappe._dict(name="R2", idx=2, employee="E2"),
        ]
        slips = [
            frappe._dict(
                name="S1",
                employee="E1",
                docstatus=0,
                company="ACME",
                start_date="2026-10-01",
                end_date="2026-10-31",
                posting_date="2026-10-31",
                payroll_frequency="Monthly",
                currency="THB",
                salary_slip_based_on_timesheet=0,
            )
        ]
        with (
            patch.object(output, "locked_payroll_entry", return_value=pe),
            patch.object(output, "_locked_rows", side_effect=[employees, slips]),
        ):
            with self.assertRaisesRegex(frappe.PermissionError, "roster"):
                output.current_roster(pe)
        with (
            patch.object(output, "locked_payroll_entry", return_value=pe),
            patch.object(output, "_locked_rows", side_effect=[[employees[0], employees[0]], slips]),
        ):
            with self.assertRaisesRegex(frappe.PermissionError, "duplicated"):
                output.current_roster(pe)
        slips.append(frappe._dict({**slips[0], "name": "S2", "employee": "E2", "company": "OTHER"}))
        with (
            patch.object(output, "locked_payroll_entry", return_value=pe),
            patch.object(output, "_locked_rows", side_effect=[employees, slips, []]),
        ):
            with self.assertRaisesRegex(frappe.PermissionError, "identity or period"):
                output.current_roster(pe)

    def test_review_refuses_queued_retry_even_with_prior_created_flag(self) -> None:
        pe = self._payroll(status="Queued", salary_slips_created=1)
        employees = [frappe._dict(name="R1", idx=1, employee="E1")]
        slips = [frappe._dict(name="S1", employee="E1")]
        with (
            patch.object(output, "locked_payroll_entry", return_value=pe),
            patch.object(output, "_locked_rows", side_effect=[employees, slips]),
        ):
            with self.assertRaisesRegex(frappe.PermissionError, "not completed"):
                output.current_roster(pe)

    def test_payroll_entry_current_full_document_is_loaded_under_existing_mutex(self) -> None:
        current = self._payroll(
            status="Queued",
            output_review_version=output.VERSION,
            output_review_digest="current-digest",
            payment_account="CURRENT-BANK",
        )
        identity = frappe._dict(name=current.name, docstatus=1, workflow_state=output.REVIEWED)
        with (
            patch.object(output.frappe.db, "get_value", return_value=identity) as lock,
            patch.object(output.frappe, "get_doc", return_value=current) as full_load,
        ):
            fresh = output.locked_payroll_entry(str(current.name))

        self.assertEqual(fresh.get("status"), "Queued")
        self.assertEqual(fresh.get("payment_account"), "CURRENT-BANK")
        self.assertEqual(fresh.get("output_review_digest"), "current-digest")
        self.assertTrue(lock.call_args.kwargs["for_update"])
        full_load.assert_called_once_with("Payroll Entry", current.name, for_update=True)

    def test_current_roster_uses_full_slip_current_read_after_parent_and_roster_locks(self) -> None:
        stale = self._payroll(status="Failed", salary_slips_created=0)
        current = self._payroll(
            status="Submitted",
            salary_slips_created=1,
            start_date="2026-10-01",
            end_date="2026-10-31",
            posting_date="2026-10-31",
            payroll_frequency="Monthly",
            currency="THB",
            salary_slip_based_on_timesheet=0,
        )
        employees = [frappe._dict(name="ROSTER-1", idx=1, employee="E1")]
        slip_identity = frappe._dict(
            name="SS-CURRENT",
            employee="E1",
            docstatus=1,
            company="ACME",
            start_date="2026-10-01",
            end_date="2026-10-31",
            posting_date="2026-10-31",
            payroll_frequency="Monthly",
            currency="THB",
            salary_slip_based_on_timesheet=0,
        )
        fresh_slip = cast(
            Document,
            frappe._dict(
                doctype="Salary Slip",
                name="SS-CURRENT",
                employee="E1",
                docstatus=1,
                status="Submitted",
                net_pay=275,
                earnings=[frappe._dict(amount=275)],
                deductions=[],
            ),
        )
        with (
            patch.object(output, "locked_payroll_entry", return_value=current),
            patch.object(output, "_locked_rows", side_effect=[employees, [slip_identity], []]),
            patch.object(output, "_active_job", return_value=False),
            patch.object(output.frappe, "get_doc", return_value=fresh_slip) as full_load,
        ):
            active = output.current_roster(stale)

        self.assertEqual(active[0].get("net_pay"), 275)
        earnings = cast(list[frappe._dict], active[0].get("earnings"))
        self.assertEqual(earnings[0].amount, 275)
        full_load.assert_called_once_with("Salary Slip", "SS-CURRENT", for_update=True)

    def test_active_journal_account_projection_uses_full_current_locked_document(self) -> None:
        pe = self._payroll()
        slips = [cast(Document, frappe._dict(name="SS-1", journal_entry="JE-CURRENT"))]
        active_je = cast(
            Document,
            frappe._dict(
                doctype="Journal Entry",
                name="JE-CURRENT",
                docstatus=1,
                company="ACME",
                accounts=[
                    frappe._dict(account="CURRENT-WAGES", cost_center="MAIN", debit=100, credit=0),
                    frappe._dict(account="PAYABLE", cost_center="MAIN", debit=0, credit=100),
                ],
            ),
        )
        header = frappe._dict(name="JE-CURRENT", docstatus=1)
        with (
            patch.object(
                output,
                "_locked_rows",
                return_value=[frappe._dict(name="JEA-1", parent="JE-CURRENT")],
            ) as identity_lock,
            patch.object(output.frappe.db, "get_value", return_value=header) as header_lock,
            patch.object(output.frappe, "get_doc", return_value=active_je) as full_load,
            patch.object(output.frappe, "get_precision", return_value=2),
        ):
            journals = output._active_journals(pe, slips)
            projection = output._candidate_accrual_components(journals["JE-CURRENT"], "PAYABLE")

        self.assertEqual(
            projection,
            {("CURRENT-WAGES", "MAIN", "earnings", "", ""): Decimal("100.00")},
        )
        self.assertEqual(identity_lock.call_args.args[0], "Journal Entry Account")
        self.assertTrue(header_lock.call_args.kwargs["for_update"])
        full_load.assert_called_once_with("Journal Entry", "JE-CURRENT", for_update=True)

    def test_native_operation_scope_cannot_be_reused_for_other_payroll_or_after_exit(self) -> None:
        with self.assertRaises(frappe.PermissionError):
            output.require_native_operation("PE-OUTPUT-1", "submit")
        with output.native_operation("PE-OUTPUT-1", "submit"):
            output.require_native_operation("PE-OUTPUT-1", "submit")
            with self.assertRaises(frappe.PermissionError):
                output.require_native_operation("PE-OUTPUT-2", "submit")
        with self.assertRaises(frappe.PermissionError):
            output.require_native_operation("PE-OUTPUT-1", "submit")

    def test_native_component_inclusion_matches_regular_payment_rule(self) -> None:
        slip = frappe._dict(
            earnings=[
                frappe._dict(
                    amount=100,
                    do_not_include_in_total=0,
                    do_not_include_in_accounts=0,
                    statistical_component=0,
                ),
                frappe._dict(
                    amount=50,
                    do_not_include_in_total=1,
                    do_not_include_in_accounts=0,
                    statistical_component=0,
                ),
                frappe._dict(
                    amount=999,
                    do_not_include_in_total=0,
                    do_not_include_in_accounts=0,
                    statistical_component=1,
                ),
            ],
            deductions=[
                frappe._dict(
                    amount=20,
                    do_not_include_in_total=0,
                    do_not_include_in_accounts=0,
                    statistical_component=0,
                ),
                frappe._dict(
                    amount=9, do_not_include_in_total=1, do_not_include_in_accounts=1, statistical_component=0
                ),
            ],
        )
        self.assertEqual(output._slip_obligation(cast(Document, slip)), Decimal(130))

    def test_native_component_inclusion_covers_every_hrms_flag_pair(self) -> None:
        rows = [
            frappe._dict(
                amount=amount,
                do_not_include_in_total=skip_total,
                do_not_include_in_accounts=skip_accounts,
                statistical_component=0,
            )
            for amount, skip_total, skip_accounts in (
                (1, 0, 0),
                (2, 0, 1),
                (4, 1, 0),
                (8, 1, 1),
            )
        ]
        slip = cast(Document, frappe._dict(earnings=rows, deductions=[]))
        self.assertEqual(output._slip_obligation(slip), Decimal(7))

    def test_bank_obligation_separately_excludes_statistical_component(self) -> None:
        pe = self._payroll(exchange_rate=1, payroll_payable_account="PAYABLE")
        slip = cast(
            Document,
            frappe._dict(
                employee="E1",
                earnings=[
                    frappe._dict(
                        amount=100,
                        do_not_include_in_total=0,
                        do_not_include_in_accounts=0,
                        statistical_component=0,
                    ),
                    frappe._dict(
                        amount=50,
                        do_not_include_in_total=0,
                        do_not_include_in_accounts=0,
                        statistical_component=1,
                    ),
                ],
                deductions=[],
            ),
        )
        with patch.object(output.frappe, "get_precision", return_value=2):
            self.assertEqual(
                output._native_bank_projection(
                    pe,
                    [slip],
                    {
                        "employee_wise_accounting": 0,
                        "company_currency": "THB",
                        "accounts": [{"name": "PAYABLE", "account_currency": "THB"}],
                    },
                ),
                {"": Decimal("100.00")},
            )

    def test_close_requires_accrual_when_zero_net_has_nonzero_components(self) -> None:
        pe = self._payroll(payroll_payable_account="PAYABLE")
        slip = cast(
            Document,
            frappe._dict(
                name="SS-1",
                employee="E1",
                docstatus=1,
                status="Submitted",
                net_pay=0,
                journal_entry=None,
                earnings=[frappe._dict(amount=100)],
                deductions=[frappe._dict(amount=100)],
            ),
        )
        components = {
            ("WAGES", "MAIN", "earnings", "", ""): Decimal("100.00"),
            ("TAX", "MAIN", "deductions", "", ""): Decimal("100.00"),
        }
        with (
            patch.object(output, "locked_payroll_entry", return_value=pe),
            patch.object(output, "require_output_review", return_value=[slip]),
            patch.object(output, "_active_journals", return_value={}),
            patch.object(output, "output_payload", return_value={"sources": {"components": []}}),
            patch.object(output, "_native_accrual_component_projection", return_value=components),
            self.assertRaisesRegex(frappe.PermissionError, "no native accrual Journal Entry"),
        ):
            output.require_complete_accounting(pe)

    def test_zero_net_close_accepts_exact_native_accrual_and_rejects_mismatches(self) -> None:
        pe = self._payroll(payroll_payable_account="PAYABLE")
        slip = cast(
            Document,
            frappe._dict(
                name="SS-ZERO",
                employee="E1",
                docstatus=1,
                status="Submitted",
                net_pay=0,
                journal_entry="ACCRUAL-ZERO",
                earnings=[frappe._dict(salary_component="Basic", amount=100)],
                deductions=[frappe._dict(salary_component="Tax", amount=100)],
            ),
        )
        accrual = Document(
            {
                "doctype": "Journal Entry",
                "name": "ACCRUAL-ZERO",
                "docstatus": 1,
                "company": "ACME",
                "voucher_type": "Journal Entry",
                "accounts": [
                    frappe._dict(account="WAGES", cost_center="MAIN", debit=100, credit=0),
                    frappe._dict(account="TAX", cost_center="MAIN", debit=0, credit=100),
                    frappe._dict(
                        account="PAYABLE",
                        reference_type="Payroll Entry",
                        reference_name=pe.name,
                        debit=0,
                        credit=0,
                    ),
                ],
            }
        )
        gl_rows = [
            frappe._dict(
                account="WAGES", cost_center="MAIN", party_type=None, party=None, debit=100, credit=0
            ),
            frappe._dict(account="TAX", cost_center="MAIN", party_type=None, party=None, debit=0, credit=100),
            frappe._dict(
                account="PAYABLE", cost_center="MAIN", party_type=None, party=None, debit=0, credit=0
            ),
        ]
        sources = {
            "components": [
                {"name": "Basic", "account": "WAGES"},
                {"name": "Tax", "account": "TAX"},
            ],
            "assignments": [{"employee": "E1", "cost_centers": [], "employee_cost_center": "MAIN"}],
            "additional_salaries": [],
            "accounts": [
                {"name": "WAGES", "account_currency": "THB"},
                {"name": "TAX", "account_currency": "THB"},
                {"name": "PAYABLE", "account_currency": "THB"},
            ],
            "company_currency": "THB",
            "employee_wise_accounting": 0,
        }

        def close_with(candidate: Document, gl: list[frappe._dict]) -> None:
            with (
                patch.object(output, "locked_payroll_entry", return_value=pe),
                patch.object(output, "require_output_review", return_value=[slip]),
                patch.object(output, "_active_journals", return_value={candidate.name: candidate}),
                patch.object(output, "output_payload", return_value={"sources": sources}),
                patch.object(output, "_locked_rows", return_value=gl),
                patch.object(output.frappe, "get_precision", return_value=2),
            ):
                output.require_complete_accounting(pe)

        close_with(accrual, gl_rows)

        wrong_account = frappe.get_doc(accrual.as_dict())
        wrong_account.accounts[0].account = "OTHER"
        wrong_amount = frappe.get_doc(accrual.as_dict())
        wrong_amount.accounts[0].debit = 99
        wrong_reference = frappe.get_doc(accrual.as_dict())
        wrong_reference.accounts[2].reference_name = "PE-OTHER"
        for label, candidate in (
            ("account", wrong_account),
            ("amount", wrong_amount),
            ("reference", wrong_reference),
        ):
            with self.subTest(mismatch=label), self.assertRaises(frappe.PermissionError):
                close_with(candidate, gl_rows)

    def test_accrual_projection_uses_native_cost_center_rounding_and_currency(self) -> None:
        pe = self._payroll(exchange_rate=1.5, cost_center="MAIN")
        slip = frappe._dict(
            employee="E1",
            earnings=[
                frappe._dict(
                    salary_component="Basic",
                    amount=100.01,
                    do_not_include_in_total=0,
                    do_not_include_in_accounts=0,
                    additional_salary=None,
                )
            ],
            deductions=[],
        )
        sources = {
            "components": [{"name": "Basic", "account": "WAGES"}],
            "assignments": [
                {
                    "employee": "E1",
                    "cost_centers": [
                        {"cost_center": "A", "percentage": 33.33},
                        {"cost_center": "B", "percentage": 33.33},
                        {"cost_center": "C", "percentage": 33.34},
                    ],
                }
            ],
            "additional_salaries": [],
            "employee_wise_accounting": 0,
        }
        with patch.object(output.frappe, "get_precision", return_value=2):
            self.assertEqual(
                output._native_accrual_projection(pe, [cast(Document, slip)], sources),
                {"": Decimal("150.00")},
            )

    def test_accrual_projection_matches_every_native_hrms_inclusion_flag_pair(self) -> None:
        pe = self._payroll(exchange_rate=1, cost_center="MAIN")
        flag_rows = [
            frappe._dict(
                salary_component=name,
                amount=amount,
                do_not_include_in_total=skip_total,
                do_not_include_in_accounts=skip_accounts,
            )
            for name, amount, skip_total, skip_accounts in (
                ("A", 1, 0, 0),
                ("B", 2, 0, 1),
                ("C", 4, 1, 0),
                ("D", 8, 1, 1),
            )
        ]
        slip = cast(Document, frappe._dict(employee="E1", earnings=flag_rows, deductions=[]))
        sources = {
            "components": [{"name": name, "account": f"{name}-EXP"} for name in "ABCD"],
            "assignments": [{"employee": "E1", "cost_centers": [], "employee_cost_center": "MAIN"}],
            "additional_salaries": [],
            "accounts": [{"name": f"{name}-EXP", "account_currency": "THB"} for name in "ABCD"],
            "company_currency": "THB",
            "employee_wise_accounting": 0,
        }
        with patch.object(output.frappe, "get_precision", return_value=2):
            self.assertEqual(
                output._native_accrual_component_projection(pe, [slip], sources),
                {
                    ("A-EXP", "MAIN", "earnings", "", ""): Decimal("1.00"),
                    ("B-EXP", "MAIN", "earnings", "", ""): Decimal("2.00"),
                    ("C-EXP", "MAIN", "earnings", "", ""): Decimal("4.00"),
                },
            )

    def test_close_refuses_partial_native_roster_even_when_pe_flag_says_submitted(self) -> None:
        pe = self._payroll(salary_slips_submitted=1)
        incomplete = frappe._dict(docstatus=0, status="Draft", net_pay=100)
        with (
            patch.object(output, "locked_payroll_entry", return_value=pe),
            patch.object(output, "require_output_review", return_value=[incomplete]),
        ):
            with self.assertRaisesRegex(frappe.PermissionError, "Every reviewed Salary Slip"):
                output.require_complete_accounting(pe)

    def test_bank_projection_matches_native_employee_cost_center_rounding(self) -> None:
        pe = self._payroll(exchange_rate=1.5, payment_account="BANK")
        slip = frappe._dict(
            employee="E1",
            earnings=[frappe._dict(amount=100.01, statistical_component=0)],
            deductions=[],
        )
        source = {
            "employee_wise_accounting": 1,
            "company_currency": "THB",
            "accounts": [{"name": "BANK", "account_currency": "THB"}],
            "assignments": [
                {
                    "employee": "E1",
                    "cost_centers": [
                        {"cost_center": "A", "percentage": 33.33},
                        {"cost_center": "B", "percentage": 33.33},
                        {"cost_center": "C", "percentage": 33.34},
                    ],
                }
            ],
        }
        with patch.object(output.frappe, "get_precision", return_value=2):
            self.assertEqual(
                output._native_bank_projection(pe, [cast(Document, slip)], source),
                {"E1": Decimal("150.02")},
            )

    def test_accrual_component_projection_rejects_swapped_approved_accounts(self) -> None:
        pe = self._payroll(exchange_rate=1, cost_center="MAIN")
        slip = frappe._dict(
            employee="E1",
            earnings=[frappe._dict(salary_component="Basic", amount=100)],
            deductions=[frappe._dict(salary_component="Tax", amount=20)],
        )
        source = {
            "components": [
                {"name": "Basic", "account": "WAGES"},
                {"name": "Tax", "account": "TAX"},
            ],
            "assignments": [{"employee": "E1", "cost_centers": [], "employee_cost_center": "MAIN"}],
            "additional_salaries": [],
            "accounts": [
                {"name": "WAGES", "account_currency": "THB"},
                {"name": "TAX", "account_currency": "THB"},
            ],
            "company_currency": "THB",
        }
        je = Document({"doctype": "Journal Entry"})
        je.set(
            "accounts",
            [
                frappe._dict(account="TAX", cost_center="MAIN", debit=100, credit=0),
                frappe._dict(account="WAGES", cost_center="MAIN", debit=0, credit=20),
            ],
        )
        with patch.object(output.frappe, "get_precision", return_value=2):
            self.assertNotEqual(
                output._candidate_accrual_components(je, "PAYABLE"),
                output._native_accrual_component_projection(pe, [cast(Document, slip)], source),
            )

    def test_bank_projection_rounds_aggregated_multi_currency_slips_once(self) -> None:
        pe = self._payroll(exchange_rate=1.5, payroll_payable_account="PAYABLE")
        slips = [
            cast(
                Document, frappe._dict(employee=employee, earnings=[frappe._dict(amount=0.01)], deductions=[])
            )
            for employee in ("E1", "E2")
        ]
        source = {
            "employee_wise_accounting": 0,
            "company_currency": "THB",
            "accounts": [{"name": "PAYABLE", "account_currency": "THB"}],
        }
        with patch.object(output.frappe, "get_precision", return_value=2):
            self.assertEqual(output._native_bank_projection(pe, slips, source), {"": Decimal("0.03")})

    def test_close_rejects_submitted_accrual_changed_after_native_candidate(self) -> None:
        je = Document({"doctype": "Journal Entry", "name": "JE-4", "company": "ACME"})
        je.set(
            "accounts",
            [
                frappe._dict(account="OTHER", cost_center="MAIN", debit=100, credit=0),
                frappe._dict(
                    account="PAYABLE",
                    reference_type="Payroll Entry",
                    reference_name="PE-OUTPUT-1",
                    debit=0,
                    credit=100,
                ),
            ],
        )
        gl_rows = [
            frappe._dict(
                account="OTHER", cost_center="MAIN", party_type=None, party=None, debit=100, credit=0
            ),
            frappe._dict(
                account="PAYABLE", cost_center="MAIN", party_type=None, party=None, debit=0, credit=100
            ),
        ]
        expected = {("WAGES", "MAIN", "earnings", "", ""): Decimal(100)}
        with (
            patch.object(output, "_locked_rows", return_value=gl_rows),
            patch.object(output.frappe, "get_precision", return_value=2),
            self.assertRaisesRegex(frappe.PermissionError, "Submitted accrual component allocation"),
        ):
            output._gl_effects(je, "PAYABLE", "PE-OUTPUT-1", expected_components=expected)

    def test_close_reconciles_released_withholding_outside_regular_payment(self) -> None:
        pe = self._payroll(payroll_payable_account="PAYABLE", payment_account="BANK")
        slip = cast(
            Document,
            frappe._dict(
                employee="E1",
                docstatus=1,
                status="Submitted",
                net_pay=100,
                journal_entry="ACCRUAL",
                salary_withholding_cycle="CYCLE",
                earnings=[frappe._dict(amount=100)],
                deductions=[],
            ),
        )
        accrual = Document(
            {
                "doctype": "Journal Entry",
                "name": "ACCRUAL",
                "docstatus": 1,
                "company": "ACME",
                "voucher_type": "Journal Entry",
            }
        )
        release = Document(
            {
                "doctype": "Journal Entry",
                "name": "RELEASE",
                "docstatus": 1,
                "company": "ACME",
                "voucher_type": "Bank Entry",
            }
        )
        with (
            patch.object(output, "locked_payroll_entry", return_value=pe),
            patch.object(output, "require_output_review", return_value=[slip]),
            patch.object(output, "_active_journals", return_value={"ACCRUAL": accrual, "RELEASE": release}),
            patch.object(output, "output_payload", return_value={"sources": {"employee_wise_accounting": 0}}),
            patch.object(output, "_native_accrual_component_projection", return_value={}),
            patch.object(
                output,
                "_native_bank_projection",
                side_effect=lambda _pe, selected, _source: {"": Decimal(100) if selected else Decimal(0)},
            ),
            patch.object(
                output,
                "_gl_effects",
                side_effect=[
                    ({"": Decimal(100)}, Decimal(0)),
                    ({"": Decimal(-100)}, Decimal(100)),
                    ({"": Decimal(-100)}, Decimal(100)),
                ],
            ),
            patch.object(output.frappe.db, "get_value", return_value=frappe._dict(journal_entry="RELEASE")),
            patch.object(output.frappe, "get_precision", return_value=2),
        ):
            output.require_complete_accounting(pe)

    def test_close_rejects_cancelled_withholding_release(self) -> None:
        pe = self._payroll(payroll_payable_account="PAYABLE")
        slip = cast(
            Document,
            frappe._dict(
                employee="E1",
                docstatus=1,
                status="Submitted",
                net_pay=100,
                journal_entry="ACCRUAL",
                salary_withholding_cycle="CYCLE",
                earnings=[frappe._dict(amount=100)],
                deductions=[],
            ),
        )
        accrual = Document(
            {
                "doctype": "Journal Entry",
                "name": "ACCRUAL",
                "docstatus": 1,
                "company": "ACME",
                "voucher_type": "Journal Entry",
            }
        )
        release = Document(
            {
                "doctype": "Journal Entry",
                "name": "RELEASE",
                "docstatus": 2,
                "company": "ACME",
                "voucher_type": "Bank Entry",
            }
        )
        with (
            patch.object(output, "locked_payroll_entry", return_value=pe),
            patch.object(output, "require_output_review", return_value=[slip]),
            patch.object(output, "_active_journals", return_value={"ACCRUAL": accrual, "RELEASE": release}),
            patch.object(output, "output_payload", return_value={"sources": {"employee_wise_accounting": 0}}),
            patch.object(output, "_native_accrual_component_projection", return_value={}),
            patch.object(output, "_gl_effects", return_value=({"": Decimal(100)}, Decimal(0))),
            patch.object(output.frappe.db, "get_value", return_value=frappe._dict(journal_entry="RELEASE")),
            self.assertRaisesRegex(frappe.PermissionError, "lacks a submitted withholding"),
        ):
            output.require_complete_accounting(pe)

    def test_close_rejects_mismatched_payment_ledger_party_or_amount(self) -> None:
        je = Document({"doctype": "Journal Entry", "name": "JE-1", "company": "ACME"})
        je.set(
            "accounts",
            [
                frappe._dict(
                    account="PAYABLE",
                    reference_type="Payroll Entry",
                    reference_name="PE-OUTPUT-1",
                    party_type="Employee",
                    party="E1",
                    debit=0,
                    credit=100,
                ),
                frappe._dict(account="WAGES", debit=100, credit=0),
            ],
        )
        gl_rows = [
            frappe._dict(account="PAYABLE", party_type="Employee", party="E1", debit=0, credit=100),
            frappe._dict(account="WAGES", debit=100, credit=0),
        ]
        wrong_ledger = [
            frappe._dict(
                company="ACME",
                account_type="Payable",
                account="PAYABLE",
                party_type="Employee",
                party="E2",
                amount=100,
            )
        ]
        with (
            patch.object(output, "_locked_rows", side_effect=[gl_rows, wrong_ledger]),
            patch.object(output.frappe, "get_precision", return_value=2),
            self.assertRaisesRegex(frappe.PermissionError, "Payment Ledger amount"),
        ):
            output._gl_effects(je, "PAYABLE", "PE-OUTPUT-1")

    def test_close_requires_submitted_payment_ledger_rows(self) -> None:
        je = Document({"doctype": "Journal Entry", "name": "JE-3", "company": "ACME"})
        je.set(
            "accounts",
            [
                frappe._dict(
                    account="PAYABLE",
                    reference_type="Payroll Entry",
                    reference_name="PE-OUTPUT-1",
                    party_type="Employee",
                    party="E1",
                    debit=0,
                    credit=100,
                ),
                frappe._dict(account="WAGES", debit=100, credit=0),
            ],
        )
        gl_rows = [
            frappe._dict(account="PAYABLE", party_type="Employee", party="E1", debit=0, credit=100),
            frappe._dict(account="WAGES", debit=100, credit=0),
        ]
        with (
            patch.object(output, "_locked_rows", side_effect=[gl_rows, []]) as locked,
            patch.object(output.frappe, "get_precision", return_value=2),
            self.assertRaisesRegex(frappe.PermissionError, "Payment Ledger amount"),
        ):
            output._gl_effects(je, "PAYABLE", "PE-OUTPUT-1")
        self.assertEqual(locked.call_args.args[1]["docstatus"], 1)

    def test_bank_candidate_rejects_wrong_payment_credit_before_posting(self) -> None:
        pe = self._payroll(payroll_payable_account="PAYABLE", payment_account="BANK")
        slip = frappe._dict(employee="E1", status="Submitted")
        je = Document({"doctype": "Journal Entry", "company": "ACME", "voucher_type": "Bank Entry"})
        je.set(
            "accounts",
            [
                frappe._dict(
                    account="PAYABLE",
                    reference_type="Payroll Entry",
                    reference_name=pe.name,
                    debit=100,
                    credit=0,
                ),
                frappe._dict(account="OTHER", debit=0, credit=100),
            ],
        )
        with (
            patch.object(output, "locked_payroll_entry", return_value=pe),
            patch.object(output, "require_output_review", return_value=[slip]),
            patch.object(
                output,
                "output_payload",
                return_value={
                    "sources": {
                        "accounts": [{"name": "BANK", "account_type": "Bank"}],
                    }
                },
            ),
            patch.object(output, "_native_bank_projection", return_value={"": Decimal(100)}),
            patch.object(output.frappe, "get_precision", return_value=2),
            self.assertRaisesRegex(frappe.PermissionError, "reviewed payment Account"),
        ):
            output.validate_bank_candidate(pe, je, False, Decimal(0))

    def test_close_rejects_bank_credit_to_other_account(self) -> None:
        je = Document({"doctype": "Journal Entry", "name": "JE-2", "company": "ACME"})
        je.set(
            "accounts",
            [
                frappe._dict(
                    account="PAYABLE",
                    reference_type="Payroll Entry",
                    reference_name="PE-OUTPUT-1",
                    debit=100,
                    credit=0,
                ),
                frappe._dict(account="OTHER", debit=0, credit=100),
            ],
        )
        gl_rows = [
            frappe._dict(account="PAYABLE", party_type=None, party=None, debit=100, credit=0),
            frappe._dict(account="OTHER", debit=0, credit=100),
        ]
        with (
            patch.object(output, "_locked_rows", return_value=gl_rows),
            patch.object(output.frappe, "get_precision", return_value=2),
            self.assertRaisesRegex(frappe.PermissionError, "unapproved payment account"),
        ):
            output._gl_effects(je, "PAYABLE", "PE-OUTPUT-1", "BANK")

    def test_queue_dispatch_uses_app_wrapper_and_after_commit(self) -> None:
        pe = self._payroll(workflow_state=output.SUBMITTED, output_review_revision=0)
        user = str(frappe.session.user)
        with (
            patch.object(output, "locked_payroll_entry", return_value=pe),
            patch.object(
                output,
                "_preflight_create",
                return_value=([f"E{i}" for i in range(31)], frappe._dict(payroll_entry=pe.name)),
            ),
            patch.object(output, "_active_job", return_value=False),
            patch.object(output.frappe, "enqueue") as enqueue,
            patch.object(output.frappe, "msgprint"),
            patch.object(pe, "db_set"),
        ):
            output.create_salary_slips(pe)
        kwargs = enqueue.call_args.kwargs
        self.assertIs(enqueue.call_args.args[0], output.create_reviewed_salary_slips_for_employees)
        self.assertTrue(kwargs["enqueue_after_commit"])
        self.assertTrue(kwargs["deduplicate"])
        self.assertEqual(kwargs["timeout"], 3000)
        self.assertEqual(kwargs["initiating_user"], user)
        self.assertEqual(kwargs["expected_employee_ids"], [f"E{i}" for i in range(31)])

    def test_queued_replay_fails_before_native_hrms_worker(self) -> None:
        pe = self._payroll(workflow_state=output.SUBMITTED, status="Queued", output_review_revision=2)
        with (
            patch.object(output, "locked_payroll_entry", return_value=pe),
            patch.object(
                output, "_preflight_create", return_value=(["E1"], frappe._dict(payroll_entry=pe.name))
            ),
            patch.object(output, "create_salary_slips_for_employees") as native,
            self.assertRaisesRegex(frappe.PermissionError, "no longer matches"),
        ):
            output.create_reviewed_salary_slips_for_employees(
                str(pe.name), ["E2"], {"payroll_entry": pe.name}, 2, "reviewer@example.com"
            )
        native.assert_not_called()

    def test_candidate_payable_rejects_wrong_reference(self) -> None:
        pe = self._payroll(payroll_payable_account="PAYABLE")
        je = MagicMock(spec=Document)
        je.get.side_effect = lambda key: {
            "company": "ACME",
            "accounts": [
                frappe._dict(
                    account="PAYABLE",
                    reference_type="Payroll Entry",
                    reference_name="OTHER",
                    debit=0,
                    credit=100,
                    party_type=None,
                    party=None,
                )
            ],
        }.get(key)
        je.docstatus = 0
        with self.assertRaisesRegex(frappe.PermissionError, "another Payroll Entry"):
            output._payable_candidate(je, pe, credit=True)
