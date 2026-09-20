# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Verify the exported Stock Entry Freeze Exception schema is present."""

from __future__ import annotations


def execute() -> None:
    # Custom Field exports are synchronized by Frappe after patches.  Keep this
    # migration marker idempotent without creating third-party customizations in
    # patch code.
    return


def rollback() -> None:
    """Do not remove exported customizations from a live site during rollback."""
    return
