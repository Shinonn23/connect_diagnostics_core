# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import cast
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.frappe import approval_controls


class TestApprovalControls(UnitTestCase):
    def test_critical_digest_is_order_stable_and_value_sensitive(self) -> None:
        first = approval_controls.critical_digest({"company": "A", "items": [{"qty": 1}]})
        reordered = approval_controls.critical_digest({"items": [{"qty": 1}], "company": "A"})
        changed = approval_controls.critical_digest({"company": "A", "items": [{"qty": 2}]})

        self.assertEqual(first, reordered)
        self.assertNotEqual(first, changed)

    def test_critical_digest_normalizes_numeric_representations(self) -> None:
        integer = approval_controls.critical_digest({"amount": 1})
        floating = approval_controls.critical_digest({"amount": 1.0})
        decimal = approval_controls.critical_digest({"amount": Decimal("1.000")})

        self.assertEqual(integer, floating)
        self.assertEqual(integer, decimal)

    def test_critical_digest_preserves_business_value_types(self) -> None:
        payload = {
            "posting_date": date(2026, 9, 26),
            "approved_at": datetime(2026, 9, 26, 12, 30, 45, 123456),
            "transaction_time": timedelta(hours=12, minutes=30, microseconds=123456),
            "cutoff_time": time(16, 45, 30, 123456),
            "enabled": False,
            "missing": None,
            "empty": "",
            "supplier": "SUP-0001",
        }

        digest = approval_controls.critical_digest(payload)

        self.assertEqual(digest, approval_controls.critical_digest(dict(reversed(payload.items()))))
        self.assertNotEqual(digest, approval_controls.critical_digest({**payload, "empty": None}))
        self.assertNotEqual(
            digest,
            approval_controls.critical_digest({**payload, "posting_date": "2026-09-26"}),
        )

    def test_critical_digest_rejects_unsupported_values(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            approval_controls.critical_digest({"unsupported": object()})

    def test_employee_and_user_identities_are_compared_canonically(self) -> None:
        def exists(doctype: str, name: str) -> bool:
            return doctype == "User" and name.endswith("@example.com")

        with (
            patch.object(approval_controls.frappe.db, "exists", side_effect=exists),
            patch.object(
                approval_controls.frappe.db,
                "get_value",
                side_effect=lambda doctype, name, field: {
                    "EMP-MAKER": "maker@example.com",
                    "EMP-REVIEWER": "reviewer@example.com",
                }.get(name),
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                approval_controls.require_distinct_actors(
                    "EMP-MAKER",
                    "maker@example.com",
                )
            with self.assertRaises(frappe.ValidationError):
                approval_controls.require_distinct_actors(
                    "maker@example.com",
                    "reviewer@example.com",
                    ("EMP-REVIEWER",),
                )
            approval_controls.require_distinct_actors(
                "maker@example.com",
                "approver@example.com",
                ("reviewer@example.com",),
            )

    def test_permission_revocation_fails_closed(self) -> None:
        doc = frappe._dict(doctype="Purchase Order")
        with (
            patch.object(approval_controls.frappe, "has_permission", return_value=False),
            self.assertRaises(frappe.PermissionError),
        ):
            approval_controls.require_permission(cast(Document, doc))
