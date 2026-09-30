# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import payment_entry_approval_poc as poc


class FakeDocument:
    doctype = "Payment Entry"
    name = "PE-POC-0001"

    def __init__(self, **values: Any) -> None:
        self.values = values
        self.flags = frappe._dict()
        self.comments: list[tuple[str, str]] = []

    def get(self, fieldname: str, default: Any = None) -> Any:
        return self.values.get(fieldname, default)

    def set(self, fieldname: str, value: Any) -> None:
        self.values[fieldname] = value

    def add_comment(self, comment_type: str, text: str) -> None:
        self.comments.append((comment_type, text))


class TestPaymentEntryApprovalPOC(UnitTestCase):
    def test_activation_is_fail_closed_and_requires_integer_one(self) -> None:
        original_site = frappe.local.site
        original_flag = frappe.conf.get(poc.ENABLED_FLAG)
        had_flag = poc.ENABLED_FLAG in frappe.conf
        try:
            frappe.local.site = "local.test"
            for disabled_value in (None, 0, False, True, "1"):
                frappe.conf[poc.ENABLED_FLAG] = disabled_value
                self.assertFalse(poc.enabled())
            frappe.conf[poc.ENABLED_FLAG] = 1
            self.assertTrue(poc.enabled())
            frappe.local.site = "local"
            self.assertFalse(poc.enabled())
        finally:
            frappe.local.site = original_site
            if had_flag:
                frappe.conf[poc.ENABLED_FLAG] = original_flag
            else:
                frappe.conf.pop(poc.ENABLED_FLAG, None)

    def test_digest_is_stable_and_changes_for_posting_field(self) -> None:
        doc = {
            "payment_type": "Pay",
            "paid_amount": 10,
            "references": [{"name": "INV-1", "idx": 1, "allocated_amount": 10}],
        }
        first = poc.posting_digest(doc)
        self.assertEqual(first, poc.posting_digest(doc))
        doc["paid_amount"] = 11
        self.assertNotEqual(first, poc.posting_digest(doc))

    def test_digest_canonicalizes_child_documents(self) -> None:
        class Child:
            def as_dict(self) -> dict[str, object]:
                return {
                    "name": "row-1",
                    "idx": 1,
                    "parent": "PE-1",
                    "item_code": "ITEM-1",
                    "allocated_amount": 2,
                }

        first = {"references": [Child()]}
        second = {
            "references": [
                {
                    "name": "another",
                    "idx": 9,
                    "parent": "PE-2",
                    "item_code": "ITEM-1",
                    "allocated_amount": 2,
                }
            ]
        }
        self.assertEqual(poc.posting_digest(first), poc.posting_digest(second))

    def test_hmac_token_rejects_tampering(self) -> None:
        payload = {"version": 1, "name": "PE-1"}
        with patch.object(poc, "_site_signing_key", return_value=b"test-key"):
            token = poc._encode_token(payload)
            self.assertEqual(poc._decode_token(token), payload)
            encoded, signature = token.split(".", 1)
            tampered = f"{encoded[:-1]}A.{signature}"
            with self.assertRaises(frappe.ValidationError):
                poc._decode_token(tampered)

    def test_direct_state_spoof_is_rejected(self) -> None:
        doc = FakeDocument(payment_type="Pay", workflow_state=poc.APPROVED)
        previous = frappe._dict(workflow_state=poc.DRAFT)
        with (
            patch.object(poc, "enabled", return_value=True),
            patch.object(poc.frappe.db, "get_value", return_value=previous),
            self.assertRaises(frappe.ValidationError),
        ):
            poc.validate(cast(Document, doc))

    def test_receive_and_internal_transfer_are_rejected_when_enabled(self) -> None:
        for payment_type in ("Receive", "Internal Transfer"):
            doc = FakeDocument(payment_type=payment_type)
            with (
                patch.object(poc, "enabled", return_value=True),
                self.assertRaises(frappe.ValidationError),
            ):
                poc.validate(cast(Document, doc))

    def test_unconfigured_site_is_inert(self) -> None:
        doc = FakeDocument(payment_type="Receive")
        with patch.object(poc, "enabled", return_value=False), patch.object(poc.frappe, "throw") as throw:
            poc.validate(cast(Document, doc))
            throw.assert_not_called()
