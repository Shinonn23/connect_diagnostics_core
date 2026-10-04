# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Content-aware pagination for the app-owned item-table Print Formats."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from html import unescape
from pathlib import Path
from typing import Any, cast

from frappe.model.document import Document
from PIL import ImageFont

PRINT_DPI = 96
PRINT_FONT_PATH = Path(__file__).resolve().parents[2] / "public" / "fonts" / "THSarabun.ttf"
HTML_TAG_PATTERN = re.compile(r"<[^>]*>")
HEIGHT_EPSILON_MM = 0.0001


class PrintLayout:
    """The measurable geometry of one item table."""

    def __init__(
        self,
        usable_height_mm: float,
        line_height_mm: float,
        vertical_padding_mm: float,
        minimum_row_height_mm: float,
        fixed_row_height_mm: float | None = None,
        description_width_mm: float = 0.0,
        description_padding_mm: float = 0.0,
        font_size_mm: float = 4.10,
    ) -> None:
        self.usable_height_mm = usable_height_mm
        self.line_height_mm = line_height_mm
        self.vertical_padding_mm = vertical_padding_mm
        self.minimum_row_height_mm = minimum_row_height_mm
        self.fixed_row_height_mm = fixed_row_height_mm
        self.description_width_mm = description_width_mm
        self.description_padding_mm = description_padding_mm
        self.font_size_mm = font_size_mm


PRINT_LAYOUTS: dict[str, PrintLayout] = {
    # The quotation footer and summary must remain inside the fixed A4 page.
    # The product body is 51.50mm, but its border/padding leaves only 50.50mm
    # for complete rows. Keeping a small safety margin prevents the boundary
    # row from being painted underneath the summary in Chrome PDF.
    "quotation": PrintLayout(
        usable_height_mm=50.5,
        line_height_mm=4.25,
        vertical_padding_mm=2.65,
        minimum_row_height_mm=8.50,
        description_width_mm=89.90,
        description_padding_mm=2.35,
    ),
    # .cd-so items-table reserves 83.2mm below its 10.8mm header.
    "sales_order": PrintLayout(
        usable_height_mm=81.5,
        line_height_mm=4.35,
        vertical_padding_mm=0.0,
        minimum_row_height_mm=8.15,
        fixed_row_height_mm=8.15,
    ),
    # Purchase Order uses a 96mm item budget on continuation pages. Its final
    # page reserves a separate 29mm item budget for the summary/signatures.
    "purchase_order": PrintLayout(
        usable_height_mm=96.0,
        line_height_mm=4.25,
        vertical_padding_mm=2.65,
        minimum_row_height_mm=8.50,
        description_width_mm=46.40,
        description_padding_mm=2.35,
    ),
    # .cd-gr items-table reserves 88.25mm below its 10.9mm header.
    "goods_receipt": PrintLayout(
        usable_height_mm=87.0,
        line_height_mm=3.72,
        vertical_padding_mm=3.0,
        minimum_row_height_mm=8.50,
    ),
    # Stock Entry issue slips use a 141mm item body above their footer.
    "stock_entry": PrintLayout(
        usable_height_mm=141.0,
        line_height_mm=4.25,
        vertical_padding_mm=2.65,
        minimum_row_height_mm=8.50,
        description_width_mm=79.0,
        description_padding_mm=3.0,
    ),
}


def get_print_item_pages(
    doc: Document | Mapping[str, Any],
    layout: str,
    last_page_usable_height_mm: float | None = None,
) -> list[list[dict[str, Any]]]:
    """Measure every item and return whole-row pages for the Print Format.

    Some formats reserve a larger footer on the final page. When that
    reserve is provided, the final item page is split again so its rows fit
    above the summary and signature footer without clipping it.
    """
    print_layout = PRINT_LAYOUTS.get(layout)
    if print_layout is None:
        raise ValueError(f"Unknown print item layout: {layout}")

    rows = cast(Sequence[Any], doc.get("items") or [])
    if not rows:
        return [[]]

    pages: list[list[dict[str, Any]]] = []
    current_page: list[dict[str, Any]] = []
    current_height = 0.0
    for row in rows:
        row_height = _row_height(row, layout, print_layout)
        if current_page and current_height + row_height > print_layout.usable_height_mm:
            pages.append(current_page)
            current_page = []
            current_height = 0.0

        current_page.append({"row": row, "height_mm": row_height})
        current_height += row_height

    if current_page:
        pages.append(current_page)

    if last_page_usable_height_mm is not None:
        _reserve_last_page_space(pages, last_page_usable_height_mm, print_layout.usable_height_mm)

    return pages


