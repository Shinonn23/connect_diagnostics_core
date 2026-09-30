# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.frappe.approval_controls import critical_digest


class TestApprovalControls(UnitTestCase):
    def test_digest_is_order_stable_and_value_sensitive(self) -> None:
        self.assertEqual(critical_digest({"a": 1, "b": 2}), critical_digest({"b": 2, "a": 1}))
        self.assertNotEqual(critical_digest({"a": 1}), critical_digest({"a": 2}))
