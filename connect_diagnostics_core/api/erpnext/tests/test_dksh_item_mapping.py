# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import dksh_item_mapping, sales_order
from connect_diagnostics_core.api.frappe import search
from connect_diagnostics_core.config.dksh import (
    DKSH_COMPANY,
    DKSH_STANDARD_SELLING_PRICE_LIST,
    SAP_ORDER_STATUS_KEYED,
    SAP_ORDER_STATUS_PENDING,
)
from connect_diagnostics_core.connect_diagnostics_core.doctype.dksh_item_mapping import (
    dksh_item_mapping as mapping_doctype,
)
from connect_diagnostics_core.setup import dksh_sales


class FakeDocument(frappe._dict):
    def __init__(self, values: dict[str, Any] | None = None, *, before: FakeDocument | None = None) -> None:
        super().__init__(values or {})
        self._before = before
        self.flags = frappe._dict()

    def get_doc_before_save(self) -> FakeDocument | None:
        return self._before

    def set(self, fieldname: str, value: Any) -> None:
        self[fieldname] = value


class TestDKSHItemMappingValidation(UnitTestCase):
    def test_dksh_only_request_requires_all_item_master_fields(self) -> None:
        doc = FakeDocument({"item_channel": dksh_item_mapping.CHANNEL_DKSH})

        with self.assertRaises(frappe.ValidationError):
            dksh_item_mapping._validate_submission(cast(Document, doc))

        for fieldname in dksh_item_mapping.REQUIRED_DKSH_ONLY_FIELDS:
            doc.set(fieldname, f"{fieldname}-value")
        dksh_item_mapping._validate_submission(cast(Document, doc))

    @patch.object(
        dksh_item_mapping.frappe.db,
        "get_value",
        return_value={"item_channel": dksh_item_mapping.CHANNEL_DKSH, "disabled": 1},
    )
    def test_returned_dksh_only_request_can_be_resubmitted_with_its_pending_item(
        self, mocked_get_value: MagicMock
    ) -> None:
        pending_item = "DKSH-PENDING-00001"
        doc = FakeDocument(
            {
                "name": pending_item,
                "item_channel": dksh_item_mapping.CHANNEL_DKSH,
                "item": pending_item,
                "request_sent_on": "2026-07-24 10:00:00",
                **{
                    fieldname: f"{fieldname}-value"
                    for fieldname in dksh_item_mapping.REQUIRED_DKSH_ONLY_FIELDS
                },
            }
        )

        dksh_item_mapping._validate_submission(
            cast(Document, doc), dksh_item_mapping.RETURNED_FOR_CORRECTION_STATE
        )

        mocked_get_value.assert_called_once_with(
            "Item",
            pending_item,
            ["item_channel", "disabled"],
            as_dict=True,
        )

    def test_draft_dksh_only_request_rejects_an_existing_item(self) -> None:
        doc = FakeDocument(
            {
                "name": "DKSH-PENDING-00001",
                "item_channel": dksh_item_mapping.CHANNEL_DKSH,
                "item": "DKSH-PENDING-00001",
                **{
                    fieldname: f"{fieldname}-value"
                    for fieldname in dksh_item_mapping.REQUIRED_DKSH_ONLY_FIELDS
                },
            }
        )

        with self.assertRaises(frappe.ValidationError):
            dksh_item_mapping._validate_submission(cast(Document, doc))

    @patch.object(dksh_item_mapping.frappe.db, "set_value")
    def test_dksh_only_item_values_are_persisted_after_item_fetches(
        self, mocked_set_value: MagicMock
    ) -> None:
        item_doc = FakeDocument({"name": "DKSH-PENDING-00001"})
        mapping_doc = FakeDocument(
            {fieldname: f"{fieldname}-value" for fieldname in dksh_item_mapping.ITEM_MASTER_FIELDS}
        )

        dksh_item_mapping._persist_dksh_only_item_values(
            cast(Document, item_doc), cast(Document, mapping_doc)
        )

        expected_values = {
            fieldname: f"{fieldname}-value" for fieldname in dksh_item_mapping.ITEM_MASTER_FIELDS
        }
        mocked_set_value.assert_called_once_with(
            "Item", "DKSH-PENDING-00001", expected_values, update_modified=False
        )
        for fieldname, value in expected_values.items():
            self.assertEqual(item_doc.get(fieldname), value)

    @patch.object(dksh_item_mapping.frappe, "get_doc")
    def test_existing_cd_item_becomes_both_when_the_request_is_submitted(
        self, mocked_get_doc: MagicMock
    ) -> None:
        item_doc = FakeDocument({"item_channel": dksh_item_mapping.CHANNEL_CD, "disabled": 0})
        item_doc.save = MagicMock()
        mocked_get_doc.return_value = item_doc
        doc = FakeDocument(
            {
                "item_channel": dksh_item_mapping.CHANNEL_BOTH,
                "item": "CD-ITEM-001",
            }
        )

        dksh_item_mapping._validate_submission(cast(Document, doc))

        self.assertEqual(item_doc.item_channel, dksh_item_mapping.CHANNEL_BOTH)
        item_doc.save.assert_called_once_with(ignore_permissions=True)

    @patch.object(dksh_item_mapping, "_validate_active_mapping")
    def test_activation_marks_the_mapping_for_post_save_rename(
        self, mocked_validate_active: MagicMock
    ) -> None:
        doc = FakeDocument(
            {
                "mapping_state": dksh_item_mapping.ACTIVE_STATE,
                "item_channel": dksh_item_mapping.CHANNEL_DKSH,
                "item": "DKSH-PENDING-00001",
                "dksh_item_code": "100000001",
            },
            before=FakeDocument(
                {
                    "mapping_state": dksh_item_mapping.AWAITING_DKSH_CODE_STATE,
                    "item_channel": dksh_item_mapping.CHANNEL_DKSH,
                    "item": "DKSH-PENDING-00001",
                }
            ),
        )

        dksh_item_mapping.validate(cast(Document, doc))

        self.assertTrue(doc.flags.activate_dksh_item_mapping)
        mocked_validate_active.assert_called_once_with(cast(Document, doc))

    @patch.object(dksh_item_mapping, "_activate_mapping")
    def test_post_save_activation_performs_the_rename_atomically(self, mocked_activate: MagicMock) -> None:
        doc = FakeDocument()
        doc.flags.activate_dksh_item_mapping = True

        dksh_item_mapping.on_update(cast(Document, doc))

        mocked_activate.assert_called_once_with(cast(Document, doc))

    def test_dksh_code_cannot_be_entered_before_the_request_is_sent(self) -> None:
        doc = FakeDocument(
            {
                "mapping_state": dksh_item_mapping.DRAFT_STATE,
                "item_channel": dksh_item_mapping.CHANNEL_DKSH,
                "dksh_item_code": "100000001",
            }
        )

        with self.assertRaises(frappe.ValidationError):
            dksh_item_mapping.validate(cast(Document, doc))

    @patch.object(dksh_item_mapping.frappe.db, "exists", return_value=False)
    @patch.object(dksh_item_mapping, "rename_doc", side_effect=["100000001", "100000001"])
    def test_dksh_only_activation_uses_the_permission_aware_rename_api(
        self, mocked_rename_doc: MagicMock, _mocked_exists: MagicMock
    ) -> None:
        doc = FakeDocument(
            {
                "name": "DKSH-PENDING-00001",
                "item": "DKSH-PENDING-00001",
            }
        )

        dksh_item_mapping._rename_pending_item_and_mapping(cast(Document, doc), "100000001")

        self.assertEqual(doc.name, "100000001")
        self.assertEqual(doc.item, "100000001")
        self.assertEqual(
            mocked_rename_doc.call_args_list,
            [
                call(
                    "Item",
                    "DKSH-PENDING-00001",
                    "100000001",
                    force=True,
                    ignore_permissions=True,
                    show_alert=False,
                    rebuild_search=False,
                ),
                call(
                    dksh_item_mapping.DKSH_ITEM_MAPPING_DOCTYPE,
                    "DKSH-PENDING-00001",
                    "100000001",
                    force=True,
                    ignore_permissions=True,
                    show_alert=False,
                    rebuild_search=False,
                ),
            ],
        )


