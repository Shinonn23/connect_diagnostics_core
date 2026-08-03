# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Preflight and transactional helpers for Employee identity imports."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import cast

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.erpnext.employee import (
    IDENTITY_FIELDS,
    is_valid_thai_identity_number,
    normalize_thai_identity_number,
)

SUPPORTED_COMPANY_ABBRS = {"CD", "UB"}


@dataclass(frozen=True)
class IdentitySourceRecord:
    source_file: str
    sheet_name: str
    row_number: int
    company_abbr: str
    fieldname: str
    value: str = field(repr=False)
    employee_code: str = ""
    email: str = ""
    thai_name: str = ""
    english_name: str = ""
    intentionally_withheld: bool = False
    allow_cross_company_name_match: bool = False


@dataclass(frozen=True)
class EmployeeIdentityCandidate:
    name: str
    company_abbr: str
    employee_codes: frozenset[str] = frozenset()
    emails: frozenset[str] = frozenset()
    thai_names: frozenset[str] = frozenset()
    english_names: frozenset[str] = frozenset()
    national_id: str = field(default="", repr=False)
    tax_id: str = field(default="", repr=False)


@dataclass
class IdentityImportDecision:
    source: IdentitySourceRecord
    status: str
    reason: str
    employee: str = ""
    match_method: str = ""
    normalized_value: str = field(default="", repr=False)

    @property
    def should_write(self) -> bool:
        return self.status == "ready"


def normalize_employee_code(value: object) -> str:
    normalized = str(value or "").strip()
    if re.fullmatch(r"\d+\.0", normalized):
        return normalized[:-2]
    return normalized


def normalize_email(value: object) -> str:
    return str(value or "").strip().casefold()


