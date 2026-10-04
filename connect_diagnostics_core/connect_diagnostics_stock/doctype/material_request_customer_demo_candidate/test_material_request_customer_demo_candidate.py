# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase


class TestMaterialRequestCustomerDemoCandidate(IntegrationTestCase):
    def test_candidate_is_editable_child_row_with_required_links(self) -> None:
        meta = frappe.get_meta("Material Request Customer Demo Candidate")

        self.assertTrue(meta.istable)
        self.assertTrue(meta.editable_grid)
        self.assertFalse(meta.permissions)
        self.assertEqual(meta.get_field("material_request_item").options, "Material Request Item")
        self.assertTrue(meta.get_field("material_request_item").reqd)
        self.assertEqual(meta.get_field("asset").options, "Asset")
        self.assertTrue(meta.get_field("asset").reqd)
