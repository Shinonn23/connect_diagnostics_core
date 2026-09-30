# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Non-destructive recovery entry point for Stock Transfer approval controls."""

from __future__ import annotations

from connect_diagnostics_core.patches.v1_0.add_stock_transfer_approval_controls import rollback


def execute() -> None:
    rollback()
