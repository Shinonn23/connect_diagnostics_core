# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date
from typing import Any, Protocol, cast

import frappe
from erpnext.setup.doctype.employee.employee import Employee
from frappe import _
from frappe.utils import getdate


class _EmployeeNamingSeries(Protocol):
	naming_series: str


def before_naming(doc: Employee, _method: Any) -> None:
	naming_series: str = cast(str, doc.get("naming_series") or "")
	if not naming_series:
		return

	date_of_joining: str | None = cast(str | None, doc.get("date_of_joining"))
	if not date_of_joining:
		frappe.throw(_("Date of joining is required to generate the employee ID"))

	joining_date = getdate(date_of_joining)
	if not joining_date:
		frappe.throw(_("Date of joining is required to generate the employee ID"))
	joining_date = cast(date, joining_date)

	# Replace date tokens with values from date_of_joining.
	# YYYY must be substituted before YY to avoid partial double-replacement.
	date_tokens = (
		naming_series.replace("YYYY", joining_date.strftime("%Y"))
		.replace("YY", joining_date.strftime("%y"))
		.replace("MM", joining_date.strftime("%m"))
	)
	cast(_EmployeeNamingSeries, doc).naming_series = date_tokens
