# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date
from typing import cast

import frappe
from erpnext.setup.doctype.employee.employee import Employee
from frappe import _


class CustomEmployee(Employee):
    naming_series: str
    date_of_joining: date

    def autoname(self) -> None:
        if not self.date_of_joining:
            frappe.throw(_("Date of joining is required to generate the employee ID"))

        # Replace date tokens with values from date_of_joining.
        # YYYY must be substituted before YY to avoid partial double-replacement.
        self.naming_series = (
            self.naming_series.replace("YYYY", self.date_of_joining.strftime("%Y"))
            .replace("YY", self.date_of_joining.strftime("%y"))
            .replace("MM", self.date_of_joining.strftime("%m"))
        )
