# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Verify native Freeze exception task ownership and exact desired content."""

from __future__ import annotations

from connect_diagnostics_core.patches.v1_0.add_freeze_exception_execution_task import execute as ensure_tasks


def execute() -> None:
    ensure_tasks()


def rollback() -> None:
    """Leave site-owned task records intact; rollback cannot prove ownership by name."""
    return
