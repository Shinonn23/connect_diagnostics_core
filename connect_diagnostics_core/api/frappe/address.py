# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Strip Thai administrative prefixes from By-Tax-ID address lookups.

``erpnext_thailand.utils.get_address_by_tax_id`` fetches an address from the
Revenue Department SOAP service and prepends Thai prefixes onto the location
fields — ``ต.``/``อ.``/``จ.`` (and ``แขวง``/``เขต`` for Bangkok). Its sibling
``get_location_by_zip_code`` returns those same fields bare, straight from the
``Thai Zip Code`` table, so the two Address lookups stored different values for
the same place. This override replaces the whitelisted method through
``override_whitelisted_methods`` (hooks.py): it delegates to the original SOAP
fetch, then removes the prefixes so both lookups agree.
"""

from __future__ import annotations

from typing import Any, cast

import frappe

# Prefixes erpnext_thailand.utils.finalize_address_dict prepends per address key.
# Bangkok uses แขวง/เขต instead of ต./อ.; province is bare there, ต. otherwise.
_LOCATION_PREFIXES: dict[str, tuple[str, ...]] = {
    "city": ("ต.", "แขวง"),
    "county": ("อ.", "เขต"),
    "state": ("จ.",),
}


def _strip_location_prefixes(address: dict[str, Any]) -> dict[str, Any]:
    """Remove Thai administrative prefixes from the tambon/amphur/province fields."""
    for field, prefixes in _LOCATION_PREFIXES.items():
        value: str = cast(str, address.get(field) or "")
        for prefix in prefixes:
            value = value.removeprefix(prefix)
        address[field] = value
    return address


@frappe.whitelist()
def get_address_by_tax_id(tax_id: str | bool = False, branch: str | bool = False) -> dict[str, Any]:
    """Fetch an address by Tax ID, then strip Thai prefixes for zip-lookup parity.

    Delegates to ``erpnext_thailand.utils.get_address_by_tax_id`` — the SOAP
    fetch, argument validation, and permission behaviour are unchanged — and
    post-processes the returned ``city``/``county``/``state`` so they match the
    bare names ``get_location_by_zip_code`` returns. Replaces the original for
    every caller via ``override_whitelisted_methods``. The direct import call
    does not re-enter this override, so there is no recursion.
    """
    from erpnext_thailand.utils import get_address_by_tax_id as fetch_address_by_tax_id

    address = cast(dict[str, Any], fetch_address_by_tax_id(tax_id=tax_id, branch=branch))
    return _strip_location_prefixes(address)