def get_print_page_metrics(
    page_items: Sequence[Any],
    usable_height_mm: float,
) -> dict[str, Any]:
    """Report the measured height and overflow of one rendered item table.

    ``page_items`` may be the measured entries returned by
    :func:`get_print_item_pages` (``{"row": ..., "height_mm": ...}``) or any
    sequence of mappings/objects exposing ``height_mm``.  The function does
    not mutate or truncate rows.  A caller should use ``get_print_item_pages``
    (or another whole-row paginator) to split an overflowing sequence before
    passing it to the table component.

    ``overflow_item_indexes`` is zero-based and identifies every row whose
    bottom is beyond the fixed table budget.  ``oversized_item_indexes``
    identifies rows that cannot fit on an otherwise empty table; such a row
    needs a smaller row layout or an explicit content split.
    """
    capacity = float(usable_height_mm)
    if capacity <= 0:
        raise ValueError("usable_height_mm must be greater than zero")

    heights = [_entry_height(entry) for entry in page_items]
    used = sum(heights)
    cumulative = 0.0
    overflow_item_indexes: list[int] = []
    oversized_item_indexes: list[int] = []
    for index, height in enumerate(heights):
        if height > capacity + HEIGHT_EPSILON_MM:
            oversized_item_indexes.append(index)
        cumulative += height
        if cumulative > capacity + HEIGHT_EPSILON_MM:
            overflow_item_indexes.append(index)

    return {
        "capacity_mm": capacity,
        "used_height_mm": used,
        "remaining_height_mm": capacity - used,
        "overflow_mm": max(used - capacity, 0.0),
        "overflow": bool(overflow_item_indexes),
        "next_page_required": bool(overflow_item_indexes),
        "row_count": len(heights),
        "row_heights_mm": heights,
        "overflow_item_indexes": overflow_item_indexes,
        "oversized_item_indexes": oversized_item_indexes,
    }


def _reserve_last_page_space(
    pages: list[list[dict[str, Any]]],
    usable_height_mm: float,
    regular_page_height_mm: float,
) -> None:
    """Split an overfull final page while keeping each item row intact."""
    if not pages:
        return

    final_page = pages[-1]
    final_height = sum(entry["height_mm"] for entry in final_page)
    if final_height <= usable_height_mm:
        return

    split_at: int | None = None
    for index in range(1, len(final_page)):
        prefix_height = sum(entry["height_mm"] for entry in final_page[:index])
        suffix_height = final_height - prefix_height
        if prefix_height <= regular_page_height_mm and suffix_height <= usable_height_mm:
            split_at = index

    if split_at is None:
        # A single row can itself be taller than the reserved area. Keeping
        # it whole is safer than silently dropping it or splitting its cells.
        return

    pages[-1] = final_page[:split_at]
    pages.append(final_page[split_at:])


def _entry_height(entry: Any) -> float:
    """Read a measured row height from a paginator entry."""
    value = entry.get("height_mm") if isinstance(entry, Mapping) else getattr(entry, "height_mm", None)
    if value is None:
        raise ValueError("every page item must include a numeric height_mm")
    try:
        height = float(cast(float | int | str, value))
    except (TypeError, ValueError):
        raise ValueError("every page item must include a numeric height_mm") from None
    if height <= 0:
        raise ValueError("every page item height_mm must be greater than zero")
    return height


def _row_height(row: Any, layout: str, print_layout: PrintLayout) -> float:
    if print_layout.fixed_row_height_mm is not None:
        return print_layout.fixed_row_height_mm

    if layout == "goods_receipt":
        return _goods_receipt_row_height(row, print_layout)

    if layout == "stock_entry":
        return _stock_entry_row_height(row, print_layout)

    description = _row_text(
        (_row_value(row, "item_name") or _row_value(row, "description"))
        if layout == "purchase_order"
        else (_row_value(row, "description") or _row_value(row, "item_name"))
    )
    line_count = _display_line_count(
        description,
        print_layout.description_width_mm - print_layout.description_padding_mm,
        print_layout.font_size_mm,
    )
    calculated_height = line_count * print_layout.line_height_mm + print_layout.vertical_padding_mm
    return max(calculated_height, print_layout.minimum_row_height_mm)


