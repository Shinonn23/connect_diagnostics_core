# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import employee_identity_import as identity_import


def _valid_identity(prefix: str = "110170020345") -> str:
    checksum_total = sum(int(digit) * (13 - index) for index, digit in enumerate(prefix))
    return f"{prefix}{(11 - (checksum_total % 11)) % 10}"


def _source(
    *,
    source_file: str = "employees.xlsx",
    sheet_name: str = "Employees",
    row_number: int = 2,
    company_abbr: str = "CD",
    fieldname: str = "national_id",
    value: str | None = None,
    employee_code: str = "1001",
    email: str = "one@example.com",
    thai_name: str = "นาย ทดสอบ หนึ่ง",
    english_name: str = "Mr Test One",
    intentionally_withheld: bool = False,
    allow_cross_company_name_match: bool = False,
) -> identity_import.IdentitySourceRecord:
    return identity_import.IdentitySourceRecord(
        source_file=source_file,
        sheet_name=sheet_name,
        row_number=row_number,
        company_abbr=company_abbr,
        fieldname=fieldname,
        value=value or _valid_identity(),
        employee_code=employee_code,
        email=email,
        thai_name=thai_name,
        english_name=english_name,
        intentionally_withheld=intentionally_withheld,
        allow_cross_company_name_match=allow_cross_company_name_match,
    )


def _candidate(
    *,
    name: str = "EMP-001",
    company_abbr: str = "CD",
    employee_code: str = "1001",
    emails: frozenset[str] = frozenset({"one@example.com"}),
    thai_names: frozenset[str] | None = None,
    english_names: frozenset[str] | None = None,
    national_id: str = "",
    tax_id: str = "",
) -> identity_import.EmployeeIdentityCandidate:
    return identity_import.EmployeeIdentityCandidate(
        name=name,
        company_abbr=company_abbr,
        employee_codes=frozenset({employee_code}) if employee_code else frozenset(),
        emails=emails,
        thai_names=thai_names or frozenset({identity_import.normalize_person_name("ทดสอบ หนึ่ง")}),
        english_names=english_names or frozenset({identity_import.normalize_person_name("Test One")}),
        national_id=national_id,
        tax_id=tax_id,
    )


