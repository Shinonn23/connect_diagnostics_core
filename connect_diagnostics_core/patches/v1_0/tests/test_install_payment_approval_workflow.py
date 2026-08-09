# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import payment_approval


class TestPaymentApprovalSetup(UnitTestCase):
    def test_only_active_payment_request_fields_are_managed(self) -> None:
        fields = {field["fieldname"] for field in payment_approval.CUSTOM_FIELDS["Payment Request"]}

        self.assertEqual(fields, {"payment_approval_state", "base_grand_total"})

    def test_roles_match_the_two_stage_approval_flow(self) -> None:
        self.assertEqual(
            payment_approval.MANAGED_ROLES,
            (payment_approval.EXECUTIVE_APPROVER_ROLE, payment_approval.AP_REVIEWER_ROLE),
        )
