# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for migrate_alias_to_item_child — one-way.

The forward patch inserted Item Alternative Name rows (label Other) using random hash names,
which are indistinguishable from alternative names added manually afterwards. Deleting by label
would remove unrelated user data, so no safe automatic reversal exists. No reversal is performed."""

from __future__ import annotations

import frappe


def execute() -> None:
    frappe.logger(__name__).info(
        "rollback_migrate_alias_to_item_child: no-op; migrated rows use random hash names indistinguishable from manual entries."
    )