class TestEmployeeIdentityImport(UnitTestCase):
    def test_cd_employee_code_has_priority_over_email(self) -> None:
        code_candidate = _candidate()
        email_candidate = _candidate(
            name="EMP-002",
            employee_code="1002",
            emails=frozenset({"other@example.com"}),
        )

        decisions = identity_import.plan_identity_import(
            [_source(email="other@example.com")],
            [code_candidate, email_candidate],
        )

        self.assertEqual(decisions[0].status, "ready")
        self.assertEqual(decisions[0].employee, "EMP-001")
        self.assertEqual(decisions[0].match_method, "employee_code")

    def test_cd_falls_back_to_email(self) -> None:
        decisions = identity_import.plan_identity_import(
            [_source(employee_code="missing")],
            [_candidate()],
        )
        self.assertEqual(decisions[0].employee, "EMP-001")
        self.assertEqual(decisions[0].match_method, "email")

    def test_cd_tax_source_without_code_or_email_matches_normalized_name(self) -> None:
        source = _source(employee_code="", email="", thai_name="นาย ทดสอบ หนึ่ง")

        decisions = identity_import.plan_identity_import([source], [_candidate()])

        self.assertEqual(decisions[0].employee, "EMP-001")
        self.assertEqual(decisions[0].match_method, "normalized_name")

    def test_ub_falls_back_from_email_to_normalized_thai_name(self) -> None:
        source = _source(
            company_abbr="UB",
            employee_code="",
            email="",
            thai_name="นส. ทดสอบ   หนึ่ง",
        )
        decisions = identity_import.plan_identity_import(
            [source],
            [_candidate(company_abbr="UB", employee_code="")],
        )
        self.assertEqual(decisions[0].employee, "EMP-001")
        self.assertEqual(decisions[0].match_method, "normalized_name")

    def test_approved_transfer_matches_name_across_companies(self) -> None:
        source = _source(
            company_abbr="UB",
            employee_code="",
            email="",
            thai_name="นส. ทดสอบ หนึ่ง",
            allow_cross_company_name_match=True,
        )

        decisions = identity_import.plan_identity_import([source], [_candidate()])

        self.assertEqual(decisions[0].employee, "EMP-001")
        self.assertEqual(decisions[0].match_method, "transferred_normalized_name")

    def test_ambiguous_match_is_not_writeable(self) -> None:
        decisions = identity_import.plan_identity_import(
            [_source()],
            [_candidate(), _candidate(name="EMP-002")],
        )
        self.assertEqual(decisions[0].status, "ambiguous")
        self.assertFalse(decisions[0].should_write)

    def test_intentionally_withheld_national_id_is_not_writeable(self) -> None:
        decisions = identity_import.plan_identity_import(
            [_source(intentionally_withheld=True)],
            [_candidate()],
        )
        self.assertEqual(decisions[0].status, "withheld")

    def test_invalid_checksum_is_not_writeable(self) -> None:
        decisions = identity_import.plan_identity_import([_source(value="123")], [_candidate()])
        self.assertEqual(decisions[0].status, "invalid")

    def test_existing_different_value_is_a_conflict(self) -> None:
        decisions = identity_import.plan_identity_import(
            [_source()],
            [_candidate(national_id=_valid_identity("310060012345"))],
        )
        self.assertEqual(decisions[0].status, "conflict")

    def test_same_identity_targeting_two_employees_is_a_conflict(self) -> None:
        records = [
            _source(employee_code="1001"),
            _source(row_number=3, employee_code="1002", email="two@example.com"),
        ]
        candidates = [
            _candidate(),
            _candidate(
                name="EMP-002",
                employee_code="1002",
                emails=frozenset({"two@example.com"}),
            ),
        ]

        decisions = identity_import.plan_identity_import(records, candidates)
        self.assertEqual([decision.status for decision in decisions], ["conflict", "conflict"])

    def test_report_contains_only_masked_identity_and_email(self) -> None:
        identity = _valid_identity()
        decisions = identity_import.plan_identity_import([_source(value=identity)], [_candidate()])

        report_rows = identity_import.get_report_rows(decisions)

        self.assertNotIn(identity, str(report_rows))
        self.assertNotIn("one@example.com", str(report_rows))
        self.assertEqual(report_rows[0]["masked_value"], f"*********{identity[-4:]}")

    @patch.object(identity_import.frappe, "get_doc")
    def test_apply_groups_fields_into_one_employee_save(self, mocked_get_doc: MagicMock) -> None:
        national_id = _valid_identity("110170020345")
        tax_id = _valid_identity("310060012345")
        decisions = identity_import.plan_identity_import(
            [
                _source(value=national_id),
                _source(fieldname="tax_id", value=tax_id, row_number=3),
            ],
            [_candidate()],
        )
        employee_doc = MagicMock()
        employee_doc.get.return_value = ""
        mocked_get_doc.return_value = employee_doc

        result = identity_import.apply_identity_import(decisions)

        self.assertEqual(result, {"employees_updated": 1, "fields_updated": 2})
        mocked_get_doc.assert_called_once_with("Employee", "EMP-001", for_update=True)
        self.assertEqual(
            employee_doc.set.call_args_list,
            [(("national_id", national_id),), (("tax_id", tax_id),)],
        )
        employee_doc.save.assert_called_once_with(ignore_permissions=True, ignore_version=True)

    @patch.object(identity_import.frappe, "get_doc")
    def test_apply_stops_if_identity_changed_after_preflight(
        self,
        mocked_get_doc: MagicMock,
    ) -> None:
        decisions = identity_import.plan_identity_import([_source()], [_candidate()])
        employee_doc = MagicMock()
        employee_doc.get.return_value = _valid_identity("310060012345")
        mocked_get_doc.return_value = employee_doc

        with self.assertRaises(identity_import.frappe.ValidationError):
            identity_import.apply_identity_import(decisions)

        employee_doc.set.assert_not_called()
        employee_doc.save.assert_not_called()

    @patch.object(identity_import.frappe, "get_doc")
    def test_apply_treats_concurrently_imported_same_value_as_unchanged(
        self,
        mocked_get_doc: MagicMock,
    ) -> None:
        identity = _valid_identity()
        decisions = identity_import.plan_identity_import([_source(value=identity)], [_candidate()])
        employee_doc = MagicMock()
        employee_doc.get.return_value = identity
        mocked_get_doc.return_value = employee_doc

        result = identity_import.apply_identity_import(decisions)

        self.assertEqual(result, {"employees_updated": 0, "fields_updated": 0})
        employee_doc.set.assert_not_called()
        employee_doc.save.assert_not_called()
