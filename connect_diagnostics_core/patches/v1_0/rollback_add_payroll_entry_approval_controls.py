# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Recovery entry point for the Payroll Entry approval route."""

from connect_diagnostics_core.patches.v1_0.add_payroll_entry_approval_controls import rollback


def execute() -> None:
    rollback()
