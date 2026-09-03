# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import company


class TestCompanyAuthorizedSignatories(UnitTestCase):
    def test_duplicate_rows_are_rejected_before_employee_validation(self) -> None:
        doc = cast(
            Document,
            frappe._dict(
                {
                    "name": "COMP-0001",
                    "quotation_authorized_signatories": [
                        frappe._dict({"employee": "EMP-0001"}),
                        frappe._dict({"employee": "EMP-0001"}),
                    ],
                }
            ),
        )

        with patch.object(company, "validate_quotation_authorized_signatory_employee") as mocked_validate:
            with self.assertRaises(frappe.ValidationError):
                company.validate_quotation_authorized_signatories(doc)

        mocked_validate.assert_called_once_with("EMP-0001", "COMP-0001")

    @patch.object(company.frappe.db, "exists", return_value=False)
    @patch.object(
        company.frappe.db,
        "get_value",
        return_value={"company": "COMP-0001", "status": "Active", "user_id": "user@example.com"},
    )
    def test_employee_must_have_the_sales_manager_role(
        self, _get_value: MagicMock, _exists: MagicMock
    ) -> None:
        with self.assertRaises(frappe.ValidationError):
            company.validate_quotation_authorized_signatory_employee("EMP-0001", "COMP-0001")

    @patch.object(company.frappe.db, "exists", return_value=True)
    @patch.object(
        company.frappe.db,
        "get_value",
        return_value={"company": "COMP-0001", "status": "Active", "user_id": "user@example.com"},
    )
    def test_active_employee_in_the_same_company_with_role_is_valid(
        self, _get_value: MagicMock, _exists: MagicMock
    ) -> None:
        company.validate_quotation_authorized_signatory_employee("EMP-0001", "COMP-0001")

    def test_sidebar_rows_retain_missing_signatures_as_not_ready(self) -> None:
        child_rows = [
            {"employee": "EMP-0001", "idx": 1},
            {"employee": "EMP-0002", "idx": 2},
        ]
        employee_rows = [
            {
                "name": "EMP-0001",
                "employee_name": "Sales Manager",
                "company": "COMP-0001",
                "status": "Active",
                "user_id": "manager@example.com",
                "quotation_signature": "data:image/png;base64,signature",
            },
            {
                "name": "EMP-0002",
                "employee_name": "Second Manager",
                "company": "COMP-0001",
                "status": "Active",
                "user_id": "second@example.com",
                "quotation_signature": "",
            },
        ]

        def get_all(doctype: str, **_kwargs: Any) -> list[dict[str, Any]]:
            return child_rows if doctype == company.AUTHORIZED_SIGNATORY_DOCTYPE else employee_rows

        with (
            patch.object(company.frappe, "get_all", side_effect=get_all),
            patch.object(
                company.frappe.db,
                "sql",
                return_value=["manager@example.com", "second@example.com"],
            ),
        ):
            rows = company.get_quotation_authorized_signatories("COMP-0001")

        self.assertEqual([row["employee"] for row in rows], ["EMP-0001", "EMP-0002"])
        self.assertTrue(rows[0]["ready"])
        self.assertFalse(rows[1]["ready"])

    @patch.object(company.frappe.db, "exists", return_value=True)
    @patch.object(company.frappe.db, "sql", return_value=[])
    @patch.object(company, "get_match_cond", return_value="")
    @patch.object(company.frappe, "has_permission", return_value=True)
    def test_link_query_qualifies_employee_table_without_an_alias(
        self,
        _has_permission: MagicMock,
        _match_cond: MagicMock,
        mocked_sql: MagicMock,
        _exists: MagicMock,
    ) -> None:
        company.authorized_signatory_employee_query(
            "Employee", "manager", "name", 0, 20, {"company": "COMP-0001"}
        )

        query, values = mocked_sql.call_args.args
        self.assertIn("`tabEmployee`.company", query)
        self.assertNotIn(" e.", query)
        self.assertEqual(values["company"], "COMP-0001")
        self.assertEqual(values["role"], "Sales Manager")
