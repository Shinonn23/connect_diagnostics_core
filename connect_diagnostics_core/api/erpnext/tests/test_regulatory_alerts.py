# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import regulatory_alerts


class TestRegulatoryAlerts(UnitTestCase):
    def test_rule_recipients_prefers_user_and_role_over_default(self) -> None:
        rule = {"recipient_user": "owner@example.com", "recipient_role": "Regulatory Operator"}
        settings = {"default_regulatory_owner": "fallback@example.com"}
        with (
            patch.object(regulatory_alerts, "get_users_with_role", return_value=["role@example.com"]),
            patch.object(regulatory_alerts.frappe.db, "get_value", return_value=""),
        ):
            recipients = regulatory_alerts._rule_recipients(rule, settings, "REG-1")

        self.assertEqual(recipients, ["owner@example.com", "role@example.com"])

    def test_renewal_creation_is_idempotent(self) -> None:
        settings = {"auto_create_renewal_action": 1, "renewal_start_days_before_expiry": 365}
        registration = type("Registration", (), {"name": "REG-1", "responsible_user": "owner@example.com"})()
        with patch.object(regulatory_alerts.frappe.db, "exists", return_value=True), patch.object(
            regulatory_alerts.frappe, "get_doc"
        ) as get_doc:
            regulatory_alerts._create_renewal_action(settings, registration, 30)

        get_doc.assert_not_called()
