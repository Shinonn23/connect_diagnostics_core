# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Resolve serial and batch values from stock transaction item rows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import frappe
from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos


def get_item_traceability(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return ordered values and one traceability record per Batch/SN entry."""
    batch_nos = _unique_values(_text_values(row.get("batch_no")))
    serial_nos = _unique_values(_serial_values(row.get("serial_no")))
    records = _records_from_values(batch_nos, serial_nos)
    bundle = _text(row.get("serial_and_batch_bundle"))

    if bundle:
        entries = frappe.db.get_all(
            "Serial and Batch Entry",
            filters={"parent": bundle},
            fields=["batch_no", "serial_no"],
            order_by="idx asc",
        )
        for entry in entries:
            batch_no = _text(entry.get("batch_no"))
            serial_no = _text(entry.get("serial_no"))
            batch_nos = _append_unique(batch_nos, batch_no)
            serial_nos = _append_unique(serial_nos, serial_no)
            _append_record(records, batch_no, serial_no)

    return {"batch_nos": batch_nos, "serial_nos": serial_nos, "records": records}


def _serial_values(value: Any) -> list[str]:
    raw_value = _text(value)
    if not raw_value:
        return []
    return [str(serial_no) for serial_no in get_serial_nos(raw_value) if serial_no]


def _text_values(value: Any) -> list[str]:
    text = _text(value)
    return [text] if text else []


def _unique_values(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
    return unique


def _records_from_values(batch_nos: list[str], serial_nos: list[str]) -> list[dict[str, str]]:
    if len(batch_nos) == len(serial_nos) and batch_nos:
        return [
            {"batch_no": batch_no, "serial_no": serial_no}
            for batch_no, serial_no in zip(batch_nos, serial_nos, strict=True)
        ]

    records = [{"batch_no": batch_no, "serial_no": ""} for batch_no in batch_nos]
    records.extend({"batch_no": "", "serial_no": serial_no} for serial_no in serial_nos)
    return records


def _append_record(records: list[dict[str, str]], batch_no: str, serial_no: str) -> None:
    record = {"batch_no": batch_no, "serial_no": serial_no}
    if (batch_no or serial_no) and record not in records:
        records.append(record)


def _append_unique(values: list[str], value: str) -> list[str]:
    if value and value not in values:
        values.append(value)
    return values


def _text(value: Any) -> str:
    return str(value or "").strip()
