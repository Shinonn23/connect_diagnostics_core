# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase


class TestCustomerDemoAssetClaim(IntegrationTestCase):
    def test_claim_is_internal_and_asset_is_database_unique(self) -> None:
        meta = frappe.get_meta("Customer Demo Asset Claim")

        self.assertFalse(meta.permissions)
        self.assertEqual(meta.autoname, "field:asset")
        self.assertEqual(meta.get_field("asset").options, "Asset")
        self.assertTrue(meta.get_field("asset").reqd)
        self.assertTrue(meta.get_field("asset").unique)
        self.assertIsNotNone(
            frappe.db.get_column_index("tabCustomer Demo Asset Claim", "asset", unique=True)
        )
        self.assertEqual(meta.get_field("material_request").options, "Material Request")
        self.assertTrue(meta.get_field("material_request").reqd)
        self.assertEqual(meta.get_field("material_request_item").options, "Material Request Item")
        self.assertTrue(meta.get_field("material_request_item").reqd)
