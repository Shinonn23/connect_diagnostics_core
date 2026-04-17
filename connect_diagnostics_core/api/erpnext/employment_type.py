import re
from typing import cast

from frappe import throw
from frappe.model.document import Document

TOKEN_PATTERN = re.compile(r"\{(?:YYYY|YY|MM|DD|#+)\}|YYYY|YY|MM|DD|#+")


def validate_employment_type_format(doc: Document, method: str) -> None:
	if method != "validate":
		return

	format_pattern = cast(str, doc.get("custom_format") or "").strip()

	if not doc.is_new():
		previous_doc = doc.get_doc_before_save()
		if previous_doc:
			previous_format = cast(str, previous_doc.get("custom_format") or "").strip()
			if previous_format != format_pattern:
				throw("Format cannot be changed after this Employment Type is created.")

	if not format_pattern:
		throw("Format is required. Example: YYMM.###")

	if not re.search(r"\{#+\}|#+", format_pattern):
		throw(
			"Format must include # (for example #, ##, ###, or {###}) for running sequence. Example: C{YY}{MM}.{###}"
		)

	remaining = TOKEN_PATTERN.sub("", format_pattern)

	if "{" in remaining or "}" in remaining:
		throw(
			"Unsupported token found. Supported tokens are {YYYY}, {YY}, {MM}, {DD}, {#...}, and legacy YYYY, YY, MM, DD, #..."
		)

	if re.search(r"[YMD#]", remaining):
		throw(
			"Unsupported token found. Supported tokens are {YYYY}, {YY}, {MM}, {DD}, {#...}, and legacy YYYY, YY, MM, DD, #..."
		)

	if not re.fullmatch(r"[A-Za-z0-9._/\\-]*", remaining):
		throw(
			"Format contains unsupported characters. Use letters, numbers, dot (.), dash (-), underscore (_), slash (/), and tokens {YYYY}, {YY}, {MM}, {DD}, {#...} only."
		)


def validate(doc: Document, method: str):
	validate_employment_type_format(doc, method)
