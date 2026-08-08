# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import (
    move_quotation_signatory_to_document as move_patch,
)
from connect_diagnostics_core.patches.v1_0 import (
    rollback_move_quotation_signatory_to_document as rollback_patch,
)


class FakeMeta:
    """Stand-in for the Customer meta the patch checks before backfilling."""

    def __init__(self, fields: set[str]) -> None:
        self._fields = fields

    def has_field(self, fieldname: str) -> bool:
        return fieldname in self._fields


CUSTOMER_META_WITH_VALIDITY = FakeMeta({"override_quotation_validity_text", "quotation_custom_validity_text"})
CUSTOMER_META_AFTER_MIGRATION = FakeMeta(set())


def _get_all(
    records: dict[str, list[list[dict[str, Any]]]],
) -> Callable[..., list[dict[str, Any]]]:
    """Return a ``frappe.get_all`` stub answering each doctype's calls in order."""
    queued = {doctype: list(responses) for doctype, responses in records.items()}

    def dispatch(doctype: str, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        responses = queued.get(doctype)
        return responses.pop(0) if responses else []

    return dispatch


class TestMoveQuotationSignatoryToDocument(UnitTestCase):
    @patch.object(move_patch.frappe, "clear_cache")
    @patch.object(move_patch, "delete_custom_fields")
    @patch.object(move_patch, "create_custom_fields")
    @patch.object(move_patch.frappe, "get_meta", return_value=CUSTOMER_META_AFTER_MIGRATION)
    @patch.object(move_patch.frappe.db, "bulk_update")
    @patch.object(move_patch.frappe, "get_all")
    def test_execute_backfills_the_representative_from_the_customer_sales_team(
        self,
        mocked_get_all: MagicMock,
        mocked_bulk_update: MagicMock,
        _mocked_get_meta: MagicMock,
        mocked_create: MagicMock,
        _mocked_delete: MagicMock,
        _mocked_clear_cache: MagicMock,
    ) -> None:
        mocked_get_all.side_effect = _get_all(
            {
                "Quotation": [[{"name": "QTN-0001", "party_name": "CUST-0001"}]],
                "Sales Team": [[{"parent": "CUST-0001", "sales_person": "Narin"}]],
                "Sales Person": [[{"name": "Narin", "employee": "EMP-0001"}]],
            }
        )

        move_patch.execute()

        mocked_create.assert_called_once()
        mocked_bulk_update.assert_called_once_with(
            "Quotation",
            {"QTN-0001": {"sales_representative_employee": "EMP-0001"}},
            update_modified=False,
        )

    @patch.object(move_patch.frappe, "clear_cache")
    @patch.object(move_patch, "delete_custom_fields")
    @patch.object(move_patch, "create_custom_fields")
    @patch.object(move_patch.frappe, "get_meta", return_value=CUSTOMER_META_WITH_VALIDITY)
    @patch.object(move_patch.frappe.db, "bulk_update")
    @patch.object(move_patch.frappe, "get_all")
    def test_execute_copies_the_customer_validity_override_onto_the_quotation(
        self,
        mocked_get_all: MagicMock,
        mocked_bulk_update: MagicMock,
        _mocked_get_meta: MagicMock,
        _mocked_create: MagicMock,
        _mocked_delete: MagicMock,
        _mocked_clear_cache: MagicMock,
    ) -> None:
        mocked_get_all.side_effect = _get_all(
            {
                "Quotation": [[], [{"name": "QTN-0002", "party_name": "CUST-0002"}]],
                "Customer": [
                    [
                        {
                            "name": "CUST-0002",
                            "override_quotation_validity_text": 1,
                            "quotation_custom_validity_text": "1 ปี นับจากวันที่อนุมัติวัสดุการแพทย์เข้า",
                        }
                    ]
                ],
            }
        )

        move_patch.execute()

        mocked_bulk_update.assert_called_once_with(
            "Quotation",
            {
                "QTN-0002": {
                    "override_quotation_validity_text": 1,
                    "quotation_custom_validity_text": "1 ปี นับจากวันที่อนุมัติวัสดุการแพทย์เข้า",
                }
            },
            update_modified=False,
        )

    @patch.object(move_patch.frappe, "clear_cache")
    @patch.object(move_patch, "delete_custom_fields")
    @patch.object(move_patch, "create_custom_fields")
    @patch.object(move_patch.frappe, "get_meta", return_value=CUSTOMER_META_AFTER_MIGRATION)
    @patch.object(move_patch.frappe.db, "bulk_update")
    @patch.object(move_patch.frappe, "get_all", return_value=[])
    def test_execute_retires_the_authorized_signatory_and_customer_validity_fields(
        self,
        _mocked_get_all: MagicMock,
        mocked_bulk_update: MagicMock,
        _mocked_get_meta: MagicMock,
        _mocked_create: MagicMock,
        mocked_delete: MagicMock,
        _mocked_clear_cache: MagicMock,
    ) -> None:
        move_patch.execute()

        mocked_bulk_update.assert_not_called()
        mocked_delete.assert_called_once_with(
            {
                "Company": ["quotation_authorized_signatory_employee"],
                "Quotation": ["quotation_authorized_signatory_employee"],
                "Customer": [
                    "override_quotation_validity_text",
                    "quotation_custom_validity_text",
                ],
            },
            bypass_hooks=True,
        )

    @patch.object(move_patch.frappe, "get_meta", return_value=CUSTOMER_META_AFTER_MIGRATION)
    @patch.object(move_patch.frappe.db, "bulk_update")
    @patch.object(move_patch.frappe, "get_all")
    def test_validity_backfill_is_a_no_op_once_the_customer_fields_are_gone(
        self,
        mocked_get_all: MagicMock,
        mocked_bulk_update: MagicMock,
        _mocked_get_meta: MagicMock,
    ) -> None:
        move_patch._backfill_validity_text()

        mocked_get_all.assert_not_called()
        mocked_bulk_update.assert_not_called()

    @patch.object(move_patch.frappe, "get_all")
    def test_the_first_sales_team_row_wins_per_customer(self, mocked_get_all: MagicMock) -> None:
        """The retiring print chain read row idx 1, so the backfill must match it."""
        mocked_get_all.return_value = [
            {"parent": "CUST-0001", "sales_person": "Narin"},
            {"parent": "CUST-0001", "sales_person": "Somchai"},
            {"parent": "CUST-0002", "sales_person": "Ratri"},
        ]

        self.assertEqual(
            move_patch._first_sales_person_by_customer({"CUST-0001", "CUST-0002"}),
            {"CUST-0001": "Narin", "CUST-0002": "Ratri"},
        )

    @patch.object(move_patch.frappe, "get_all")
    def test_a_blank_customer_validity_text_is_not_copied(self, mocked_get_all: MagicMock) -> None:
        mocked_get_all.return_value = [
            {
                "name": "CUST-0003",
                "override_quotation_validity_text": 1,
                "quotation_custom_validity_text": "   ",
            }
        ]

        self.assertEqual(move_patch._customer_validity_overrides({"CUST-0003"}), {})


class TestRollbackMoveQuotationSignatoryToDocument(UnitTestCase):
    @patch.object(rollback_patch.frappe, "clear_cache")
    @patch.object(rollback_patch, "delete_custom_fields")
    @patch.object(rollback_patch, "create_custom_fields")
    def test_rollback_restores_the_retired_fields_and_drops_the_new_ones(
        self,
        mocked_create: MagicMock,
        mocked_delete: MagicMock,
        _mocked_clear_cache: MagicMock,
    ) -> None:
        rollback_patch.execute()

        mocked_create.assert_called_once_with(rollback_patch.RESTORED_FIELDS, ignore_validate=True)
        mocked_delete.assert_called_once_with(rollback_patch.INTRODUCED_FIELDS, bypass_hooks=True)

    def test_rollback_covers_every_field_the_move_touched(self) -> None:
        restored = {
            doctype: [field["fieldname"] for field in fields]
            for doctype, fields in rollback_patch.RESTORED_FIELDS.items()
        }

        self.assertEqual(restored, move_patch.RETIRED_FIELDS)
        self.assertEqual(
            set(rollback_patch.INTRODUCED_FIELDS["Quotation"]),
            {field["fieldname"] for field in move_patch.quotation_setup.CUSTOM_FIELDS["Quotation"]}
            - {"quotation_signatory_type"},
        )
