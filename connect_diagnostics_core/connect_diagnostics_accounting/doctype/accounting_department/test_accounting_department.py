# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from typing import cast

import frappe
from frappe.tests.utils import FrappeTestCase

from connect_diagnostics_core.connect_diagnostics_accounting.doctype.accounting_department.accounting_department import (
    AccountingDepartment,
)

test_records = frappe.get_test_records("Accounting Department")


class TestAccountingDepartment(FrappeTestCase):
    def test_creation_against_non_group_parent_is_rejected(self) -> None:
        if not frappe.db.get_value("Accounting Department", {"name": "_Test Accounting Department 2 - _TC"}):
            frappe.get_doc(test_records[1]).insert()

        department = frappe.get_doc(
            {
                "doctype": "Accounting Department",
                "department_name": "_Test Accounting Department 3",
                "parent_accounting_department": "_Test Accounting Department 2 - _TC",
                "is_group": 0,
                "company": "_Test Company",
            }
        )

        self.assertRaises(frappe.ValidationError, department.save)


def create_accounting_department(**args) -> None:
    args = frappe._dict(args)
    if args.department_name:
        company = args.company or "_Test Company"
        company_abbr = frappe.db.get_value("Company", company, "abbr")
        dept_name = args.department_name + " - " + company_abbr
        if not frappe.db.exists("Accounting Department", dept_name):
            dept = cast(AccountingDepartment, frappe.new_doc("Accounting Department"))
            dept.company = company
            dept.department_name = args.department_name
            dept.is_group = args.is_group or 0
            dept.parent_accounting_department = args.parent_accounting_department or "_Test Company - _TC"
            dept.insert()
