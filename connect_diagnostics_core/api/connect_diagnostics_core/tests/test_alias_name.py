# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ..alias_name import get_alias_map, get_original_display_name


def _mock_meta(has_field_result: bool = True) -> MagicMock:
    meta = MagicMock()
    meta.has_field.return_value = has_field_result
    return meta


def _make_source_rows(*items: tuple[str, str], alias_field: str = "item_name") -> list[dict]:
    return [{"name": name, alias_field: display} for name, display in items]


def _make_alias_rows(*pairs: tuple[str, str]) -> list[dict]:
    return [{"primary_name": name, "alias_name": alias} for name, alias in pairs]


class TestGetOriginalDisplayName(FrappeTestCase):
    def test_raises_permission_error_when_no_read_access(self):
        with patch("frappe.has_permission", return_value=False):
            with self.assertRaises(frappe.PermissionError):
                get_original_display_name("Customer", "CUST-001")

    def test_returns_empty_when_doctype_not_configured(self):
        with (
            patch("frappe.has_permission", return_value=True),
            patch("frappe.db.get_value", return_value=None),
        ):
            result = get_original_display_name("Customer", "CUST-001")
        self.assertEqual(result, {"data": ""})

    def test_returns_original_field_value(self):
        def _get_value_side_effect(doctype, filters_or_name, field):
            if doctype == "Alias Supported DocType":
                return "customer_name"
            return "John Doe"

        with (
            patch("frappe.has_permission", return_value=True),
            patch("frappe.db.get_value", side_effect=_get_value_side_effect),
        ):
            result = get_original_display_name("Customer", "CUST-001")
        self.assertEqual(result, {"data": "John Doe"})

    def test_returns_empty_string_when_field_value_is_none(self):
        def _get_value_side_effect(doctype, filters_or_name, field):
            if doctype == "Alias Supported DocType":
                return "customer_name"
            return None

        with (
            patch("frappe.has_permission", return_value=True),
            patch("frappe.db.get_value", side_effect=_get_value_side_effect),
        ):
            result = get_original_display_name("Customer", "CUST-001")
        self.assertEqual(result, {"data": ""})


class TestGetAliasMap(FrappeTestCase):
    @contextmanager
    def _patch_all(
        self,
        *,
        has_permission: bool = True,
        alias_field: str | None = "item_name",
        meta_has_field: bool = True,
        source_rows: list[dict] | None = None,
        alias_rows: list[dict] | None = None,
    ):
        def _get_all_side_effect(doctype, **_kwargs):
            if doctype == "Alias Name":
                return alias_rows or []
            return source_rows or []

        with ExitStack() as stack:
            stack.enter_context(patch("frappe.has_permission", return_value=has_permission))
            stack.enter_context(patch("frappe.db.get_value", return_value=alias_field))
            stack.enter_context(patch("frappe.get_meta", return_value=_mock_meta(meta_has_field)))
            stack.enter_context(patch("frappe.get_all", side_effect=_get_all_side_effect))
            yield

    def test_raises_permission_error_when_no_read_access(self):
        with patch("frappe.has_permission", return_value=False):
            with self.assertRaises(frappe.PermissionError):
                get_alias_map("Item")

    def test_returns_empty_when_doctype_not_configured(self):
        with (
            patch("frappe.has_permission", return_value=True),
            patch("frappe.db.get_value", return_value=None),
        ):
            result = get_alias_map("Item")
        self.assertEqual(result, {"data": {}})

    def test_returns_empty_when_alias_field_is_blank(self):
        with (
            patch("frappe.has_permission", return_value=True),
            patch("frappe.db.get_value", return_value=""),
        ):
            result = get_alias_map("Item")
        self.assertEqual(result, {"data": {}})

    def test_returns_empty_when_alias_field_not_on_meta(self):
        with (
            patch("frappe.has_permission", return_value=True),
            patch("frappe.db.get_value", return_value="item_name"),
            patch("frappe.get_meta", return_value=_mock_meta(has_field_result=False)),
        ):
            result = get_alias_map("Item")
        self.assertEqual(result, {"data": {}})

    def test_returns_alias_name_when_mapping_exists(self):
        source = _make_source_rows(("ITEM-001", "Original Name A"))
        aliases = _make_alias_rows(("ITEM-001", "ชื่อตามราชการ A"))
        with self._patch_all(source_rows=source, alias_rows=aliases):
            result = get_alias_map("Item")
        self.assertEqual(result, {"data": {"ITEM-001": "ชื่อตามราชการ A"}})

    def test_falls_back_to_alias_field_value_when_no_alias(self):
        source = _make_source_rows(("ITEM-001", "Original Name A"))
        with self._patch_all(source_rows=source, alias_rows=[]):
            result = get_alias_map("Item")
        self.assertEqual(result, {"data": {"ITEM-001": "Original Name A"}})

    def test_mixed_aliased_and_unaliased_records(self):
        source = _make_source_rows(
            ("ITEM-001", "Original A"),
            ("ITEM-002", "Original B"),
        )
        aliases = _make_alias_rows(("ITEM-001", "ชื่อตามราชการ A"))
        with self._patch_all(source_rows=source, alias_rows=aliases):
            result = get_alias_map("Item")
        self.assertEqual(
            result,
            {"data": {"ITEM-001": "ชื่อตามราชการ A", "ITEM-002": "Original B"}},
        )

    def test_returns_empty_dict_when_no_source_records(self):
        with self._patch_all(source_rows=[], alias_rows=[]):
            result = get_alias_map("Item")
        self.assertEqual(result, {"data": {}})