class TestDKSHSalesOrderResolution(UnitTestCase):
    def test_fixed_company_is_used_for_dksh_matching(self) -> None:
        self.assertEqual(dksh_item_mapping.get_dksh_company(), DKSH_COMPANY)
        self.assertTrue(dksh_item_mapping.is_dksh_company(DKSH_COMPANY))
        self.assertFalse(dksh_item_mapping.is_dksh_company("CD Company"))

    @patch.object(sales_order.frappe, "has_permission")
    def test_dksh_item_mode_returns_managed_sales_defaults(self, _mocked_has_permission: MagicMock) -> None:
        result = sales_order.get_sales_order_item_mode(DKSH_COMPANY)

        self.assertEqual(
            result["data"],
            {
                "is_dksh_company": True,
                "selling_price_list": DKSH_STANDARD_SELLING_PRICE_LIST,
                "skip_delivery_note": 1,
                "sap_order_statuses": {
                    "pending": SAP_ORDER_STATUS_PENDING,
                    "keyed": SAP_ORDER_STATUS_KEYED,
                },
            },
        )

    @patch.object(sales_order, "_get_active_mapping_item", return_value="CD-ITEM-001")
    @patch.object(sales_order.dksh_item_mapping, "is_dksh_company", return_value=True)
    def test_server_replaces_the_visible_mapping_with_internal_item_code(
        self, _mocked_is_dksh_company: MagicMock, mocked_mapping_item: MagicMock
    ) -> None:
        row = FakeDocument({"dksh_item_mapping": "DKSH-MAPPING-001"})
        doc = FakeDocument({"company": "DKSH Company", "items": [row]})

        sales_order.before_validate(cast(Document, doc))

        self.assertEqual(row.item_code, "CD-ITEM-001")
        mocked_mapping_item.assert_called_once_with("DKSH-MAPPING-001", "DKSH Company", for_update=True)

    @patch.object(sales_order.dksh_item_mapping, "is_dksh_company", return_value=True)
    def test_server_rejects_a_dksh_row_without_a_mapping(self, _mocked_is_dksh_company: MagicMock) -> None:
        doc = FakeDocument({"company": "DKSH Company", "items": [FakeDocument()]})

        with self.assertRaises(frappe.ValidationError):
            sales_order.before_validate(cast(Document, doc))

    def test_company_change_with_item_rows_is_rejected(self) -> None:
        doc = FakeDocument(
            {"company": "DKSH Company", "items": [FakeDocument({"item_code": "CD-ITEM-001"})]},
            before=FakeDocument({"company": "CD Company"}),
        )

        with self.assertRaises(frappe.ValidationError):
            sales_order.validate(cast(Document, doc))

    @patch.object(sales_order, "_get_active_mapping_item", return_value="CD-ITEM-001")
    def test_dksh_draft_sets_managed_price_list_skip_delivery_note_and_sap_pending_status(
        self, _mocked_mapping_item: MagicMock
    ) -> None:
        row = FakeDocument({"dksh_item_mapping": "DKSH-MAPPING-001"})
        doc = FakeDocument(
            {
                "company": DKSH_COMPANY,
                "docstatus": 0,
                "selling_price_list": "Other Price List",
                "skip_delivery_note": 0,
                "items": [row],
            }
        )

        sales_order.before_validate(cast(Document, doc))

        self.assertEqual(doc.selling_price_list, DKSH_STANDARD_SELLING_PRICE_LIST)
        self.assertEqual(doc.skip_delivery_note, 1)
        self.assertEqual(doc.sap_order_status, SAP_ORDER_STATUS_PENDING)
        self.assertEqual(row.item_code, "CD-ITEM-001")

    def test_submitted_sap_fields_cannot_be_edited_outside_the_keying_actions(self) -> None:
        doc = FakeDocument(
            {
                "docstatus": 1,
                "sap_order_status": SAP_ORDER_STATUS_KEYED,
                "sap_order_no": "SAP-NEW",
            },
            before=FakeDocument(
                {
                    "docstatus": 1,
                    "sap_order_status": SAP_ORDER_STATUS_KEYED,
                    "sap_order_no": "SAP-OLD",
                }
            ),
        )

        with self.assertRaises(frappe.ValidationError):
            sales_order.before_update_after_submit(cast(Document, doc))

    def test_sap_actions_can_update_submitted_sap_fields(self) -> None:
        doc = FakeDocument(
            {
                "docstatus": 1,
                "sap_order_status": SAP_ORDER_STATUS_KEYED,
                "sap_order_no": "SAP-NEW",
            },
            before=FakeDocument(
                {
                    "docstatus": 1,
                    "sap_order_status": SAP_ORDER_STATUS_KEYED,
                    "sap_order_no": "SAP-OLD",
                }
            ),
        )
        doc.flags.allow_sap_order_update = True

        sales_order.before_update_after_submit(cast(Document, doc))


