# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import print_pagination


class TestPrintPagination(UnitTestCase):
    def test_pages_are_based_on_measured_row_height(self) -> None:
        rows = [frappe._dict(idx=idx, description="รายการสั้น") for idx in range(1, 8)]

        pages = print_pagination.get_print_item_pages(frappe._dict(items=rows), "quotation")

        self.assertEqual([row["row"].idx for row in pages[0]], list(range(1, 6)))
        self.assertEqual([row["row"].idx for row in pages[1]], [6, 7])

    def test_ten_quotation_rows_keep_the_boundary_row_on_the_next_page(self) -> None:
        rows = [frappe._dict(idx=idx, description="รายการสั้น") for idx in range(1, 11)]

        pages = print_pagination.get_print_item_pages(frappe._dict(items=rows), "quotation")

        self.assertEqual(
            [[entry["row"].idx for entry in page] for page in pages], [list(range(1, 6)), list(range(6, 11))]
        )

    def test_long_description_consumes_more_than_one_row(self) -> None:
        long_description = "รายละเอียดสินค้าที่มีข้อความยาวมาก " * 20
        pages = print_pagination.get_print_item_pages(
            frappe._dict(
                items=[
                    frappe._dict(idx=1, description=long_description),
                    frappe._dict(idx=2, description="รายการสั้น"),
                ]
            ),
            "quotation",
        )

        measured_height = pages[0][0]["height_mm"]
        self.assertGreater(measured_height, print_pagination.PRINT_LAYOUTS["quotation"].minimum_row_height_mm)
        self.assertEqual(sum(entry["row"].idx for page in pages for entry in page), 3)

    def test_all_supported_layouts_return_whole_item_rows(self) -> None:
        rows = [frappe._dict(idx=idx, description="รายการสั้น") for idx in range(1, 3)]
        doc = frappe._dict(items=rows)

        for layout in print_pagination.PRINT_LAYOUTS:
            with self.subTest(layout=layout):
                pages = print_pagination.get_print_item_pages(doc, layout)
                self.assertEqual(
                    [entry["row"].idx for page in pages for entry in page],
                    [1, 2],
                )
                self.assertTrue(all(entry["height_mm"] > 0 for page in pages for entry in page))

    def test_stock_entry_traceability_consumes_measured_row_height(self) -> None:
        pages = print_pagination.get_print_item_pages(
            frappe._dict(
                items=[
                    frappe._dict(
                        idx=1,
                        item_name="รายการเบิกสินค้า",
                        description="รายละเอียดสินค้ายาว " * 30,
                        s_warehouse="คลังสินค้าหลัก",
                        serial_no="\n".join(f"SN-{idx:03d}" for idx in range(1, 8)),
                    )
                ]
            ),
            "stock_entry",
        )

        self.assertGreater(
            pages[0][0]["height_mm"], print_pagination.PRINT_LAYOUTS["stock_entry"].minimum_row_height_mm
        )

    def test_last_page_can_reserve_space_for_a_signature_footer(self) -> None:
        rows = [frappe._dict(idx=idx, description="รายการสั้น") for idx in range(1, 16)]

        pages = print_pagination.get_print_item_pages(
            frappe._dict(items=rows),
            "purchase_order",
            last_page_usable_height_mm=29.0,
        )

        self.assertEqual([entry["row"].idx for entry in pages[-1]], [15])
        self.assertLessEqual(sum(entry["height_mm"] for entry in pages[-1]), 29.0)
        self.assertEqual([entry["row"].idx for page in pages for entry in page], list(range(1, 16)))

    def test_page_metrics_identify_rows_beyond_a_fixed_table_height(self) -> None:
        metrics = print_pagination.get_print_page_metrics(
            [
                {"height_mm": 8.5},
                {"height_mm": 8.5},
                {"height_mm": 8.5},
            ],
            usable_height_mm=17.0,
        )

        self.assertTrue(metrics["overflow"])
        self.assertTrue(metrics["next_page_required"])
        self.assertEqual(metrics["overflow_item_indexes"], [2])
        self.assertAlmostEqual(metrics["used_height_mm"], 25.5)
        self.assertAlmostEqual(metrics["overflow_mm"], 8.5)

    def test_page_metrics_flag_an_item_that_cannot_fit_on_an_empty_page(self) -> None:
        metrics = print_pagination.get_print_page_metrics(
            [{"height_mm": 25.0}],
            usable_height_mm=20.0,
        )

        self.assertTrue(metrics["overflow"])
        self.assertEqual(metrics["overflow_item_indexes"], [0])
        self.assertEqual(metrics["oversized_item_indexes"], [0])

    def test_page_metrics_reject_invalid_row_height(self) -> None:
        with self.assertRaisesRegex(ValueError, "numeric height_mm"):
            print_pagination.get_print_page_metrics([{"height_mm": ""}], usable_height_mm=20.0)
