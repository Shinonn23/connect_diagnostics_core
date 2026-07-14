# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

import click
import frappe
from frappe.commands import pass_context
from frappe.utils import cint

COUNTER_SUFFIX_PATTERN = re.compile(r"\.(#+)$")


@dataclass(frozen=True)
class EmployeeSeriesCounterResult:
    prefix: str
    employee_count: int
    highest_counter: int
    current_counter: int
    action: str


def sync_employee_series_counters(*, apply: bool, force: bool = False) -> list[EmployeeSeriesCounterResult]:
    """Return Employee series counters and optionally raise stale counters to the highest used value."""

    highest_counters: dict[str, int] = {}
    employee_counts: defaultdict[str, int] = defaultdict(int)
    employees = frappe.get_all("Employee", fields=["name", "naming_series"], order_by="name")

    for employee in employees:
        counter = _get_employee_counter(employee.name, employee.naming_series)
        if counter is None:
            continue

        prefix, value = counter
        employee_counts[prefix] += 1
        highest_counters[prefix] = max(highest_counters.get(prefix, 0), value)

    results: list[EmployeeSeriesCounterResult] = []
    for prefix in sorted(highest_counters):
        current_counter = _get_current_counter(prefix, lock=apply)
        highest_counter = highest_counters[prefix]
        action = "unchanged"

        if current_counter < highest_counter or (force and current_counter > highest_counter):
            action = "updated" if apply else "would-update"
            if apply:
                _set_counter(prefix, highest_counter, force=force)

        results.append(
            EmployeeSeriesCounterResult(
                prefix=prefix,
                employee_count=employee_counts[prefix],
                highest_counter=highest_counter,
                current_counter=current_counter,
                action=action,
            )
        )

    return results


def _get_employee_counter(name: str, naming_series: str | None) -> tuple[str, int] | None:
    if not naming_series:
        return None

    match = COUNTER_SUFFIX_PATTERN.search(naming_series)
    if match is None:
        return None

    digits = len(match.group(1))
    if len(name) <= digits:
        return None

    counter_text = name[-digits:]
    if not counter_text.isdigit():
        return None

    return name[:-digits], cint(counter_text)


def _get_current_counter(prefix: str, *, lock: bool) -> int:
    current = frappe.db.get_value("Series", prefix, "current", order_by="name", for_update=lock)
    return cint(current)


def _set_counter(prefix: str, value: int, *, force: bool) -> None:
    if force:
        frappe.db.sql(
            """
            INSERT INTO `tabSeries` (`name`, `current`) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE `current` = VALUES(`current`)
            """,
            (prefix, value),
        )
        return

    frappe.db.sql(
        """
        INSERT INTO `tabSeries` (`name`, `current`) VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE `current` = GREATEST(`current`, VALUES(`current`))
        """,
        (prefix, value),
    )


@click.command("sync-employee-series-counters")
@click.option("--apply", is_flag=True, help="Write counters. Without this flag the command only previews.")
@click.option("--force", is_flag=True, help="Also lower counters that are above the highest Employee number.")
@pass_context
def sync_employee_series_counters_command(context, apply: bool, force: bool) -> None:
    """Check Employee naming-series counters and bring stale counters forward."""

    if not context.sites:
        raise frappe.SiteNotSpecifiedError
    if force and not apply:
        raise click.UsageError("--force requires --apply.")

    for site in context.sites:
        frappe.init(site=site)
        try:
            frappe.connect()
            results = sync_employee_series_counters(apply=apply, force=force)
            if apply:
                frappe.db.commit()  # nosemgrep

            for result in results:
                click.echo(
                    f"{site}: {result.action} prefix={result.prefix} "
                    f"highest={result.highest_counter} current={result.current_counter} "
                    f"employees={result.employee_count}"
                )
        except Exception:
            if frappe.db:
                frappe.db.rollback()
            raise
        finally:
            frappe.destroy()
