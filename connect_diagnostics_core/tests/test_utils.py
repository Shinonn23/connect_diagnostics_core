# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe


def before_tests() -> None:
    """Minimal test bootstrap.

    The app's tests are self-contained unit tests (no DocType fixtures), so there is no
    need to run the ERPNext setup wizard here. Doing so previously created a THB
    "_Test Company" that collided with ERPNext's own USD "_Test Company" test records
    under Frappe v16's eager test-record bootstrap.
    """
    frappe.clear_cache()
