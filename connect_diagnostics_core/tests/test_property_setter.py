# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path

from frappe.tests.utils import FrappeTestCase

import connect_diagnostics_core

FIXTURE_PATH = Path(connect_diagnostics_core.__file__).parent / "fixtures" / "property_setter.json"


def _load_fixture() -> list[dict]:
    with FIXTURE_PATH.open() as f:
        return json.load(f)


class TestNamingSeriesPropertySetters(FrappeTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.rows = _load_fixture()
        cls.options_rows = {
            r["doc_type"]: r
            for r in cls.rows
            if r.get("field_name") == "naming_series" and r.get("property") == "options"
        }
        cls.default_rows = {
            r["doc_type"]: r
            for r in cls.rows
            if r.get("field_name") == "naming_series" and r.get("property") == "default"
        }

    def test_every_options_setter_has_matching_default(self) -> None:
        missing = sorted(set(self.options_rows) - set(self.default_rows))
        self.assertFalse(
            missing,
            f"naming_series options set without a matching default property setter for: {missing}. "
            "Add a `<DocType>-naming_series-default` row whose value is one of the options.",
        )

    def test_default_value_is_present_in_options(self) -> None:
        mismatches: list[str] = []
        for doc_type, default_row in self.default_rows.items():
            options_row = self.options_rows.get(doc_type)
            if not options_row:
                mismatches.append(f"{doc_type}: default set without matching options")
                continue
            default_value = (default_row.get("value") or "").strip()
            options = [o.strip() for o in (options_row.get("value") or "").split("\n") if o.strip()]
            if default_value not in options:
                mismatches.append(f"{doc_type}: default {default_value!r} not in options {options!r}")
        self.assertFalse(
            mismatches,
            "naming_series default does not match options list:\n  " + "\n  ".join(mismatches),
        )
