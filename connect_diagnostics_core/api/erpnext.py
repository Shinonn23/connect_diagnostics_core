import inspect
from typing import cast

from erpnext.setup.doctype.employee.employee import Employee
from frappe import throw
from frappe.model.naming import make_autoname  # pyright: ignore[reportUnknownVariableType]
from frappe.utils import getdate


def set_thai_employee_name(doc: Employee, method: str) -> None:
	if method != "validate":
		return

	first_name: str = cast(str, doc.get("custom_first_name_th") or "").strip()  # pyright: ignore[reportUnknownMemberType]
	last_name: str = cast(str, doc.get("custom_last_name_th") or "").strip()  # pyright: ignore[reportUnknownMemberType]

	if first_name and last_name:
		doc.custom_full_name_th = f"{first_name} {last_name}"  # pyright: ignore[reportAttributeAccessIssue]


def generate_thai_year_autoname(doc: Employee, _method: str) -> None:
	joining_date = getdate(doc.date_of_joining) if doc.date_of_joining else None  # pyright: ignore[reportUnknownMemberType,  reportAttributeAccessIssue, reportUnknownArgumentType]
	if not joining_date:
		current_line = inspect.currentframe().f_lineno or 0  # pyright: ignore[reportOptionalMemberAccess]

		throw(
			f"Cannot generate autoname: today's date is not available. File: {__file__}, Line: {current_line}"
		)
		return
	thai_year: str = str(joining_date.year + 543)[-2:]
	thai_month: str = f"{joining_date.month:02d}"
	prefix = f"{thai_year}{thai_month}."
	doc.name = make_autoname(f"{prefix}###")
