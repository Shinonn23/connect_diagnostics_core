# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Tests for code-managed Regulatory setup metadata."""

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import regulatory


class TestRegulatorySetup(UnitTestCase):
    def test_superseded_workflow_state_uses_a_supported_style(self) -> None:
        self.assertEqual(regulatory.WORKFLOW_STATES["Registration Superseded"], "Inverse")