def normalize_person_name(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    normalized = re.sub(
        r"^(?:miss|mrs|mr|ms|นางสาว|น\.ส\.|นส\.|นาง|นาย)\s*\.?\s*",
        "",
        normalized,
    )
    return "".join(character for character in normalized if character.isalnum())


def mask_identity_number(value: object) -> str:
    normalized = normalize_thai_identity_number(value)
    if len(normalized) != 13 or not normalized.isdigit():
        return "<masked>" if normalized else ""
    return f"{'*' * 9}{normalized[-4:]}"


def mask_email(value: object) -> str:
    normalized = normalize_email(value)
    if not normalized or "@" not in normalized:
        return ""
    local_part, domain = normalized.rsplit("@", 1)
    return f"{local_part[:1]}***@{domain}"


def load_employee_candidates() -> list[EmployeeIdentityCandidate]:
    company_abbrs = {
        company.name: company.abbr for company in frappe.get_all("Company", fields=["name", "abbr"])
    }
    employee_rows = frappe.get_all(
        "Employee",
        fields=[
            "name",
            "company",
            "employee_number",
            "company_email",
            "personal_email",
            "prefered_email",
            "user_id",
            "employee_name",
            "first_name",
            "middle_name",
            "last_name",
            "first_name_en",
            "last_name_en",
            "national_id",
            "tax_id",
        ],
        order_by="name",
    )

    candidates: list[EmployeeIdentityCandidate] = []
    for employee in employee_rows:
        company_abbr = cast(str, company_abbrs.get(employee.company, ""))
        employee_codes = frozenset(
            code
            for raw_code in (employee.name, employee.employee_number)
            if (code := normalize_employee_code(raw_code))
        )
        emails = frozenset(
            email
            for raw_email in (
                employee.company_email,
                employee.personal_email,
                employee.prefered_email,
                employee.user_id,
            )
            if (email := normalize_email(raw_email))
        )
        thai_names = frozenset(
            name
            for raw_name in (
                employee.employee_name,
                " ".join(
                    name_part
                    for name_part in (employee.first_name, employee.middle_name, employee.last_name)
                    if name_part
                ),
            )
            if (name := normalize_person_name(raw_name))
        )
        english_names = frozenset(
            name
            for raw_name in (
                " ".join(
                    name_part for name_part in (employee.first_name_en, employee.last_name_en) if name_part
                ),
            )
            if (name := normalize_person_name(raw_name))
        )
        candidates.append(
            EmployeeIdentityCandidate(
                name=employee.name,
                company_abbr=company_abbr,
                employee_codes=employee_codes,
                emails=emails,
                thai_names=thai_names,
                english_names=english_names,
                national_id=employee.national_id or "",
                tax_id=employee.tax_id or "",
            )
        )
    return candidates


def plan_identity_import(
    source_records: list[IdentitySourceRecord],
    candidates: list[EmployeeIdentityCandidate],
) -> list[IdentityImportDecision]:
    decisions = [_plan_source_record(source, candidates) for source in source_records]
    _mark_plan_collisions(decisions)
    return decisions


def _plan_source_record(
    source: IdentitySourceRecord,
    candidates: list[EmployeeIdentityCandidate],
) -> IdentityImportDecision:
    if source.fieldname not in IDENTITY_FIELDS:
        return IdentityImportDecision(source, "invalid", "Unsupported identity field")
    if source.company_abbr not in SUPPORTED_COMPANY_ABBRS:
        return IdentityImportDecision(source, "unmatched", "Company is outside the approved scope")
    if source.intentionally_withheld:
        return IdentityImportDecision(source, "withheld", "National ID intentionally withheld")

    normalized_value = normalize_thai_identity_number(source.value)
    if not is_valid_thai_identity_number(normalized_value):
        return IdentityImportDecision(
            source,
            "invalid",
            "Identity number must have 13 digits and a valid checksum",
            normalized_value=normalized_value,
        )

    matches, match_method = _match_employee(source, candidates)
    if not matches:
        return IdentityImportDecision(
            source,
            "unmatched",
            "No employee matched the approved keys",
            match_method=match_method,
            normalized_value=normalized_value,
        )
    if len(matches) > 1:
        return IdentityImportDecision(
            source,
            "ambiguous",
            "More than one employee matched the approved keys",
            match_method=match_method,
            normalized_value=normalized_value,
        )

    employee = matches[0]
    existing_owners = [
        candidate
        for candidate in candidates
        if candidate.name != employee.name
        and normalize_thai_identity_number(cast(str, getattr(candidate, source.fieldname)))
        == normalized_value
    ]
    if existing_owners:
        return IdentityImportDecision(
            source,
            "conflict",
            "Identity number is already assigned to another employee",
            employee=employee.name,
            match_method=match_method,
            normalized_value=normalized_value,
        )

    existing_value = cast(str, getattr(employee, source.fieldname))
    if existing_value:
        if normalize_thai_identity_number(existing_value) == normalized_value:
            return IdentityImportDecision(
                source,
                "unchanged",
                "Employee already has the same value",
                employee=employee.name,
                match_method=match_method,
                normalized_value=normalized_value,
            )
        return IdentityImportDecision(
            source,
            "conflict",
            "Employee already has a different value",
            employee=employee.name,
            match_method=match_method,
            normalized_value=normalized_value,
        )

    return IdentityImportDecision(
        source,
        "ready",
        "Ready to import",
        employee=employee.name,
        match_method=match_method,
        normalized_value=normalized_value,
    )


def _match_employee(
    source: IdentitySourceRecord,
    candidates: list[EmployeeIdentityCandidate],
) -> tuple[list[EmployeeIdentityCandidate], str]:
    company_candidates = [
        candidate for candidate in candidates if candidate.company_abbr == source.company_abbr
    ]
    if source.company_abbr == "CD":
        employee_code = normalize_employee_code(source.employee_code)
        if employee_code:
            code_matches = [
                candidate for candidate in company_candidates if employee_code in candidate.employee_codes
            ]
            if code_matches:
                return code_matches, "employee_code"
        email_matches, match_method = _match_by_email(source, company_candidates)
        if email_matches or source.email:
            return email_matches, match_method
        return _match_by_name(source, company_candidates)

    email_matches, match_method = _match_by_email(source, company_candidates)
    if email_matches:
        return email_matches, match_method
    if source.allow_cross_company_name_match:
        name_matches, _ = _match_by_name(source, candidates)
        return name_matches, "transferred_normalized_name"
    return _match_by_name(source, company_candidates)


def _match_by_email(
    source: IdentitySourceRecord,
    candidates: list[EmployeeIdentityCandidate],
) -> tuple[list[EmployeeIdentityCandidate], str]:
    email = normalize_email(source.email)
    if not email:
        return [], "email"
    return [candidate for candidate in candidates if email in candidate.emails], "email"


def _match_by_name(
    source: IdentitySourceRecord,
    candidates: list[EmployeeIdentityCandidate],
) -> tuple[list[EmployeeIdentityCandidate], str]:
    thai_name = normalize_person_name(source.thai_name)
    english_name = normalize_person_name(source.english_name)
    matches = {
        candidate
        for candidate in candidates
        if (thai_name and thai_name in candidate.thai_names)
        or (english_name and english_name in candidate.english_names)
    }
    return sorted(matches, key=lambda candidate: candidate.name), "normalized_name"


def _mark_plan_collisions(decisions: list[IdentityImportDecision]) -> None:
    ready_decisions = [decision for decision in decisions if decision.should_write]
    by_employee_field: dict[tuple[str, str], list[IdentityImportDecision]] = {}
    by_field_value: dict[tuple[str, str], list[IdentityImportDecision]] = {}
    for decision in ready_decisions:
        by_employee_field.setdefault((decision.employee, decision.source.fieldname), []).append(decision)
        by_field_value.setdefault((decision.source.fieldname, decision.normalized_value), []).append(decision)

    for grouped_decisions in by_employee_field.values():
        distinct_values = {decision.normalized_value for decision in grouped_decisions}
        if len(distinct_values) > 1:
            _set_conflict(grouped_decisions, "Multiple source values target the same employee field")
        elif len(grouped_decisions) > 1:
            for duplicate in grouped_decisions[1:]:
                duplicate.status = "duplicate"
                duplicate.reason = "Duplicate source row for the same employee and value"

    for grouped_decisions in by_field_value.values():
        distinct_employees = {decision.employee for decision in grouped_decisions}
        if len(distinct_employees) > 1:
            _set_conflict(grouped_decisions, "The same identity number targets multiple employees")


def _set_conflict(decisions: list[IdentityImportDecision], reason: str) -> None:
    for decision in decisions:
        decision.status = "conflict"
        decision.reason = reason


def apply_identity_import(decisions: list[IdentityImportDecision]) -> dict[str, int]:
    """Apply preflight-approved values while locking and revalidating every target."""
    values_by_employee: dict[str, dict[str, str]] = {}
    for decision in decisions:
        if not decision.should_write:
            continue
        values_by_employee.setdefault(decision.employee, {})[decision.source.fieldname] = (
            decision.normalized_value
        )

    employees_updated = 0
    fields_updated = 0
    for employee_name in sorted(values_by_employee):
        values = values_by_employee[employee_name]
        employee = cast(Document, frappe.get_doc("Employee", employee_name, for_update=True))
        values_to_write: dict[str, str] = {}
        for fieldname, value in values.items():
            current_value = normalize_thai_identity_number(cast(str, employee.get(fieldname) or ""))
            if current_value and current_value != value:
                frappe.throw(
                    _("Employee identity changed after preflight. Run preflight again before importing.")
                )
            if current_value == value:
                continue
            values_to_write[fieldname] = value

        for fieldname, value in values_to_write.items():
            employee.set(fieldname, value)
        if not values_to_write:
            continue
        employee.save(ignore_permissions=True, ignore_version=True)
        employees_updated += 1
        fields_updated += len(values_to_write)

    return {"employees_updated": employees_updated, "fields_updated": fields_updated}


def get_report_rows(decisions: list[IdentityImportDecision]) -> list[dict[str, object]]:
    """Return an audit report that never contains a complete identity number or email."""
    return [
        {
            "source_file": decision.source.source_file,
            "sheet": decision.source.sheet_name,
            "row": decision.source.row_number,
            "company": decision.source.company_abbr,
            "field": decision.source.fieldname,
            "employee_code": decision.source.employee_code,
            "email": mask_email(decision.source.email),
            "thai_name": decision.source.thai_name,
            "english_name": decision.source.english_name,
            "masked_value": mask_identity_number(decision.normalized_value or decision.source.value),
            "status": decision.status,
            "employee": decision.employee,
            "match_method": decision.match_method,
            "reason": decision.reason,
        }
        for decision in decisions
    ]