def _stock_entry_row_height(row: Any, print_layout: PrintLayout) -> float:
    """Measure the description and traceability lines on an issue row."""
    description = _row_text(_row_value(row, "description") or _row_value(row, "item_name"))
    metadata = "  ".join(
        value
        for value in (
            _row_text(_row_value(row, "s_warehouse")),
            _row_text(_row_value(row, "batch_no")),
            _row_text(_row_value(row, "serial_no")),
        )
        if value
    )
    if metadata:
        description = f"{description}\n{metadata}"

    line_count = _display_line_count(
        description,
        print_layout.description_width_mm - print_layout.description_padding_mm,
        print_layout.font_size_mm,
    )
    calculated_height = line_count * print_layout.line_height_mm + print_layout.vertical_padding_mm
    return max(calculated_height, print_layout.minimum_row_height_mm)


def _goods_receipt_row_height(row: Any, print_layout: PrintLayout) -> float:
    """Measure the stacked metadata blocks used by the Goods Receipt row."""
    description_width_mm = 184.60 * 0.545 - 3.10
    metadata: list[str] = []
    for fieldname, label in (
        ("warehouse", "คลัง / Warehouse"),
        ("batch_no", "Batch"),
        ("serial_no", "S/N"),
        ("quality_inspection", "Q.I."),
    ):
        value = _row_text(_row_value(row, fieldname))
        if value:
            metadata.append(f"{label}: {value}")

    metadata_lines = _display_line_count("  ".join(metadata), description_width_mm, 3.25) if metadata else 0
    rejected_lines = 0
    if _row_value(row, "rejected_qty"):
        rejected_text = (
            f"ไม่รับ / Rejected: {_row_value(row, 'rejected_qty')} "
            f"{_row_value(row, 'uom') or _row_value(row, 'stock_uom') or ''} "
            f"{_row_value(row, 'rejected_warehouse') or ''}"
        )
        rejected_lines = _display_line_count(rejected_text, description_width_mm, 3.42)

    received_lines = 0
    if _numbers_differ(_row_value(row, "received_qty"), _row_value(row, "qty")):
        received_lines = 1

    content_height = print_layout.vertical_padding_mm + 4.25
    if metadata_lines:
        content_height += 0.55 + metadata_lines * print_layout.line_height_mm
    if rejected_lines:
        content_height += 0.55 + rejected_lines * print_layout.line_height_mm
    if received_lines:
        content_height += 0.55 + received_lines * print_layout.line_height_mm
    return max(content_height, print_layout.minimum_row_height_mm)


def _display_line_count(value: str, width_mm: float, font_size_mm: float) -> int:
    if width_mm <= 0:
        return 1
    text = _row_text(value).replace("\r\n", "\n").replace("\r", "\n")
    font = _print_font(font_size_mm)
    width_px = _mm_to_px(width_mm)
    return sum(_wrapped_line_count(line, font, width_px) for line in text.split("\n")) or 1


def _wrapped_line_count(value: str, font: ImageFont.FreeTypeFont, width_px: float) -> int:
    if not value:
        return 1

    line_count = 1
    line_width = 0.0
    for character in value:
        character_width = float(font.getlength(character))
        if line_width and line_width + character_width > width_px:
            line_count += 1
            line_width = character_width
        else:
            line_width += character_width
    return line_count


def _row_value(row: Any, fieldname: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(fieldname)
    return getattr(row, fieldname, None)


def _row_text(value: Any) -> str:
    text = unescape(str(value or ""))
    return HTML_TAG_PATTERN.sub("", text).strip()


def _numbers_differ(left: Any, right: Any) -> bool:
    try:
        return float(left or 0) != float(right or 0)
    except (TypeError, ValueError):
        return str(left or "") != str(right or "")


def _mm_to_px(value_mm: float) -> float:
    return value_mm / 25.4 * PRINT_DPI


@lru_cache(maxsize=8)
def _print_font(size_mm: float) -> ImageFont.FreeTypeFont:
    size_px = max(round(_mm_to_px(size_mm)), 1)
    return ImageFont.truetype(str(PRINT_FONT_PATH), size_px)
