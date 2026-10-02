# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from math import inf, nan
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.frappe import approval_controls


class TestCriticalDigest(UnitTestCase):
    def test_nonfinite_floats_fail_closed_at_any_depth(self) -> None:
        for value in (nan, inf, -inf):
            for payload in ({"value": value}, {"nested": [value]}):
                with self.subTest(value=value, payload=payload), self.assertRaises(frappe.ValidationError):
                    approval_controls.critical_digest(payload)

    def test_finite_floats_keep_their_canonical_values(self) -> None:
        for value in (0.0, -0.0, 5e-324, -5e-324, 1.7976931348623157e308, -1.7976931348623157e308):
            with self.subTest(value=value):
                self.assertIs(approval_controls._canonical_value(value), value)
        self.assertNotEqual(
            approval_controls.critical_digest({"value": 0.0}),
            approval_controls.critical_digest({"value": -0.0}),
        )

    def test_mapping_order_and_nested_sequences_are_stable(self) -> None:
        first = {"b": [1, "สอง"], "a": {"x": True}}
        second = {"a": {"x": True}, "b": (1, "สอง")}
        self.assertEqual(approval_controls.critical_digest(first), approval_controls.critical_digest(second))

    def test_tagged_scalar_does_not_collide_with_string(self) -> None:
        self.assertNotEqual(
            approval_controls.critical_digest({"value": "2026-01-01"}),
            approval_controls.critical_digest({"value": datetime(2026, 1, 1)}),
        )

    def test_tagged_temporal_and_decimal_values_preserve_type_and_precision(self) -> None:
        values = [
            {"value": Decimal("1.00")},
            {"value": Decimal("1.0")},
            {"value": date(2026, 1, 1)},
            {"value": datetime(2026, 1, 1)},
            {"value": time(1, 2, 3)},
        ]
        digests = {approval_controls.critical_digest(value) for value in values}
        self.assertEqual(len(digests), len(values))

    def test_scalar_types_and_sequence_order_are_significant(self) -> None:
        self.assertNotEqual(
            approval_controls.critical_digest({"value": 1}),
            approval_controls.critical_digest({"value": "1"}),
        )
        self.assertNotEqual(
            approval_controls.critical_digest({"value": [1, 2]}),
            approval_controls.critical_digest({"value": [2, 1]}),
        )

    def test_unsupported_values_fail_closed(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            approval_controls.critical_digest({"value": {1, 2}})


class TestApprovalControls(UnitTestCase):
    def test_native_time_intervals_are_lossless_and_deterministic(self) -> None:
        for value, exact in (
            (timedelta(), "0"),
            (timedelta(hours=1, microseconds=1), "3600000001"),
            (timedelta(microseconds=-1), "-1"),
            (timedelta(days=999999999, microseconds=999999), "86399999913600999999"),
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    approval_controls._canonical_value(value),
                    {"__approval_type__": "timedelta", "value": exact},
                )
        self.assertEqual(
            approval_controls.critical_digest({"value": timedelta(days=1, seconds=-1)}),
            approval_controls.critical_digest({"value": timedelta(seconds=86399)}),
        )

    def test_time_interval_digest_preserves_type_and_microsecond_differences(self) -> None:
        values = (timedelta(hours=1), timedelta(hours=1, microseconds=1), time(1), "3600000000", 3600000000)
        self.assertEqual(
            len({approval_controls.critical_digest({"value": value}) for value in values}), len(values)
        )

    def tearDown(self) -> None:
        if hasattr(frappe.local, approval_controls._APPROVAL_GRANTS_KEY):
            delattr(frappe.local, approval_controls._APPROVAL_GRANTS_KEY)
        super().tearDown()

    def _identity_mocks(self):
        def exists(doctype, name):
            return doctype == "User" and name in {"maker@example.com", "actor@example.com"}

        def get_value(doctype, filters, fieldname, **kwargs):
            if doctype == "User":
                return 1 if filters in {"maker@example.com", "actor@example.com"} else None
            if doctype == "Employee":
                if isinstance(filters, dict) and filters.get("name") == "EMP-001":
                    return {"name": "EMP-001", "user_id": "actor@example.com"}
                return None
            return None

        def get_all(doctype, **kwargs):
            return [
                {
                    "name": "EMP-001",
                    "employee_name": "Actor",
                    "user_id": "actor@example.com",
                    "approval_signature": "sig",
                }
            ]

        return patch.multiple(
            frappe.db,
            exists=exists,
            get_value=get_value,
        ), patch("frappe.get_all", side_effect=get_all)

    def test_resolve_user_accepts_enabled_user_and_employee_alias(self) -> None:
        with self._identity_mocks()[0], self._identity_mocks()[1]:
            self.assertEqual(approval_controls.resolve_user("actor@example.com"), "actor@example.com")

    def test_resolve_user_accepts_exact_employee_alias(self) -> None:
        with self._identity_mocks()[0], self._identity_mocks()[1]:
            self.assertEqual(approval_controls.resolve_user("EMP-001"), "actor@example.com")

    def test_digest_rejects_invalid_root_and_values(self) -> None:
        for payload in ([1], {1: "bad"}, {"value": nan}, {"value": inf}, {"value": object()}):
            with self.subTest(payload=payload), self.assertRaises(frappe.ValidationError):
                approval_controls.critical_digest(payload)  # ty: ignore[invalid-argument-type] - intentionally invalid root input

    def test_distinct_actors_accepts_mixed_aliases(self) -> None:
        with self._identity_mocks()[0], self._identity_mocks()[1]:
            approval_controls.require_distinct_actors("maker@example.com", "EMP-001", ())

    def test_distinct_actor_matrix_canonicalizes_user_employee_aliases(self) -> None:
        users = {"maker@example.com", "actor@example.com", "prior@example.com"}
        employees = {
            "EMP-ACTOR": {"name": "EMP-ACTOR", "user_id": "actor@example.com"},
            "EMP-PRIOR": {"name": "EMP-PRIOR", "user_id": "prior@example.com"},
        }

        def exists(doctype, name):
            return doctype == "User" and name in users

        def get_value(doctype, filters, fieldname, **kwargs):
            if doctype == "User":
                return 1 if filters in users else None
            if doctype == "Employee" and isinstance(filters, dict):
                return employees.get(filters.get("name"))
            return None

        def get_all(doctype, filters, fields, limit):
            user = filters["user_id"]
            return [
                {
                    "name": employee["name"],
                    "employee_name": employee["name"],
                    "user_id": user,
                    "approval_signature": "sig",
                }
                for employee in employees.values()
                if employee["user_id"] == user
            ][:limit]

        environment = (
            patch.object(frappe.db, "exists", side_effect=exists),
            patch.object(frappe.db, "get_value", side_effect=get_value),
            patch("frappe.get_all", side_effect=get_all),
        )
        with environment[0], environment[1], environment[2]:
            approval_controls.require_distinct_actors(
                "maker@example.com", "EMP-ACTOR", ("prior@example.com",)
            )
            for previous in (
                ("prior@example.com", "EMP-PRIOR"),
                ("maker@example.com",),
                ("EMP-ACTOR",),
                ("",),
            ):
                with self.subTest(previous=previous), self.assertRaises(frappe.ValidationError):
                    approval_controls.require_distinct_actors("maker@example.com", "EMP-ACTOR", previous)

    def test_identity_failures_are_fail_closed(self) -> None:
        def exists(doctype, name):
            return doctype == "User" and name in {"disabled@example.com", "same"}

        def get_value(doctype, filters, fieldname, **kwargs):
            if doctype == "User":
                return 0 if filters == "disabled@example.com" else None
            if doctype == "Employee":
                if isinstance(filters, dict) and filters.get("name") == "inactive":
                    return None
                if isinstance(filters, dict) and filters.get("name") == "unlinked":
                    return {"name": "unlinked", "user_id": ""}
                if isinstance(filters, dict) and filters.get("name") == "same":
                    return {"name": "same", "user_id": "other@example.com"}
            return None

        with (
            patch.object(frappe.db, "exists", side_effect=exists),
            patch.object(frappe.db, "get_value", side_effect=get_value),
            patch("frappe.get_all", return_value=[]),
        ):
            for identity in ("disabled@example.com", "inactive", "unlinked", "same"):
                with self.subTest(identity=identity), self.assertRaises(frappe.ValidationError):
                    approval_controls.resolve_user(identity)

    def test_multiple_active_employees_are_ambiguous(self) -> None:
        def get_value(doctype, filters, fieldname, **kwargs):
            return 1 if doctype == "User" else None

        with (
            patch.object(frappe.db, "exists", return_value=True),
            patch.object(frappe.db, "get_value", side_effect=get_value),
            patch(
                "frappe.get_all",
                return_value=[{"name": "EMP-1"}, {"name": "EMP-2"}],
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            approval_controls.resolve_user("actor@example.com")

    def test_distinct_actors_reject_alias_reuse(self) -> None:
        with self._identity_mocks()[0], self._identity_mocks()[1]:
            with self.assertRaises(frappe.ValidationError):
                approval_controls.require_distinct_actors("maker@example.com", "maker@example.com", ())

    def test_capture_rechecks_permission_and_returns_frozen_snapshot(self) -> None:
        doc = Document({"doctype": "Asset Movement"})
        now = datetime(2026, 9, 26, 10, 30, 0)
        with (
            self._identity_mocks()[0],
            self._identity_mocks()[1],
            patch.object(frappe, "has_permission", return_value=True),
            patch.dict(frappe.session, {"user": "actor@example.com"}),
            patch.object(frappe.utils, "now_datetime", return_value=now),
        ):
            snapshot = approval_controls.capture_signed_approval_actor(doc, "maker@example.com")
        self.assertEqual(snapshot.user, "actor@example.com")
        self.assertEqual(snapshot.employee, "EMP-001")
        self.assertEqual(snapshot.acted_at, now)
        self.assertEqual(snapshot.signature, "sig")
        with self.assertRaises(AttributeError):
            snapshot.signature = "changed"  # ty: ignore[invalid-assignment] - prove frozen snapshot rejects mutation

    def test_capture_stops_before_employee_data_when_permission_denied(self) -> None:
        doc = Document({"doctype": "Asset Movement"})
        with (
            patch.object(frappe, "has_permission", return_value=False) as permission,
            patch("frappe.get_all", side_effect=AssertionError("Employee query must not run")),
            patch.dict(frappe.session, {"user": "actor@example.com"}),
        ):
            with self.assertRaises(frappe.PermissionError):
                approval_controls.capture_signed_approval_actor(doc, "maker@example.com")
        permission.assert_called_once_with("Asset Movement", ptype="write", doc=doc, user="actor@example.com")

    def test_capture_preserves_nonempty_signature_verbatim(self) -> None:
        doc = Document({"doctype": "Asset Movement"})
        with (
            self._identity_mocks()[0],
            patch.object(frappe, "has_permission", return_value=True),
            patch.dict(frappe.session, {"user": "actor@example.com"}),
            patch(
                "frappe.get_all",
                return_value=[
                    {
                        "name": "EMP-001",
                        "employee_name": "Actor",
                        "user_id": "actor@example.com",
                        "approval_signature": "  signed exactly  ",
                    }
                ],
            ),
        ):
            snapshot = approval_controls.capture_signed_approval_actor(doc, "maker@example.com")
        self.assertEqual(snapshot.signature, "  signed exactly  ")

    def test_capture_rejects_whitespace_only_signature(self) -> None:
        doc = Document({"doctype": "Asset Movement"})
        with (
            self._identity_mocks()[0],
            patch.object(frappe, "has_permission", return_value=True),
            patch.dict(frappe.session, {"user": "actor@example.com"}),
            patch(
                "frappe.get_all",
                return_value=[
                    {
                        "name": "EMP-001",
                        "employee_name": "Actor",
                        "user_id": "actor@example.com",
                        "approval_signature": "   ",
                    }
                ],
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                approval_controls.capture_signed_approval_actor(doc, "maker@example.com")

    def test_capture_rejects_missing_duplicate_and_unsigned_employees(self) -> None:
        doc = Document({"doctype": "Asset Movement"})
        employee = {"name": "EMP-001", "employee_name": "Actor", "user_id": "actor@example.com"}
        for rows in ([], [employee, employee], [{**employee, "approval_signature": ""}]):
            with (
                self.subTest(rows=rows),
                self._identity_mocks()[0],
                patch.object(frappe, "has_permission", return_value=True),
                patch.dict(frappe.session, {"user": "actor@example.com"}),
                patch("frappe.get_all", return_value=rows),
                self.assertRaises(frappe.ValidationError),
            ):
                approval_controls.capture_signed_approval_actor(doc, "maker@example.com")

    def test_interactive_actor_mints_one_use_exact_document_grant(self) -> None:
        doc = Document({"doctype": "Asset Movement", "name": "AM-1"})
        with (
            self._identity_mocks()[0],
            self._identity_mocks()[1],
            patch.object(frappe, "has_permission", return_value=True),
            patch.object(frappe, "get_roles", return_value=["Stock Manager"]),
            patch.dict(frappe.session, {"user": "actor@example.com"}),
            patch.object(frappe.local, "request", object(), create=True),
        ):
            snapshot = approval_controls.authorize_approval_field_write(
                doc,
                "asset_movement",
                "Review Asset Movement",
                ("Stock Manager",),
                "maker@example.com",
            )
            self.assertEqual(snapshot.user, "actor@example.com")
            approval_controls.consume_approval_field_grant(
                doc,
                "asset_movement",
                "Review Asset Movement",
            )
            with self.assertRaises(frappe.ValidationError):
                approval_controls.consume_approval_field_grant(
                    doc,
                    "asset_movement",
                    "Review Asset Movement",
                )

    def test_grant_rejects_cross_document_route_action_and_forged_lookalike(self) -> None:
        doc = Document({"doctype": "Asset Movement", "name": "AM-1"})
        lookalike = Document({"doctype": "Asset Movement", "name": "AM-1"})
        with (
            self._identity_mocks()[0],
            self._identity_mocks()[1],
            patch.object(frappe, "has_permission", return_value=True),
            patch.object(frappe, "get_roles", return_value=["Stock Manager"]),
            patch.dict(frappe.session, {"user": "actor@example.com"}),
            patch.object(frappe.local, "request", object(), create=True),
        ):
            approval_controls.authorize_approval_field_write(
                doc,
                "asset_movement",
                "Review Asset Movement",
                ("Stock Manager",),
                "maker@example.com",
            )
            invalid = (
                (lookalike, "asset_movement", "Review Asset Movement"),
                (doc, "payment_entry", "Review Asset Movement"),
                (doc, "asset_movement", "Approve Asset Movement"),
            )
            for candidate, route, action in invalid:
                with self.subTest(route=route, action=action), self.assertRaises(frappe.ValidationError):
                    approval_controls.consume_approval_field_grant(candidate, route, action)
            approval_controls.consume_approval_field_grant(
                doc,
                "asset_movement",
                "Review Asset Movement",
            )

    def test_interactive_actor_rejects_noninteractive_and_unauthorized_users(self) -> None:
        doc = Document({"doctype": "Asset Movement", "name": "AM-1"})
        for user, roles, request in (
            ("Guest", ["Stock Manager"], object()),
            ("Administrator", ["Stock Manager"], object()),
            ("actor@example.com", ["Stock User"], object()),
            ("actor@example.com", ["Stock Manager"], None),
        ):
            with (
                self.subTest(user=user, roles=roles, request=request),
                self._identity_mocks()[0],
                self._identity_mocks()[1],
                patch.object(frappe, "has_permission", return_value=True),
                patch.object(frappe, "get_roles", return_value=roles),
                patch.dict(frappe.session, {"user": user}),
                patch.object(frappe.local, "request", request, create=True),
                self.assertRaises(frappe.ValidationError),
            ):
                approval_controls.authorize_approval_field_write(
                    doc,
                    "asset_movement",
                    "Review Asset Movement",
                    ("Stock Manager",),
                    "maker@example.com",
                )

    def test_permission_revocation_does_not_mint_a_grant(self) -> None:
        doc = Document({"doctype": "Asset Movement", "name": "AM-1"})
        with (
            self._identity_mocks()[0],
            self._identity_mocks()[1],
            patch.object(frappe, "has_permission", return_value=False),
            patch.object(frappe, "get_roles", return_value=["Stock Manager"]),
            patch.dict(frappe.session, {"user": "actor@example.com"}),
            patch.object(frappe.local, "request", object(), create=True),
            self.assertRaises(frappe.PermissionError),
        ):
            approval_controls.authorize_approval_field_write(
                doc,
                "asset_movement",
                "Review Asset Movement",
                ("Stock Manager",),
                "maker@example.com",
            )
        with self.assertRaises(frappe.ValidationError):
            approval_controls.consume_approval_field_grant(
                doc,
                "asset_movement",
                "Review Asset Movement",
            )

    def test_maker_action_allows_self_without_employee_signature(self) -> None:
        doc = Document({"doctype": "Asset Movement", "name": "AM-1"})

        def get_value(doctype, filters, fieldname, **kwargs):
            return 1 if doctype == "User" and filters == "maker@example.com" else None

        with (
            patch.object(frappe.db, "exists", return_value=True),
            patch.object(frappe.db, "get_value", side_effect=get_value),
            patch("frappe.get_all", return_value=[]),
            patch.object(frappe, "has_permission", return_value=True),
            patch.object(frappe, "get_roles", return_value=["Stock User"]),
            patch.dict(frappe.session, {"user": "maker@example.com"}),
            patch.object(frappe.local, "request", object(), create=True),
        ):
            user = approval_controls.authorize_workflow_field_write(
                doc,
                "asset_movement",
                "Send Asset Movement for Review",
                ("Stock User",),
            )
            self.assertEqual(user, "maker@example.com")
            approval_controls.consume_approval_field_grant(
                doc,
                "asset_movement",
                "Send Asset Movement for Review",
            )

    def test_nonapproval_action_still_rechecks_role_permission_and_request(self) -> None:
        doc = Document({"doctype": "Asset Movement", "name": "AM-1"})
        cases = (
            (["Stock Manager"], True, object(), frappe.ValidationError),
            (["Stock User"], False, object(), frappe.PermissionError),
            (["Stock User"], True, None, frappe.ValidationError),
        )
        for roles, permitted, request, error in cases:
            with (
                self.subTest(roles=roles, permitted=permitted, request=request),
                patch.object(frappe, "get_roles", return_value=roles),
                patch.object(frappe, "has_permission", return_value=permitted),
                patch.dict(frappe.session, {"user": "maker@example.com"}),
                patch.object(frappe.local, "request", request, create=True),
                self.assertRaises(error),
            ):
                approval_controls.authorize_workflow_field_write(
                    doc,
                    "asset_movement",
                    "Send Asset Movement for Review",
                    ("Stock User",),
                )

    def test_terminal_labels_require_native_status(self) -> None:
        doc = Document({"doctype": "Stock Entry", "name": "STE-1"})
        for state, status in (("Stock Transfer Submitted", 0), ("Stock Transfer Cancelled", 1)):
            doc.set("workflow_state", state)
            doc.docstatus = status
            with self.subTest(state=state), self.assertRaises(frappe.ValidationError):
                approval_controls.require_native_terminal_state(
                    doc, "Stock Transfer Submitted", "Stock Transfer Cancelled"
                )
        for state, status in (("Stock Transfer Submitted", 1), ("Stock Transfer Cancelled", 2)):
            doc.set("workflow_state", state)
            doc.docstatus = status
            approval_controls.require_native_terminal_state(
                doc, "Stock Transfer Submitted", "Stock Transfer Cancelled"
            )

    def test_submitted_update_requires_locked_persisted_previous_and_current_state(self) -> None:
        state = "Stock Transfer Submitted"
        doc = Document({"doctype": "Stock Entry", "name": "STE-1", "workflow_state": state, "docstatus": 1})
        previous = Document(
            {"doctype": "Stock Entry", "name": "STE-1", "workflow_state": state, "docstatus": 1}
        )
        row = frappe._dict(workflow_state=state, docstatus=1)
        with (
            patch.object(doc, "get_doc_before_save", return_value=previous),
            patch.object(frappe.db, "get_value", return_value=row) as get_value,
        ):
            approval_controls.require_locked_submitted_update(doc, state)
            self.assertEqual(get_value.call_args.kwargs["for_update"], True)
            for changed in (doc, previous, row):
                if isinstance(changed, Document):
                    changed.set("workflow_state", "Stock Transfer Cancelled")
                else:
                    changed["workflow_state"] = "Stock Transfer Cancelled"
                with self.subTest(changed=type(changed).__name__), self.assertRaises(frappe.ValidationError):
                    approval_controls.require_locked_submitted_update(doc, state)
                if isinstance(changed, Document):
                    changed.set("workflow_state", state)
                else:
                    changed["workflow_state"] = state
            with patch.object(doc, "get_doc_before_save", return_value=None):
                with self.assertRaises(frappe.ValidationError):
                    approval_controls.require_locked_submitted_update(doc, state)
