# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Scheduled expiry processing for regulatory registrations and evidence."""

from __future__ import annotations

from datetime import date
from typing import Any, cast

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, now_datetime, today
from frappe.utils.user import get_users_with_role

from connect_diagnostics_core.api.erpnext import regulatory

SETTINGS_DOCTYPE = "Medical Device Regulatory Settings"
PRODUCT_REGISTRATION = "Medical Device Product Registration"
REGULATORY_DOCUMENT = "Medical Device Regulatory Document"
ALERT_LOG = "Medical Device Regulatory Alert Log"
REGISTRATION_ALERT = "Registration Expiry"
DOCUMENT_ALERT = "Supporting Document Expiry"


def run_daily_expiry_processing() -> None:
    """Update expiry facts, create one alert per registration/document threshold, and notify recipients."""
    settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
    rules = list(settings.get("expiry_alert_rules") or [])
    _process_registrations(settings, rules)
    _process_documents(settings, rules)


def send_weekly_regulatory_digest() -> None:
    """Send a compact expiry and renewal-work digest to configured Regulatory recipients."""
    settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
    recipients = _default_recipients(settings)
    if not recipients:
        return
    registrations = frappe.get_all(
        PRODUCT_REGISTRATION,
        filters={"official_status": ["in", ["Active", "Expired"]]},
        fields=["name", "expiry_date", "renewal_status", "responsible_user"],
        order_by="expiry_date asc",
    )
    upcoming = [
        row
        for row in registrations
        if row.expiry_date
        and date_diff(cast(date, getdate(row.expiry_date)), cast(date, getdate(today()))) <= 30
    ]
    no_renewal = [row for row in upcoming if row.renewal_status in ("", "Not Started")]
    frappe.sendmail(
        recipients=recipients,
        subject=_("Weekly medical-device regulatory digest"),
        message=_(
            "Registrations expiring within 30 days: {0}. Registrations without renewal work: {1}."
        ).format(len(upcoming), len(no_renewal)),
    )


def _process_registrations(settings: Any, rules: list[Any]) -> None:
    for registration in frappe.get_all(
        PRODUCT_REGISTRATION,
        fields=["name", "expiry_date", "official_status", "responsible_user"],
    ):
        if not registration.expiry_date:
            continue
        days_remaining = date_diff(
            cast(date, getdate(registration.expiry_date)), cast(date, getdate(today()))
        )
        frappe.db.set_value(
            PRODUCT_REGISTRATION, registration.name, "days_to_expiry", days_remaining, update_modified=False
        )
        if days_remaining < 0 and registration.official_status == "Active":
            frappe.db.set_value(
                PRODUCT_REGISTRATION, registration.name, "official_status", "Expired", update_modified=False
            )
        _create_renewal_action(settings, registration, days_remaining)
        for rule in rules:
            if cast(int, rule.get("days_before_expiry") or -1) == days_remaining:
                _send_alert(
                    registration=registration.name,
                    document=None,
                    alert_kind=REGISTRATION_ALERT,
                    threshold=days_remaining,
                    rule=rule,
                    settings=settings,
                )
        if days_remaining < 0:
            regulatory.refresh_item_coverage_for_registration(registration.name)


def _process_documents(settings: Any, rules: list[Any]) -> None:
    for document in frappe.get_all(
        REGULATORY_DOCUMENT,
        filters={"expiry_date": ["is", "set"]},
        fields=["name", "registration", "expiry_date"],
    ):
        days_remaining = date_diff(cast(date, getdate(document.expiry_date)), cast(date, getdate(today())))
        for rule in rules:
            if cast(int, rule.get("days_before_expiry") or -1) == days_remaining:
                _send_alert(
                    registration=document.registration,
                    document=document.name,
                    alert_kind=DOCUMENT_ALERT,
                    threshold=days_remaining,
                    rule=rule,
                    settings=settings,
                )


def _create_renewal_action(settings: Any, registration: Any, days_remaining: int) -> None:
    if not settings.get("auto_create_renewal_action"):
        return
    threshold = cast(int, settings.get("renewal_start_days_before_expiry") or 0)
    if days_remaining > threshold:
        return
    if frappe.db.exists(
        "Medical Device Registration Action",
        {
            "registration": registration.name,
            "action_type": "Renewal",
            "current_stage": ["not in", ["Rejected", "Cancelled"]],
        },
    ):
        return
    frappe.get_doc(
        {
            "doctype": "Medical Device Registration Action",
            "registration": registration.name,
            "action_type": "Renewal",
            "current_stage": "Preparing",
            "assigned_to": registration.responsible_user or settings.get("default_regulatory_owner"),
            "remarks": _("Created automatically by expiry processing."),
        }
    ).insert(ignore_permissions=True)


def _send_alert(
    *, registration: str, document: str | None, alert_kind: str, threshold: int, rule: Any, settings: Any
) -> None:
    filters: dict[str, Any] = {
        "registration": registration,
        "alert_kind": alert_kind,
        "threshold_days": threshold,
    }
    if document:
        filters["regulatory_document"] = document
    if frappe.db.exists(ALERT_LOG, filters):
        return
    recipients = _rule_recipients(rule, settings, registration)
    alert = frappe.get_doc(
        {
            "doctype": ALERT_LOG,
            **filters,
            "severity": rule.get("severity"),
            "alerted_on": now_datetime(),
            "recipient_summary": ", ".join(recipients),
            "status": "Queued",
        }
    ).insert(ignore_permissions=True)
    if not recipients:
        alert.db_set("status", "No Recipients", update_modified=False)
        return
    try:
        frappe.sendmail(
            recipients=recipients,
            subject=_("Medical-device regulatory alert: {0}").format(registration),
            message=_("{0} threshold reached for registration {1}: {2} days.").format(
                alert_kind, registration, threshold
            ),
        )
        alert.db_set("status", "Sent", update_modified=False)
    except Exception:
        frappe.log_error(title="Medical-device regulatory alert delivery failed")
        alert.db_set("status", "Failed", update_modified=False)


def _rule_recipients(rule: Any, settings: Any, registration: str) -> list[str]:
    recipients: set[str] = set()
    recipient_user = cast(str, rule.get("recipient_user") or "")
    if recipient_user:
        recipients.add(recipient_user)
    recipient_role = cast(str, rule.get("recipient_role") or "")
    if recipient_role:
        recipients.update(get_users_with_role(recipient_role))
    responsible_user = cast(
        str, frappe.db.get_value(PRODUCT_REGISTRATION, registration, "responsible_user") or ""
    )
    if responsible_user:
        recipients.add(responsible_user)
    return sorted(recipients or set(_default_recipients(settings)))


def _default_recipients(settings: Any) -> list[str]:
    owner = cast(str, settings.get("default_regulatory_owner") or "")
    return [owner] if owner else get_users_with_role("Regulatory Approver")
