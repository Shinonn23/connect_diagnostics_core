# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Safely restore the pre-consolidation Stock Entry workflow state."""

from __future__ import annotations

from connect_diagnostics_core.patches.v1_0.consolidate_stock_entry_workflow import rollback


def execute() -> None:
    rollback()
