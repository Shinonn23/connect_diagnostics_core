import re
from typing import cast

import frappe
from erpnext.setup.doctype.employee.employee import Employee
from frappe import throw
from frappe.model.naming import make_autoname
from frappe.utils import getdate


def _apply_autoname_tokens(
	format_pattern: str,
	thai_year_2: str,
	thai_year_4: str,
	thai_month: str,
	thai_day: str,
) -> str:
	token_values = {
		"YYYY": thai_year_4,
		"YY": thai_year_2,
		"MM": thai_month,
		"DD": thai_day,
	}

	resolved = format_pattern
	for token, value in token_values.items():
		resolved = resolved.replace(f"{{{token}}}", value)

	# Keep backward compatibility with legacy non-brace token format.
	for token, value in token_values.items():
		resolved = re.sub(token, value, resolved)

	# Handle hash sequences of any length, e.g. {##} -> ##, {###} -> ###, etc.
	# and we just leave legacy ## or ### without braces as they are.
	resolved = re.sub(r"\{(#+)\}", r"\1", resolved)

	return resolved


def set_thai_employee_name(doc: Employee, method: str) -> None:
	if method != "validate":
		return

	first_name: str = cast(str, doc.get("custom_first_name_th") or "").strip()
	last_name: str = cast(str, doc.get("custom_last_name_th") or "").strip()

	if first_name and last_name:
		doc.custom_full_name_th = f"{first_name} {last_name}"  # ty: ignore[unresolved-attribute] - runtime-injected attribute (employee.json)


def _resolve_employee_autoname_pattern(
	doc: Employee,
	thai_year_2: str,
	thai_year_4: str,
	thai_month: str,
	thai_day: str,
) -> str:
	employment_type = cast(str, doc.get("employment_type") or "").strip()

	if employment_type:
		custom_format = cast(
			str,
			frappe.db.get_value("Employment Type", employment_type, "custom_format") or "",
		).strip()

		if custom_format:
			return _apply_autoname_tokens(
				custom_format,
				thai_year_2,
				thai_year_4,
				thai_month,
				thai_day,
			)

	# Legacy format from old logic: Thai 2-digit year + 2-digit month + running sequence
	return f"{thai_year_2}{thai_month}.###"


def autoname(doc: Employee, _method: str) -> None:
	joining_date = (
		getdate(doc.date_of_joining)  # ty:ignore[unresolved-attribute] - runtime-injected attribute (hrms)
		if doc.date_of_joining  # ty:ignore[unresolved-attribute] - runtime-injected attribute (hrms)
		else None
	)
	if not joining_date:
		throw("Cannot generate autoname: joining date is not available.")
		return
	thai_year_4: str = str(joining_date.year + 543)
	thai_year_2: str = thai_year_4[-2:]
	thai_month: str = f"{joining_date.month:02d}"
	thai_day: str = f"{joining_date.day:02d}"
	autoname_pattern = _resolve_employee_autoname_pattern(
		doc,
		thai_year_2,
		thai_year_4,
		thai_month,
		thai_day,
	)
	doc.name = make_autoname(autoname_pattern)


def validate(doc: Employee, _method: str):
	set_thai_employee_name(doc, _method)