class TestDKSHSapOrderKeying(UnitTestCase):
    @patch.object(sales_order, "now", return_value="2026-07-26 12:30:00")
    @patch.object(sales_order.frappe, "get_doc")
    @patch.object(sales_order.frappe.db, "get_value")
    @patch.object(sales_order.frappe, "has_permission")
    def test_marking_pending_order_as_keyed_records_number_and_actor(
        self,
        _mocked_has_permission: MagicMock,
        mocked_get_value: MagicMock,
        mocked_get_doc: MagicMock,
        _mocked_now: MagicMock,
    ) -> None:
        mocked_get_value.return_value = {
            "company": DKSH_COMPANY,
            "docstatus": 1,
            "sap_order_status": SAP_ORDER_STATUS_PENDING,
            "sap_order_no": "",
        }
        doc = FakeDocument(
            {
                "name": "_Test DKSH SO-001",
                "company": DKSH_COMPANY,
                "docstatus": 1,
                "sap_order_status": SAP_ORDER_STATUS_PENDING,
            }
        )
        doc.save = MagicMock()
        mocked_get_doc.return_value = doc

        result = sales_order.mark_as_keyed_in_sap("_Test DKSH SO-001", "SAP-0001")

        mocked_get_value.assert_called_once_with(
            "Sales Order",
            "_Test DKSH SO-001",
            list(sales_order.SALES_ORDER_LOCK_FIELDS),
            as_dict=True,
            for_update=True,
        )
        self.assertEqual(doc.sap_order_status, SAP_ORDER_STATUS_KEYED)
        self.assertEqual(doc.sap_order_no, "SAP-0001")
        self.assertEqual(doc.sap_keyed_by, frappe.session.user)
        self.assertEqual(doc.sap_keyed_on, "2026-07-26 12:30:00")
        self.assertIsNone(doc.sap_order_correction_reason)
        self.assertTrue(doc.flags.allow_sap_order_update)
        doc.save.assert_called_once_with()
        self.assertEqual(result["data"]["sap_order_no"], "SAP-0001")

    @patch.object(sales_order.frappe, "get_doc")
    @patch.object(sales_order.frappe.db, "get_value")
    @patch.object(sales_order.frappe, "has_permission")
    def test_correction_uses_document_save_and_requires_a_reason(
        self,
        _mocked_has_permission: MagicMock,
        mocked_get_value: MagicMock,
        mocked_get_doc: MagicMock,
    ) -> None:
        mocked_get_value.return_value = {
            "company": DKSH_COMPANY,
            "docstatus": 1,
            "sap_order_status": SAP_ORDER_STATUS_KEYED,
            "sap_order_no": "SAP-OLD",
        }
        doc = FakeDocument(
            {
                "name": "_Test DKSH SO-002",
                "company": DKSH_COMPANY,
                "docstatus": 1,
                "sap_order_status": SAP_ORDER_STATUS_KEYED,
                "sap_order_no": "SAP-OLD",
            }
        )
        doc.save = MagicMock()
        mocked_get_doc.return_value = doc

        with self.assertRaises(frappe.ValidationError):
            sales_order.correct_sap_order_no("_Test DKSH SO-002", "SAP-NEW", " ")

        result = sales_order.correct_sap_order_no(
            "_Test DKSH SO-002",
            "SAP-NEW",
            "Corrected after checking the SAP confirmation.",
        )

        self.assertEqual(doc.sap_order_status, SAP_ORDER_STATUS_KEYED)
        self.assertEqual(doc.sap_order_no, "SAP-NEW")
        self.assertEqual(doc.sap_order_correction_reason, "Corrected after checking the SAP confirmation.")
        doc.save.assert_called_once_with()
        self.assertEqual(result["data"]["sap_order_correction_reason"], doc.sap_order_correction_reason)

    @patch.object(sales_order.frappe.db, "get_value")
    @patch.object(sales_order.frappe, "has_permission")
    def test_sap_keying_rejects_draft_non_dksh_and_non_pending_orders(
        self,
        _mocked_has_permission: MagicMock,
        mocked_get_value: MagicMock,
    ) -> None:
        invalid_orders = (
            {"company": DKSH_COMPANY, "docstatus": 0, "sap_order_status": SAP_ORDER_STATUS_PENDING},
            {"company": "CD Company", "docstatus": 1, "sap_order_status": SAP_ORDER_STATUS_PENDING},
            {"company": DKSH_COMPANY, "docstatus": 1, "sap_order_status": SAP_ORDER_STATUS_KEYED},
        )

        for locked_order in invalid_orders:
            with self.subTest(locked_order=locked_order):
                mocked_get_value.return_value = locked_order
                with self.assertRaises(frappe.ValidationError):
                    sales_order.mark_as_keyed_in_sap("_Test DKSH SO-003", "SAP-0003")

    def test_sap_keying_rejects_empty_sales_order(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            sales_order.mark_as_keyed_in_sap(" ", "SAP-0004")

    @patch.object(sales_order.frappe, "get_doc")
    @patch.object(sales_order.frappe.db, "get_value")
    @patch.object(sales_order.frappe, "has_permission")
    def test_sap_keying_rejects_empty_sap_order_number(
        self,
        _mocked_has_permission: MagicMock,
        mocked_get_value: MagicMock,
        mocked_get_doc: MagicMock,
    ) -> None:
        mocked_get_value.return_value = {
            "company": DKSH_COMPANY,
            "docstatus": 1,
            "sap_order_status": SAP_ORDER_STATUS_PENDING,
            "sap_order_no": "",
        }
        mocked_get_doc.return_value = FakeDocument(
            {
                "name": "_Test DKSH SO-004",
                "sap_order_status": SAP_ORDER_STATUS_PENDING,
            }
        )

        with self.assertRaises(frappe.ValidationError):
            sales_order.mark_as_keyed_in_sap("_Test DKSH SO-004", " ")


class TestDKSHSalesSetup(UnitTestCase):
    @patch.object(dksh_sales.frappe, "clear_cache")
    @patch.object(dksh_sales.frappe, "cache")
    @patch.object(dksh_sales.frappe, "get_doc")
    @patch.object(dksh_sales.frappe.db, "get_value", return_value=None)
    def test_creates_managed_price_list_without_saving_item_prices(
        self,
        _mocked_get_value: MagicMock,
        mocked_get_doc: MagicMock,
        mocked_cache: MagicMock,
        mocked_clear_cache: MagicMock,
    ) -> None:
        price_list = MagicMock()
        mocked_get_doc.return_value = price_list

        dksh_sales.ensure_configuration()

        mocked_get_doc.assert_called_once_with(
            {
                "doctype": "Price List",
                "name": DKSH_STANDARD_SELLING_PRICE_LIST,
                "buying": 0,
                **dksh_sales.MANAGED_PRICE_LIST_VALUES,
            }
        )
        price_list.db_insert.assert_called_once_with()
        price_list.save.assert_not_called()
        mocked_cache.hdel.assert_called_once_with(
            "price_list_details", DKSH_STANDARD_SELLING_PRICE_LIST
        )
        mocked_clear_cache.assert_called_once_with(doctype="Price List")

    @patch.object(dksh_sales.frappe, "clear_cache")
    @patch.object(dksh_sales.frappe, "cache")
    @patch.object(dksh_sales.frappe.db, "set_value")
    @patch.object(dksh_sales.frappe, "get_doc")
    @patch.object(dksh_sales.frappe.db, "get_value")
    def test_repairs_managed_price_list_with_scoped_database_update(
        self,
        mocked_get_value: MagicMock,
        mocked_get_doc: MagicMock,
        mocked_set_value: MagicMock,
        _mocked_cache: MagicMock,
        _mocked_clear_cache: MagicMock,
    ) -> None:
        mocked_get_value.return_value = {
            "price_list_name": DKSH_STANDARD_SELLING_PRICE_LIST,
            "currency": "USD",
            "selling": 0,
            "enabled": 0,
        }

        dksh_sales.ensure_configuration()

        mocked_get_doc.assert_not_called()
        mocked_set_value.assert_called_once_with(
            "Price List",
            DKSH_STANDARD_SELLING_PRICE_LIST,
            {"currency": "THB", "selling": 1, "enabled": 1},
            update_modified=False,
        )


class TestDKSHMappingLinkSearch(UnitTestCase):
    @patch.object(
        search.frappe_search, "search_widget", return_value=[("CD-ITEM-001", "100000001", "Test Item")]
    )
    def test_special_link_search_hides_the_internal_cd_item_code(
        self, mocked_search_widget: MagicMock
    ) -> None:
        result = search.search_link(
            dksh_item_mapping.DKSH_ITEM_MAPPING_DOCTYPE,
            "100000001",
            sales_order.DKSH_ITEM_MAPPING_QUERY,
            {"company": "DKSH Company"},
        )

        self.assertEqual(
            result,
            [{"value": "CD-ITEM-001", "label": "100000001", "description": "Test Item"}],
        )
        self.assertNotIn("CD-ITEM-001", result[0]["label"])
        self.assertNotIn("CD-ITEM-001", result[0]["description"])
        mocked_search_widget.assert_called_once()


class TestDKSHItemMappingSchema(UnitTestCase):
    @patch.object(mapping_doctype.frappe.db, "add_unique")
    def test_mapping_doctype_enforces_external_code_uniqueness(self, mocked_add_unique: MagicMock) -> None:
        mapping_doctype.on_doctype_update()

        mocked_add_unique.assert_called_once_with(
            dksh_item_mapping.DKSH_ITEM_MAPPING_DOCTYPE,
            ["dksh_item_code"],
            constraint_name="unique_dksh_item_mapping_code",
        )
